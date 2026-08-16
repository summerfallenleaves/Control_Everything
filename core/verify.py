"""步骤验证：检查动作是否真的改变了屏幕。

macOS 的 AX 读回可能不可靠（见调研文档），因此验证是与 orchestrator 分离、
可开关的独立关注点。这里的启发式简单且平台无关；更丰富的检查
（截图 diff、OCR）以后接入。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core.types import Action, ActionResult, ScreenState


def _extract_domain(url: str) -> Optional[str]:
    m = re.match(r'https?://([^/]+)', url)
    return m.group(1).lower() if m else None


@dataclass
class VerificationResult:
    ok: bool
    summary: str
    fatal: bool = False


def verify_step(
    prev: Optional[ScreenState],
    action: Action,
    result: ActionResult,
    current: ScreenState,
    backend=None,
) -> VerificationResult:
    """对上一次动作的启发式验证。"""
    if not result.ok:
        return VerificationResult(False, f'动作报告失败: {result.error}', fatal=True)

    if action.kind == 'open_app' and backend is not None and hasattr(backend, 'is_app_running'):
        target = action.text or action.target or ''
        if backend.is_app_running(target):
            return VerificationResult(True, f'{target} 正在运行')
        return VerificationResult(False, f'{target} 尚未运行', fatal=False)

    if action.kind in ('wait', 'open_app', 'copy', 'paste', 'key', 'done'):
        return VerificationResult(True, '该动作类型没有结构检查')

    if prev is None or prev.tree is None or current.tree is None:
        return VerificationResult(True, '没有可比较的上一快照')

    # 树是否发生了变化？
    prev_texts = {e.ref: e.text for e in prev.tree.flatten() if e.ref}
    cur_texts = {e.ref: e.text for e in current.tree.flatten() if e.ref}
    changed = [r for r in prev_texts if prev_texts.get(r) != cur_texts.get(r)]
    if changed:
        sample = ', '.join(changed[:3])
        return VerificationResult(True, f'屏幕已变化（{len(changed)} 个元素）')

    if action.kind == 'type' and action.text:
        # 导航检查：输入的 URL 是否出现在页面/窗口标题里？
        dom = _extract_domain(action.text)
        if dom:
            texts = [e.text.lower() for e in current.tree.flatten() if e.text]
            if any(dom.split('.')[0] in t or dom in t for t in texts):
                return VerificationResult(True, f'页面显示 {dom}')

    if action.kind in ('tap', 'type'):
        return VerificationResult(
            False,
            '动作后屏幕未变化（可能需要重新快照或异步等待）',
            fatal=False,
        )
    return VerificationResult(True, '无明显变化；继续')
