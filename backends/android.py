"""Android backend: adb + UIAutomator + scrcpy.

Skeleton — maps the unified model onto Android primitives:

  UIAutomator XML node                      -> core Element
    resource-id / text / class / bounds       ref / text / role / Rect
    bounds="[l,t][r,b]"                       normalized 0-1000

  Unified Action          -> Android mechanism
    tap(ref)                adb shell input tap (from normalized bounds)
    type(text)              ADBKeyboard / Appium IME (native input text has
                             no CJK support)
    swipe / scroll          adb shell input swipe
    key(back/home)          adb shell input keyevent 4 / 3
    open_app(pkg)           adb shell am start -n pkg/activity
    screenshot              adb exec-out screencap -p
    long_press / pinch      motionevent / multi-touch inject

Implementation steps (when porting):
  1. `adb devices` - require one device (USB debugging on)
  2. `adb shell uiautomator dump /sdcard/ui.xml && adb pull` for the tree
  3. Parse XML into Element tree (normalize bounds via screen size)
  4. scrcpy for real-time screen streaming on dynamic pages
  5. Handle dialog interference: permission prompts, ads, update popups
"""

from __future__ import annotations

import shutil
from typing import Optional

from core.types import Action, ActionResult, Element, Rect, ScreenState
from backends.base import BackendError, DeviceBackend


class AndroidBackend(DeviceBackend):
    """Controls an Android device over adb (skeleton)."""

    platform = "android"

    def __init__(self, serial: Optional[str] = None):
        if not shutil.which("adb"):
            raise BackendError("adb not found on PATH; install platform-tools")
        self.serial = serial
        self._device = ["adb"] + (["-s", serial] if serial else [])

    def _sh(self, *args: str) -> str:
        """Run an adb command, return stdout."""
        import subprocess
        proc = subprocess.run(self._device + list(args), capture_output=True, text=True)
        if proc.returncode != 0:
            raise BackendError(f"adb {args[0]} failed: {proc.stderr.strip()}")
        return proc.stdout

    # -- observation ---------------------------------------------------------

    def perceive(self) -> ScreenState:
        """TODO: uiautomator dump -> XML -> Element tree + screencap."""
        raise NotImplementedError("AndroidBackend.perceive: see docstring")

    # -- execution -----------------------------------------------------------

    def act(self, action: Action) -> ActionResult:
        """TODO: map unified Action onto adb primitives."""
        raise NotImplementedError("AndroidBackend.act: see docstring")


def parse_uiautomator_xml(xml: str, screen_w: int, screen_h: int) -> Element:
    """Parse a uiautomator dump into a normalized Element tree.

    Node mapping:
      resource-id -> ref, text/content-desc -> text,
      class -> role (android.widget.Button -> button ...),
      bounds="[l,t][r,b]" -> normalized Rect.
    """
    raise NotImplementedError("parse_uiautomator_xml: port when implementing")