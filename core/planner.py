"""任务规划：把高层目标分解为子目标。

第一阶段保持轻量：LLM 拿到完整目标，在循环里逐步决策。
后续增量（Roadmap）是专门的 plan()，为长任务返回检查清单。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from llm.client import LLMClient


@dataclass
class Plan:
    goal: str
    steps: list[str] = field(default_factory=list)  # 人类可读的子目标


class Planner:
    """为目标产出可选的步骤检查清单。"""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def plan(self, goal: str) -> Plan:
        if self.llm is None:
            # 尚无专门的规划模型：把目标作为单步返回。
            return Plan(goal=goal, steps=[goal])
        raise NotImplementedError('LLM-backed planning lands in the next increment')
