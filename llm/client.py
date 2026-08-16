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

from core.types import Action, ScreenState
from llm.providers import PROVIDER_ANTHROPIC, ProviderConfig, load_provider_config
from llm.schema import ACTION_SCHEMA, OBSERVATION_PROMPT


class LLMError(Exception):
    pass


class LLMClient(abc.ABC):
    """Turns observations into the next unified Action."""

    @abc.abstractmethod
    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Action:
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

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Action:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=512,
            tools=[{
                "name": "gui_action",
                "description": "Emit the next GUI action as one JSON object.",
                "input_schema": ACTION_SCHEMA,
            }],
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': OBSERVATION_PROMPT},
                {'type': 'text', 'text': _build_user_message(goal, state, history)},
            ]}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "gui_action":
                return _action_from_json(block.input)
        raise LLMError("model did not return a gui_action tool call")


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

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Action:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=512,
            tools=[{
                "type": "function",
                "function": {"name": "gui_action",
                    "description": "Emit the next GUI action as one JSON object.",
                    "parameters": ACTION_SCHEMA},
            }],
            tool_choice={"type": "function", "function": {"name": "gui_action"}},
            messages=[{'role': 'user', 'content': OBSERVATION_PROMPT + chr(10) + chr(10) +
                      _build_user_message(goal, state, history)}],
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            args = json.loads(msg.tool_calls[0].function.arguments)
            return _action_from_json(args)
        raise LLMError("model did not return a gui_action tool call")


class DummyClient(LLMClient):
    """Offline client for smoke tests: waits, then declares done."""

    def __init__(self, steps: int = 1):
        self._steps = steps

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Action:
        if len(history) >= self._steps:
            return Action(kind="done", note="dummy client finished")
        return Action(kind="wait", duration_s=0.1, note="dummy client: waiting")


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
