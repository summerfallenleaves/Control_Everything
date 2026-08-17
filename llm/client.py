"""LLM 客户端：Agent 循环背后可插拔的大脑。

每个客户端把（目标, ScreenState）转化为一个 Decision。

客户端由完整的 ProviderConfig（llm/providers.py）构建，
因此任何供应商都可以支撑任何用途：
  - AnthropicClient  : Anthropic Messages API（tool use）
  - OpenAIClient     : OpenAI SDK，含任意 OpenAI 兼容端点
                       （DeepSeek、Moonshot、Qwen、Ollama、vLLM……）
  - DummyClient      : 离线冒烟测试 / 演示
"""

from __future__ import annotations

import abc
import json
from typing import Optional

from core.types import Action, Decision, ScreenState
from llm.providers import PROVIDER_ANTHROPIC, ProviderConfig, load_provider_config
from llm.schema import ACTION_SCHEMA, SYSTEM_PROMPT


class LLMError(Exception):
    pass


class LLMClient(abc.ABC):
    """把观察转化为 Decision（一个动作，或纯文本）。

    宽松模式：tool_choice 为 auto，因此模型可以用文本回应
    （一个观察 / 计划 / 等待请求）而不是动作。
    """

    @abc.abstractmethod
    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        ...

    def ask(self, prompt: str, max_tokens: int = 1024) -> str:
        """自由文本问答（任务规划等辅助用途）。

        默认不支持；支持规划的具体客户端覆盖此方法。
        """
        raise NotImplementedError(f"{type(self).__name__} 不支持 ask")


def _tree_to_text(tree, depth: int = 0, limit: int = 200) -> list[str]:
    """把 Element 树紧凑地渲染给 LLM（节省 token）。"""
    out: list[str] = []

    def walk(e, d):
        if len(out) >= limit:
            return
        label = e.text[:40] if e.text else ''
        b = e.bounds
        bstr = f'[{b.x:.0f},{b.y:.0f}]' if b else ''
        line = f"{'  ' * d}- {e.ref} role={e.role}"
        if label:
            line += f' text={label!r}'
        if bstr:
            line += f' at {bstr}'
        out.append(line)
        for c in e.children:
            walk(c, d + 1)

    walk(tree, depth)
    return out


def _build_user_message(goal: str, state: ScreenState, history: list[str]) -> str:
    NL = chr(10)
    tree_text = NL.join(_tree_to_text(state.tree))
    prev = NL.join(history[-6:]) if history else '(无)'
    vision_note = state.meta.get('vision_note') if state.meta else None
    plan = state.meta.get('plan') if state.meta else None
    parts = [
        f'目标: {goal}{NL}{NL}',
        f'平台: {state.platform}, 应用: {state.app}{NL}{NL}',
    ]
    if plan:
        parts.append(f'任务计划（按顺序推进）:{NL}{plan}{NL}{NL}')
    if vision_note:
        parts.append(f'截图的视觉分析:{NL}{vision_note}{NL}{NL}')
    parts.append(f'UI 树:{NL}{tree_text}{NL}{NL}')
    parts.append(f'之前的动作:{NL}' + prev)
    return ''.join(parts)


def _effort_for_openai(effort: str, vendor: str) -> str:
    """把统一的 minimal/low/medium/high 映射到端点自己的 effort 值。

    OpenAI 官方接受全部四档；DeepSeek 接受 low/high/max
    （medium 在服务端映射为 high），因此低档坍缩为 low。
    """
    if vendor == 'deepseek':
        return {'minimal': 'low', 'low': 'low', 'medium': 'high', 'high': 'high',
                'max': 'max'}.get(effort, 'high')
    return 'high' if effort == 'max' else effort  # OpenAI 没有 'max'


def _budget_for_effort(effort: str) -> int:
    """Anthropic 某档 effort 对应的 budget_tokens（要求 >=1024）。"""
    return {'minimal': 1024, 'low': 2048, 'medium': 4096, 'high': 8192,
            'max': 16384}.get(effort or 'medium', 4096)


def _action_from_json(data: dict) -> Action:
    """把模型的动作 JSON 解析为统一 Action。"""
    kind = data.get("kind") or data.get("action", {}).get("kind")
    if not kind:
        raise LLMError(f'模型输出中没有 kind: {data}')
    from core.types import Point
    pos = data.get('pos')
    to = data.get('to')
    return Action(
        kind=kind,
        target=data.get("target"),
        pos=Point(pos["x"], pos["y"]) if pos else None,
        to=Point(to["x"], to["y"]) if to else None,
        text=data.get("text"),
        dir=data.get("dir"),
        key=data.get("key"),
        modifiers=data.get("modifiers") or [],
        duration_s=float(data.get("duration_s") or 0.5),
        note=data.get("reasoning") or "",
    )


class AnthropicClient(LLMClient):
    """Anthropic Messages API，tool use 限制为单一动作。"""

    def __init__(self, cfg: ProviderConfig):
        if not cfg.api_key:
            raise LLMError(
                "anthropic 供应商缺少 API key：请设置 "
                f'{cfg.purpose.upper()}_API_KEY（或 ANTHROPIC_API_KEY）'
            )
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("anthropic 包未安装；`uv add anthropic`") from e
        kwargs = {}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        self._client = anthropic.Anthropic(api_key=cfg.api_key, **kwargs)
        self.model = cfg.model
        self._cfg = cfg

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        kwargs: dict = {}
        if self._cfg.thinking == 'enabled':
            budget = _budget_for_effort(self._cfg.thinking_effort or 'medium')
            kwargs['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
            kwargs['max_tokens'] = max(8192, budget * 2)
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=kwargs.pop('max_tokens', 4096),
            tools=[{
                "name": "gui_action",
                "description": "输出下一个 GUI 动作（单个 JSON 对象）。",
                "input_schema": ACTION_SCHEMA,
            }],
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': _build_user_message(goal, state, history)},
            ]}],
            **kwargs,
        )
        text_parts: list[str] = []
        for block in resp.content:
            if block.type == "tool_use" and block.name == "gui_action":
                return Decision(action=_action_from_json(block.input))
            if block.type == 'text' and block.text:
                text_parts.append(block.text)
        if text_parts:
            return Decision(text=' '.join(text_parts).strip())
        raise LLMError("模型既没有返回工具调用也没有返回文本")

    def ask(self, prompt: str, max_tokens: int = 1024) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}],
        )
        parts = [b.text for b in resp.content if b.type == 'text' and b.text]
        return ' '.join(parts).strip()


class OpenAIClient(LLMClient):
    """OpenAI SDK chat-completions（可用于任意兼容端点）。

    把 DECISION_BASE_URL 指向 DeepSeek / Moonshot / Qwen / Ollama
    / vLLM / LM Studio 等即可，无需改代码。
    """

    def __init__(self, cfg: ProviderConfig):
        try:
            import openai
        except ImportError as e:
            raise LLMError("openai 包未安装；`uv add openai`") from e
        kwargs = {}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        # 本地端点（Ollama 等）接受任意非空 key。
        self._client = openai.OpenAI(api_key=cfg.api_key or "not-needed", **kwargs)
        self.model = cfg.model
        self._cfg = cfg

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        """宽松模式：tool_choice=auto；模型可以用文本回应。"""
        extra: dict = {}
        kwargs: dict = {}
        if self._cfg.thinking:  # DeepSeek 及兼容端点
            extra["extra_body"] = {"thinking": {"type": self._cfg.thinking}}
        if (self._cfg.thinking_effort and self._cfg.thinking != 'disabled'):
            kwargs["reasoning_effort"] = _effort_for_openai(
                self._cfg.thinking_effort, self._cfg.vendor)
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            tools=[{
                "type": "function",
                "function": {"name": "gui_action",
                    "description": "输出下一个 GUI 动作（单个 JSON 对象）。",
                    "parameters": ACTION_SCHEMA},
            }],
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': _build_user_message(goal, state, history)},
            ],
            **extra,
            **kwargs,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            args = json.loads(msg.tool_calls[0].function.arguments)
            return Decision(action=_action_from_json(args))
        text = (msg.content or '').strip()
        if text:
            return Decision(text=text)
        raise LLMError("模型既没有返回工具调用也没有返回文本")

    def ask(self, prompt: str, max_tokens: int = 1024) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return (resp.choices[0].message.content or '').strip()


class DummyClient(LLMClient):
    """离线客户端（冒烟测试）：等待，然后宣告完成。"""

    def __init__(self, steps: int = 1):
        self._steps = steps

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        if len(history) >= self._steps:
            return Decision(action=Action(kind="done", note="dummy 客户端结束"))
        return Decision(action=Action(kind="wait", duration_s=0.1, note="dummy 客户端：等待"))

    def ask(self, prompt: str, max_tokens: int = 1024) -> str:
        return ''


def get_client(
    purpose: str = 'decision',
    *,
    name: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMClient:
    """按用途从其完整供应商配置构建客户端。

    显式传入的覆盖参数（provider/model/api_key/base_url）优先于 .env。
    """
    if name == 'dummy':
        return DummyClient()
    cfg = load_provider_config(
        purpose, provider=provider, model=model, api_key=api_key, base_url=base_url
    )
    if purpose == 'vision':
        from llm.vision import VisionClient
        return VisionClient(cfg)
    if cfg.provider == PROVIDER_ANTHROPIC:
        return AnthropicClient(cfg)
    return OpenAIClient(cfg)
