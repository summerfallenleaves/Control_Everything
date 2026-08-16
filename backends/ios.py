"""iOS backend: Appium / WebDriverAgent (WDA).

Skeleton — iOS is the most constrained platform:
  - Physical devices need a developer certificate + WDA service
  - Screenshots only via WDA (no direct screencap)

  Unified Action          -> iOS mechanism
    tap(ref)                WDA POST /session/:id/wda/tap (coords from frame)
    type(text)              WDA sendKeys (supports CJK)
    swipe / scroll          WDA swipe / scroll endpoints
    key(home)               WDA pressButton("home")
    open_app(bundle)        WDA app activate / springboard launch
    screenshot              WDA GET /screenshot (PNG base64)

Notes:
  - WDA hierarchy JSON mirrors the unified model almost 1:1
    (type -> role, label -> text, identifier -> ref, frame -> Rect)
  - Permission popups and SpringBoard alerts need explicit dismissal
"""

from __future__ import annotations

from core.types import Action, ActionResult, ScreenState
from backends.base import DeviceBackend


class IOSBackend(DeviceBackend):
    """Controls an iOS device via Appium WebDriverAgent (skeleton)."""

    platform = "ios"

    def __init__(self, wda_url: str = "http://127.0.0.1:8100"):
        self.wda_url = wda_url.rstrip("/")

    def perceive(self) -> ScreenState:
        """TODO: WDA GET /session/:id/source + /screenshot."""
        raise NotImplementedError("IOSBackend.perceive")

    def act(self, action: Action) -> ActionResult:
        """TODO: map unified Action onto WDA endpoints."""
        raise NotImplementedError("IOSBackend.act")