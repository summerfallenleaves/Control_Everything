"""反思机制：连续失败后的结构化复盘。

当动作连续失败达到阈值时，用 LLM 回顾最近的失败与记忆，
分析原因并输出下一步策略建议；结论注入记忆指导后续决策。
带冷却机制，避免反复触发浪费调用。
"""

from __future__ import annotations

from typing import Optional

from llm.client import LLMClient


class Reflector:
    """失败后的策略复盘器。"""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def reflect(self, goal: str, memory_render: str, recent_history: list[str]) -> str:
        """分析最近失败并输出策略建议；失败时返回空串（不阻塞）。"""
        if self.llm is None:
            return ""
        try:
            recent = chr(10).join(recent_history[-8:]) if recent_history else '(无)'
            prompt = (
                f'目标: {goal}{chr(10)}'
                f'结构化记忆:{chr(10)}{memory_render or "(空)"}{chr(10)}'
                f'最近历史:{chr(10)}{recent}{chr(10)}'
                '上面的操作最近连续失败了。请分析失败原因，并给出下一步策略建议。{chr(10)}'
                '要求：只输出 1-2 条简短建议（每条不超过 30 字），不要解释过程。'
            )
            text = self.llm.ask(prompt, max_tokens=300)
            return text.strip()
        except Exception as e:
            print(f'反思失败（跳过）: {e}')
            return ""
