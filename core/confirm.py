"""危险动作确认：Human-in-the-loop 安全底线。

对不可逆/有实际后果的动作（支付、下单、发送、提交等）执行前必须
获得用户确认。判定用关键词匹配（代码级拦截，模型无法绕过），
确认交互通过 orchestrator 注入的 confirm_callback 完成。
"""

from __future__ import annotations

from typing import Optional

from core.types import Action

# 危险关键词（触发确认）。可随时增删。
DANGEROUS_KEYWORDS = [
    # 支付/付款/下单/购买类
    "支付", "付款", "下单", "结账", "购买", "付费", "买单", "订单",
    "checkout", "pay", "purchase", "order",
    # 发送/发布/提交类
    "发送", "发布", "提交", "确认购买", "确认支付",
    "submit", "send", "publish", "post",
]


def find_dangerous_keyword(action: Action) -> Optional[str]:
    """返回动作命中的第一个危险关键词；未命中返回 None。

    检查范围：动作的 text（要输入的文本/URL/应用名）与
    note（模型的动作理由）。
    """
    haystack = ((action.text or "") + " " + (action.note or "")).lower()
    for kw in DANGEROUS_KEYWORDS:
        if kw.lower() in haystack:
            return kw
    return None


def is_dangerous(action: Action) -> bool:
    """动作是否属于需要用户确认的危险操作。"""
    return find_dangerous_keyword(action) is not None
