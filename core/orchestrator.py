"""Agent 编排器：平台无关的「观察 -> 规划 -> 执行 -> 验证」循环。

适用于任意 DeviceBackend（macOS、Android、iOS）和任意 LLMClient。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from backends.base import DeviceBackend
from core.confirm import find_dangerous_keyword
from core.memory import Memory
from core.types import Action, ActionResult, Decision, ScreenState
from core.verify import VerificationResult, extract_domain, verify_step
from llm.client import LLMClient

# 可能改变屏幕的动作；这些动作之后的下一步总是强制做一次
# 全新的视觉分析（界面突变那一刻最需要「看见」）。
VISION_TRIGGER_ACTIONS = frozenset({
    'tap', 'type', 'key', 'open_app', 'scroll', 'swipe', 'paste',
    'back', 'home', 'app_switch', 'long_press',
})


@dataclass
class RunResult:
    goal: str
    ok: bool = False
    steps: int = 0
    history: list[str] = field(default_factory=list)
    last_error: str = ''
    duration_s: float = 0.0


class AgentOrchestrator:
    """基于 backend + LLM 把一个任务执行到完成。"""

    def __init__(
        self,
        backend: DeviceBackend,
        llm: LLMClient,
        max_steps: int = 20,
        verify: bool = True,
        max_text_rounds: int = 3,
        vision=None,
        vision_interval: int = 3,
        confirm_callback=None,
        planner=None,
    ):
        self.backend = backend
        self.llm = llm
        self.max_steps = max_steps
        self.verify_enabled = verify
        self.max_text_rounds = max_text_rounds
        self.vision = vision
        self.vision_interval = max(1, vision_interval)
        # 初始设为间隔值，让第 1 步必定做视觉分析（全新开始）。
        self._steps_since_vision = self.vision_interval
        self._fail_counts: dict[tuple, int] = {}
        # 危险动作确认（Human-in-the-loop）
        self.confirm_callback = confirm_callback
        # 任务规划（长任务导航）
        self.planner = planner
        # 结构化记忆（跨轮持久上下文）
        self.memory = Memory()
        self._confirm_allowed: set[str] = set()  # 记住允许的关键词
        self._confirm_denied: set[str] = set()   # 记住拒绝的关键词
        self.history: list[str] = []

    def run(self, goal: str) -> RunResult:
        started = time.monotonic()
        result = RunResult(goal=goal)
        prev_state: Optional[ScreenState] = None
        last_action_kind: Optional[str] = None
        pending_domain: Optional[str] = None

        # 任务开始前规划一次（失败则退回无规划模式，不阻塞）
        plan_summary = ''
        if self.planner is not None:
            try:
                plan = self.planner.plan(goal)
                plan_summary = plan.summary
                if plan_summary:
                    self.history.append(f'任务计划:{chr(10)}{plan_summary}')
            except Exception as e:
                self.history.append(f'规划跳过: {e}')

        for step in range(1, self.max_steps + 1):
            try:
                state = self.backend.perceive()
            except Exception as e:
                result.last_error = f'感知失败: {e}'
                return result

            if plan_summary:
                state.meta['plan'] = plan_summary
            memory_text = self.memory.render()
            if memory_text:
                state.meta['memory'] = memory_text

            do_vision = False
            if self.vision is not None and state.screenshot is not None:
                self._steps_since_vision += 1
                if last_action_kind in VISION_TRIGGER_ACTIONS:
                    do_vision = True
                elif self._steps_since_vision >= self.vision_interval:
                    do_vision = True
            if do_vision:
                try:
                    note = self.vision.describe(
                        state.screenshot, goal=goal,
                        platform=state.platform, app=state.app,
                    )
                    if note:
                        state.meta['vision_note'] = note
                        self.history.append(f'  视觉: {note[:150]}')
                    self._steps_since_vision = 0
                except Exception as e:
                    self.history.append(f'  视觉跳过: {e}')

            decision: Decision = self.llm.decide(goal, state, self.history)

            if not decision.is_action:
                # 宽松模式：模型用文本回应（观察 / 计划）。
                # 记录它、防止纯文本死循环，然后重新观察。
                text = decision.text.strip()
                self.history.append(f'模型: {text[:200]}')
                if not text:
                    result.last_error = '模型返回了空文本'
                    return result
                recent = self.history[-self.max_text_rounds:]
                if (len(recent) >= self.max_text_rounds
                        and all(h.startswith('模型: ') for h in recent)):
                    result.last_error = (
                        f'模型连续 {self.max_text_rounds} 轮只输出文本（无动作）'
                        '；判定为卡死'
                    )
                    return result
                continue

            action: Action = decision.action

            if action.kind == 'ask_user':
                # 模型主动向用户提问（如需要人工登录）：把回答写入历史，
                # 让模型下一轮根据回答继续决策。
                question = action.text or action.note or '(未说明问题)'
                answer = self._ask_user(question)
                self.history.append(f'模型提问: {question[:200]}')
                self.history.append(f'用户回答: {answer[:200]}')
                self.memory.record_user_qa(question[:200], answer[:200])
                continue

            if action.kind == 'done':
                result.ok = True
                result.steps = step
                result.history = list(self.history)
                result.duration_s = time.monotonic() - started
                return result

            # 危险动作确认（Human-in-the-loop）
            confirm_deny = self._confirm_guard(action)
            if confirm_deny is not None:
                act_result = ActionResult(
                    False, action, error=confirm_deny, detail='用户拒绝执行'
                )
                self.history.append(_fmt_action(action, act_result))
                result.last_error = f'动作 {action.kind} 被用户拒绝: {confirm_deny}'
                last_action_kind = None
                continue

            act_result: ActionResult = self.backend.act(action)
            self.history.append(_fmt_action(action, act_result))
            self.memory.record_action(action, act_result)
            if act_result.ok and action.kind in ('open_app', 'open_url', 'set_address_bar'):
                self.memory.add_fact(
                    f'{action.kind} {action.text or action.target or ""} 成功'
                )

            if not act_result.ok:
                result.last_error = f'动作 {action.kind} 失败: {act_result.error}'
                last_action_kind = None  # 失败的动作没有改变任何东西
                # 防重复失败：相同动作连续失败达到阈值时显式警告 LLM 换策略
                fail_key = (
                    action.kind,
                    (action.target or ''),
                    str(action.pos or ''),
                    (action.text or '')[:60],
                )
                self._fail_counts[fail_key] = self._fail_counts.get(fail_key, 0) + 1
                n = self._fail_counts[fail_key]
                if n >= 3:
                    self.history.append(
                        f'警告: 这个动作已连续失败 {n} 次，不要再重复！'
                        f'请换一种策略（例如改用 pos 坐标点击、'
                        f'set_address_bar(url) 或重新感知后再定位元素）。'
                    )
                # 继续循环：LLM 可以恢复（例如重新定位元素）
                continue

            last_action_kind = action.kind

            # 记录最近输入的 URL 域名，供 wait 之后的导航验证使用。
            if action.kind in ('type', 'open_url') and action.text:
                dom = extract_domain(action.text)
                if dom:
                    pending_domain = dom

            if self.verify_enabled:
                try:
                    new_state = self.backend.perceive()
                    v: VerificationResult = verify_step(
                        prev_state, action, act_result, new_state, backend=self.backend,
                        pending_domain=pending_domain,
                    )
                    self.history.append(f'  验证: {v.summary}')
                    prev_state = new_state
                    if v.ok and '页面已显示' in v.summary:
                        pending_domain = None  # 导航已确认，清除待验证域名
                    if not v.ok and v.fatal:
                        result.last_error = f'验证失败: {v.summary}'
                        return result
                except Exception as e:
                    self.history.append(f'  验证跳过: {e}')
            else:
                prev_state = state

        result.last_error = f'超过最大步数 max_steps={self.max_steps}'
        result.steps = self.max_steps
        result.history = list(self.history)
        result.duration_s = time.monotonic() - started
        return result


    def _ask_user(self, question: str) -> str:
        """向用户提问（ask_user 动作），返回自由文本回答。"""
        if self.confirm_callback is not None:
            ans = self.confirm_callback(question, ask_mode=True)
            if ans:
                return str(ans)
        return "(无回答)"

    def _confirm_guard(self, action: Action) -> str | None:
        """危险动作确认门卫。

        返回 None 表示放行；返回拒绝原因字符串表示不执行。
        """
        kw = find_dangerous_keyword(action)
        if kw is None:
            return None
        if kw in self._confirm_allowed:
            return None  # 已记住允许
        if kw in self._confirm_denied:
            return f'关键词「{kw}」已被用户拒绝（本会话记住）'
        if self.confirm_callback is None:
            # 无确认通道且未记住 -> 默认拒绝（安全优先）
            return f'危险动作（{kw}）无确认通道，默认拒绝'
        choice = self.confirm_callback(action)
        if choice == 'y':
            self._confirm_allowed.add(kw)
            self.memory.record_user_qa(f'允许执行危险动作', f'关键词「{kw}」允许并记住')
            return None
        if choice == 'n':
            self._confirm_denied.add(kw)
            self.memory.record_user_qa(f'拒绝危险动作', f'关键词「{kw}」拒绝并记住')
            return f'用户拒绝并记住：{kw}'
        if choice == 'o':
            return None  # 仅本次允许
        if choice == 'c':
            return f'用户仅本次拒绝：{kw}'
        return f'未获用户确认（默认拒绝）：{kw}'


def _fmt_action(a: Action, r: ActionResult) -> str:
    d = a.to_dict()
    tail = f' -> ok' if r.ok else f' -> 失败: {r.error}'
    return f'[{d.pop("kind")}] {d} {tail}'
