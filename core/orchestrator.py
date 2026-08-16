"""Agent orchestrator: the platform-agnostic observe -> plan -> act -> verify loop.

Works with any DeviceBackend (macOS, Android, iOS) and any LLMClient.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from backends.base import DeviceBackend
from core.types import Action, ActionResult, ScreenState
from core.verify import VerificationResult, verify_step
from llm.client import LLMClient


@dataclass
class RunResult:
    goal: str
    ok: bool = False
    steps: int = 0
    history: list[str] = field(default_factory=list)
    last_error: str = ''
    duration_s: float = 0.0


class AgentOrchestrator:
    """Runs one task to completion against a backend + LLM."""

    def __init__(
        self,
        backend: DeviceBackend,
        llm: LLMClient,
        max_steps: int = 20,
        verify: bool = True,
    ):
        self.backend = backend
        self.llm = llm
        self.max_steps = max_steps
        self.verify_enabled = verify
        self.history: list[str] = []

    def run(self, goal: str) -> RunResult:
        started = time.monotonic()
        result = RunResult(goal=goal)
        prev_state: Optional[ScreenState] = None

        for step in range(1, self.max_steps + 1):
            try:
                state = self.backend.perceive()
            except Exception as e:
                result.last_error = f'perceive failed: {e}'
                return result

            action = self.llm.decide(goal, state, self.history)

            if action.kind == 'done':
                result.ok = True
                result.steps = step
                result.history = list(self.history)
                result.duration_s = time.monotonic() - started
                return result

            act_result: ActionResult = self.backend.act(action)
            self.history.append(_fmt_action(action, act_result))

            if not act_result.ok:
                result.last_error = f'action {action.kind} failed: {act_result.error}'
                # keep going: LLM may recover (e.g. re-locate element)
                continue

            if self.verify_enabled:
                try:
                    new_state = self.backend.perceive()
                    v: VerificationResult = verify_step(prev_state, action, act_result, new_state)
                    self.history.append(f'  verify: {v.summary}')
                    prev_state = new_state
                    if not v.ok and v.fatal:
                        result.last_error = f'verification failed: {v.summary}'
                        return result
                except Exception as e:
                    self.history.append(f'  verify skipped: {e}')
            else:
                prev_state = state

        result.last_error = f'exceeded max_steps={self.max_steps}'
        result.steps = self.max_steps
        result.history = list(self.history)
        result.duration_s = time.monotonic() - started
        return result


def _fmt_action(a: Action, r: ActionResult) -> str:
    d = a.to_dict()
    tail = f' -> ok' if r.ok else f' -> FAILED: {r.error}'
    return f'[{d.pop("kind")}] {d} {tail}'