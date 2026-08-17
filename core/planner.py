"""任务规划：把高层目标分解为界面操作步骤清单。

规划由 PLANNING 配置的模型（llm.client 的 ask 能力）完成；
orchestrator 在任务开始时调用一次，之后把清单注入每轮决策上下文，
让决策模型按计划顺序推进——解决长任务（搜索→筛选→加购→下单）
只看最近几步历史而迷失的问题。

容错：规划失败或解析异常时退回无规划模式（不阻塞主流程）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from llm.client import LLMClient


@dataclass
class Plan:
    goal: str
    steps: list[str] = field(default_factory=list)  # 人类可读的子步骤

    @property
    def summary(self) -> str:
        if not self.steps:
            return ""
        return chr(10).join(f'{i+1}. {s}' for i, s in enumerate(self.steps))


_PLAN_PROMPT_TEMPLATE = (

    '目标: {goal}{nl}'

    '把目标分解为可在真实设备上执行的界面操作步骤清单，要求：{nl}'

    '- 不超过 8 步，每步简短具体（如「打开淘宝」「搜索除湿机」{nl}'

    '  「点击第一个商品」「加入购物车」「去结算」）{nl}'

    '- 只输出步骤本身，每行一条，不要编号、不要解释、不要额外文字。'

)


class Planner:
    """用 LLM 为目标生成步骤清单。"""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def plan(self, goal: str) -> Plan:
        if self.llm is None:
            return Plan(goal=goal, steps=[])
        try:
            prompt = _PLAN_PROMPT_TEMPLATE.format(goal=goal, nl=chr(10))
            text = self.llm.ask(prompt)
            if not text:
                return Plan(goal=goal, steps=[])
            steps = []
            for line in text.splitlines():
                s = line.strip()
                if not s:
                    continue
                # 去掉可能的编号前缀（1. / - / 、/ ① 等）
                s = re.sub(r'^[\d\.\-、①-⑩\s]+', '', s).strip()
                if s and s not in steps:
                    steps.append(s)
                if len(steps) >= 8:
                    break
            return Plan(goal=goal, steps=steps)
        except Exception as e:
            print(f'规划失败，退回无规划模式: {e}')
            return Plan(goal=goal, steps=[])
