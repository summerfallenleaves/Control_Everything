"""Task planning: decompose a high-level goal into sub-goals.

Phase 1 keeps planning light: the LLM is given the full goal and decides
step-by-step in the loop. A dedicated plan() that returns a checklist for
long tasks is the next increment (Roadmap).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from llm.client import LLMClient


@dataclass
class Plan:
    goal: str
    steps: list[str] = field(default_factory=list)  # human-readable sub-goals


class Planner:
    """Produces an optional step checklist for the goal."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def plan(self, goal: str) -> Plan:
        if self.llm is None:
            # No dedicated planning model yet: return the goal as a single step.
            return Plan(goal=goal, steps=[goal])
        raise NotImplementedError('LLM-backed planning lands in the next increment')