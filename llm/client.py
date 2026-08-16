"""LLM clients: pluggable brains behind the agent loop.

Every client turns (goal, ScreenState) into one unified Action.
AnthropicClient uses the Messages API with structured output.
DummyClient exists for offline smoke tests / demos.
"""

from __future__ import annotations

import abc
import os
from typing import Optional

from dotenv import load_dotenv

from core.types import Action, ScreenState
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


class AnthropicClient(LLMClient):
    """Anthropic Messages API with tool-use constrained to one action.

    Model and key come from environment variables named by PURPOSE:
      DECISION_MODEL     - model used to pick the next action
      ANTHROPIC_API_KEY  - provider key
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        load_dotenv()  # idempotent; also loads when used outside main.py
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("anthropic package not installed; `uv add anthropic`") from e
        if not api_key:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY not set (see .env.example)")
        if not model:
            model = os.environ.get("DECISION_MODEL") or "claude-sonnet-4-5"
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Action:
        NL = chr(10)
        tree_text = NL.join(_tree_to_text(state.tree))
        prev = NL.join(history[-6:]) if history else '(none)'
        user = (
            f'Goal: {goal}{NL}{NL}'
            f'Platform: {state.platform}, app: {state.app}{NL}{NL}'
            f'UI tree:{NL}{tree_text}{NL}{NL}'
            f'Previous actions:{NL}' + prev
        )
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
                {'type': 'text', 'text': user},
            ]}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "gui_action":
                return self._action_from_json(block.input)
        raise LLMError("model did not return a gui_action tool call")

    @staticmethod
    def _action_from_json(data: dict) -> Action:
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


class DummyClient(LLMClient):
    """Offline client for smoke tests: waits, then declares done."""

    def __init__(self, steps: int = 1):
        self._steps = steps

    def decide(self, goal: str, state: ScreenState, history: list[str]) -> Action:
        if len(history) >= self._steps:
            return Action(kind="done", note="dummy client finished")
        return Action(kind="wait", duration_s=0.1, note="dummy client: waiting")


def get_client(name: str = 'anthropic', **kwargs) -> LLMClient:
    if name == 'anthropic':
        return AnthropicClient(**kwargs)
    if name == 'dummy':
        kwargs.pop('model', None)
        return DummyClient(**kwargs)
    raise LLMError(f"unknown client: {name}")
