"""结构化记忆：长任务的持久上下文。

纯文本 history 只给决策模型最近 6 步，长任务会迷失、重复劳动。
Memory 把关键信息结构化分类，跨轮持久，每轮渲染后注入决策上下文：

  - 已完成的关键动作（去重，最近 N 条）
  - 失败的尝试（带连续失败计数，提示「不要再重复」）
  - 用户交互（ask_user 问答、确认决定）
  - 环境事实（打开的应用、导航到的页面等）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.types import Action, ActionResult


@dataclass
class Memory:
    """Agent 的跨轮持久结构化记忆。"""

    completed: list[str] = field(default_factory=list)   # 成功动作摘要
    failures: dict[str, int] = field(default_factory=dict)  # 失败键 -> 计数
    user_qa: list[tuple[str, str]] = field(default_factory=list)  # (问题, 回答)
    facts: list[str] = field(default_factory=list)       # 环境事实
    max_completed: int = 10
    max_facts: int = 8

    def record_action(self, action: Action, result: ActionResult) -> None:
        """记录动作结果：成功进 completed，失败进 failures 计数。"""
        brief = self._brief(action)
        if result.ok:
            if brief not in self.completed:
                self.completed.append(brief)
                self.completed = self.completed[-self.max_completed:]
            # 成功后清除同类失败计数
            self.failures.pop(brief, None)
        else:
            self.failures[brief] = self.failures.get(brief, 0) + 1

    def record_user_qa(self, question: str, answer: str) -> None:
        self.user_qa.append((question, answer))
        self.user_qa = self.user_qa[-5:]

    def add_fact(self, fact: str) -> None:
        if fact not in self.facts:
            self.facts.append(fact)
            self.facts = self.facts[-self.max_facts:]

    @staticmethod
    def _brief(action: Action) -> str:
        parts = [action.kind]
        if action.text:
            parts.append(str(action.text)[:50])
        elif action.target:
            parts.append(str(action.target)[:50])
        elif action.pos:
            parts.append(f"({action.pos.x:.0f},{action.pos.y:.0f})")
        return " ".join(parts)

    def render(self) -> str:
        """渲染为注入决策上下文的结构化文本块。"""
        NL = chr(10)
        blocks: list[str] = []
        if self.completed:
            items = NL.join(f'  ✓ {c}' for c in self.completed[-self.max_completed:])
            blocks.append(f'【已完成的关键动作】{NL}{items}')
        if self.failures:
            items = NL.join(
                f'  ✗ {k}（连续失败 {v} 次，不要再重复）'
                for k, v in self.failures.items()
            )
            blocks.append(f'【失败的尝试】{NL}{items}')
        if self.user_qa:
            items = NL.join(f'  Q: {q}{NL}  A: {a}' for q, a in self.user_qa)
            blocks.append(f'【用户交互】{NL}{items}')
        if self.facts:
            items = NL.join(f'  · {f}' for f in self.facts)
            blocks.append(f'【环境事实】{NL}{items}')
        return NL.join(blocks)
