"""LLM clients: pluggable brains behind the agent loop.

Every client turns (goal, ScreenState) into one unified Action.

Clients are built from a full ProviderConfig (llm/providers.py) so any
vendor can back any purpose:
  - AnthropicClient  : Anthropic Messages API (tool use)
  - OpenAIClient     : OpenAI SDK, incl. any OpenAI-compatible endpoint
                       (DeepSeek, Moonshot, Qwen, Ollama, vLLM, ...)
  - DummyClient      : offline smoke tests / demos
"""

from __future__ import annotations

import abc
import json
from typing import Optional

from core.types import Action, Decision, ScreenState
from llm.providers import PROVIDER_ANTHROPIC, ProviderConfig, load_provider_config
from llm.schema import ACTION_SCHEMA, OBSERVATION_PROMPT


class LLMError(Exception):
    pass


class LLMClient(abc.ABC):
    """Turns observations into a Decision (an Action, or plain text).

    Relaxed mode: tool_choice is auto, so the model may reply with text
    (an observation / plan / wait request) instead of an action.
    """

    @abc.abstractmethod
    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        ...


def _tree_to_text(tree, depth: int = 0, limit: int = 200) -> list[str]:
    """Render the Element tree compactly for the LLM (token-friendly)."""
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
    prev = NL.join(history[-6:]) if history else '(none)'
    return (
        f'Goal: {goal}{NL}{NL}'
        f'Platform: {state.platform}, app: {state.app}{NL}{NL}'
        f'UI tree:{NL}{tree_text}{NL}{NL}'
        f'Previous actions:{NL}' + prev
    )


def _effort_for_openai(effort: str, vendor: str) -> str:
    """Map unified minimal/low/medium/high onto an endpoint's effort values.

    OpenAI official accepts all four; DeepSeek accepts low/high/max
    (medium maps to high server-side), so low tiers collapse to low.
    """
    if vendor == 'deepseek':
        return {'minimal': 'low', 'low': 'low', 'medium': 'high', 'high': 'high',
                'max': 'max'}.get(effort, 'high')
    return 'high' if effort == 'max' else effort  # OpenAI has no 'max'


def _budget_for_effort(effort: str) -> int:
    """Anthropic budget_tokens for an effort level (>=1024 required)."""
    return {'minimal': 1024, 'low': 2048, 'medium': 4096, 'high': 8192,
            'max': 16384}.get(effort or 'medium', 4096)


def _action_from_json(data: dict) -> Action:
    """Parse a model's action JSON into a unified Action."""
    kind = data.get("kind") or data.get("action", {}).get("kind")
    if not kind:
        raise LLMError(f"no kind in model output: {data}")
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
    """Anthropic Messages API with tool-use constrained to one action."""

    def __init__(self, cfg: ProviderConfig):
        if not cfg.api_key:
            raise LLMError(
                "no API key for anthropic provider: set "
                f"{cfg.purpose.upper()}_API_KEY (or ANTHROPIC_API_KEY)"
            )
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("anthropic package not installed; `uv add anthropic`") from e
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
                "description": "Emit the next GUI action as one JSON object.",
                "input_schema": ACTION_SCHEMA,
            }],
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': OBSERVATION_PROMPT},
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
        raise LLMError("model returned neither a tool call nor text")


class OpenAIClient(LLMClient):
    """OpenAI SDK chat-completions (works with any compatible endpoint).

    Set DECISION_BASE_URL to point at DeepSeek / Moonshot / Qwen / Ollama
    / vLLM / LM Studio etc. without code changes.
    """

    def __init__(self, cfg: ProviderConfig):
        try:
            import openai
        except ImportError as e:
            raise LLMError("openai package not installed; `uv add openai`") from e
        kwargs = {}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        # Local endpoints (Ollama etc.) accept any non-empty key.
        self._client = openai.OpenAI(api_key=cfg.api_key or "not-needed", **kwargs)
        self.model = cfg.model
        self._cfg = cfg

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        """Relaxed mode: tool_choice=auto; the model may reply with text."""
        extra: dict = {}
        kwargs: dict = {}
        if self._cfg.thinking:  # DeepSeek & compatible endpoints
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
                    "description": "Emit the next GUI action as one JSON object.",
                    "parameters": ACTION_SCHEMA},
            }],
            messages=[{'role': 'user', 'content': OBSERVATION_PROMPT + chr(10) + chr(10) +
                      _build_user_message(goal, state, history)}],
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
        raise LLMError("model returned neither a tool call nor text")


class DummyClient(LLMClient):
    """Offline client for smoke tests: waits, then declares done."""

    def __init__(self, steps: int = 1):
        self._steps = steps

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Decision:
        if len(history) >= self._steps:
            return Decision(action=Action(kind="done", note="dummy client finished"))
        return Decision(action=Action(kind="wait", duration_s=0.1, note="dummy client: waiting"))


def get_client(
    purpose: str = 'decision',
    *,
    name: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMClient:
    """Build a client for a purpose from its full provider config.

    Overrides (provider/model/api_key/base_url) win over .env when given.
    """
    if name == 'dummy':
        return DummyClient()
    cfg = load_provider_config(
        purpose, provider=provider, model=model, api_key=api_key, base_url=base_url
    )
    if cfg.provider == PROVIDER_ANTHROPIC:
        return AnthropicClient(cfg)
    return OpenAIClient(cfg)
