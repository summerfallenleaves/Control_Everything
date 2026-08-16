"""Step verification: check that an action actually changed the screen.

macOS AX read-back can be unreliable (see research doc), so verification is
a separate concern the orchestrator can toggle. Heuristics here are simple
and platform-agnostic; richer checks (screenshot diff, OCR) plug in later.
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
    """Heuristic verification of the last action."""
    if not result.ok:
        return VerificationResult(False, f'action reported failure: {result.error}', fatal=True)

    if action.kind == 'open_app' and backend is not None and hasattr(backend, 'is_app_running'):
        target = action.text or action.target or ''
        if backend.is_app_running(target):
            return VerificationResult(True, f'{target} is running')
        return VerificationResult(False, f'{target} not yet running', fatal=False)

    if action.kind in ('wait', 'open_app', 'copy', 'paste', 'key', 'done'):
        return VerificationResult(True, 'no structural check for this action kind')

    if prev is None or prev.tree is None or current.tree is None:
        return VerificationResult(True, 'no previous snapshot to compare')

    # tree changed at all?
    prev_texts = {e.ref: e.text for e in prev.tree.flatten() if e.ref}
    cur_texts = {e.ref: e.text for e in current.tree.flatten() if e.ref}
    changed = [r for r in prev_texts if prev_texts.get(r) != cur_texts.get(r)]
    if changed:
        sample = ', '.join(changed[:3])
        return VerificationResult(True, f'screen changed ({len(changed)} elements)')

    if action.kind == 'type' and action.text:
        # navigation check: did a URL-like input surface in the page/window title?
        dom = _extract_domain(action.text)
        if dom:
            texts = [e.text.lower() for e in current.tree.flatten() if e.text]
            if any(dom.split('.')[0] in t or dom in t for t in texts):
                return VerificationResult(True, f'page shows {dom}')

    if action.kind in ('tap', 'type'):
        return VerificationResult(
            False,
            'screen unchanged after action (may need re-snapshot or async wait)',
            fatal=False,
        )
    return VerificationResult(True, 'no visible change; continuing')