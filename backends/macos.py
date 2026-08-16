"""macOS backend: Accessibility API (pyobjc) + CoreGraphics events.

Verified on macOS 26.5.2 against Safari / TextEdit (see
docs/macos-accessibility-research.md):

- AX tree traversal and element coordinates: working
- AXValue text entry (incl. Chinese): working
- screencapture screenshots: working (Screen Recording permission granted)

Strategy (three-layer hybrid):
  1. AX semantic actions (AXPress / set AXValue) - preferred, stable
  2. CGEvent coordinate fallback (self-drawn / WebView controls)
  3. screenshot + vision (not here; exposed via perceive().screenshot)
"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

from core.types import Action, ActionResult, Element, Point, Rect, ScreenState
from backends.base import (
    ActionNotSupportedError,
    BackendError,
    DeviceBackend,
    ElementNotFoundError,
    PermissionError_,
)

try:  # macOS only; import errors surface at construction time
    import ApplicationServices as ax
    import AppKit
    import Quartz
except ImportError:  # pragma: no cover - non-macOS
    ax = AppKit = Quartz = None

# AX role -> normalized role
_ROLE_MAP = {
    "AXButton": "button",
    "AXTextField": "text_field",
    "AXTextArea": "text_field",
    "AXComboBox": "text_field",
    "AXSearchField": "text_field",
    "AXWindow": "window",
    "AXStaticText": "text",
    "AXRadioButton": "radio",
    "AXCheckBox": "checkbox",
    "AXMenuBarItem": "menu_item",
    "AXMenuItem": "menu_item",
    "AXMenu": "menu",
    "AXScrollArea": "scroll_area",
    "AXImage": "image",
    "AXLink": "link",
    "AXSwitch": "switch",
    "AXSlider": "slider",
    "AXTabGroup": "group",
    "AXGroup": "group",
    "AXList": "list",
    "AXTable": "table",
    "AXCell": "cell",
    "AXDialog": "dialog",
    "AXSheet": "dialog",
}

_ATTRS = [
    "AXRole", "AXTitle", "AXDescription", "AXValue", "AXIdentifier",
    "AXFrame", "AXEnabled", "AXFocused", "AXChildren",
]


class MacOSBackend(DeviceBackend):
    """Controls macOS desktop apps via Accessibility API + CGEvent."""

    platform = "macos"

    def __init__(self, screenshot: bool = True, max_depth: int = 8):
        if ax is None:
            raise BackendError("pyobjc frameworks unavailable (macOS required)")
        self._screenshot_enabled = screenshot
        self._max_depth = max_depth
        self._screen = AppKit.NSScreen.mainScreen().frame()
        self._sw = float(self._screen.size.width)
        self._sh = float(self._screen.size.height)
        if not self._check_permission():
            raise PermissionError_(
                "Accessibility permission missing. Grant it in "
                "System Settings > Privacy & Security > Accessibility."
            )

    # -- helpers -------------------------------------------------------------

    def _check_permission(self) -> bool:
        return bool(ax.AXIsProcessTrusted())

    def _norm(self, x: float, y: float) -> Point:
        return Point(round(x / self._sw * 1000, 2), round(y / self._sh * 1000, 2))

    def _native(self, p: Point) -> tuple[float, float]:
        return (p.x / 1000 * self._sw, p.y / 1000 * self._sh)

    def _ax_rect(self, value) -> Optional[Rect]:
        """Extract a Rect from an AXFrame value (AXValue wrapper or CGRect)."""
        if value is None:
            return None
        try:
            if hasattr(value, "origin"):  # CGRect
                return Rect(value.origin.x, value.origin.y,
                            value.size.width, value.size.height)
        except Exception:
            pass
        try:  # AXValue wrapped
            err, r = ax.AXValueGetValue(value, ax.kAXValueCGRectType, None)
            if err == 0 and hasattr(r, "origin"):
                return Rect(r.origin.x, r.origin.y, r.size.width, r.size.height)
        except Exception:
            pass
        return None

    def _get(self, el, attr):
        err, v = ax.AXUIElementCopyAttributeValue(el, attr, None)
        return v if err == 0 else None

    def _ax_point(self, value):
        try:
            err, p = ax.AXValueGetValue(value, ax.kAXValueCGPointType, None)
            if err == 0 and hasattr(p, "x"):
                return (p.x, p.y)
        except Exception:
            pass
        return None

    def _ax_size(self, value):
        try:
            err, s = ax.AXValueGetValue(value, ax.kAXValueCGSizeType, None)
            if err == 0 and hasattr(s, "width"):
                return (s.width, s.height)
        except Exception:
            pass
        return None

    def _element_center(self, el):
        """Best-effort center point of an element (frame -> pos+size -> None)."""
        frame = self._ax_rect(self._get(el, "AXFrame"))
        if frame:
            return (frame.x + frame.w / 2, frame.y + frame.h / 2)
        pos = self._ax_point(self._get(el, "AXPosition"))
        size = self._ax_size(self._get(el, "AXSize"))
        if pos and size:
            return (pos[0] + size[0] / 2, pos[1] + size[1] / 2)
        return None

    def _role(self, el) -> str:
        r = self._get(el, "AXRole")
        return _ROLE_MAP.get(str(r), "other") if r else "other"

    def _ref(self, el, role: str, counter: dict) -> str:
        ident = self._get(el, "AXIdentifier")
        if ident:
            return f"axid:{ident}"
        counter[role] = counter.get(role, 0) + 1
        return f"{role}#{counter[role]}"

    def _text(self, el) -> str:
        for attr in ("AXTitle", "AXDescription", "AXValue"):
            v = self._get(el, attr)
            if v and str(v).strip():
                return str(v)
        return ""

    def _frontmost_app(self):
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()

    # -- observation ---------------------------------------------------------

    def perceive(self) -> ScreenState:
        if not self._check_permission():
            raise PermissionError_("Accessibility permission was revoked.")
        app = self._frontmost_app()
        pid = app.processIdentifier()
        app_ax = ax.AXUIElementCreateApplication(pid)
        tree = self._walk(app_ax, 0, {}, None)
        state = ScreenState(
            tree=tree,
            app=str(app.bundleIdentifier() or app.localizedName() or ""),
            platform=self.platform,
        )
        if self._screenshot_enabled:
            path = "/tmp/control_everything_shot.png"
            subprocess.run(
                ["screencapture", "-x", path], check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                from PIL import Image
                state.screenshot = Image.open(path)
                state.screenshot_path = path
            except Exception:
                pass
        return state

    def _walk(self, el, depth: int, counter: dict, parent_ref: str) -> Element:
        if depth > self._max_depth or el is None:
            return Element(ref="", role="other", meta={"skipped": True})
        role = self._role(el)
        ref = self._ref(el, role, counter)
        bounds = self._ax_rect(self._get(el, "AXFrame"))
        norm_bounds = None
        if bounds:
            norm_bounds = Rect(
                round(bounds.x / self._sw * 1000, 2),
                round(bounds.y / self._sh * 1000, 2),
                round(bounds.w / self._sw * 1000, 2),
                round(bounds.h / self._sh * 1000, 2),
            )
        node = Element(
            ref=ref,
            role=role,
            text=self._text(el),
            bounds=norm_bounds,
            enabled=bool(self._get(el, "AXEnabled") if self._get(el, "AXEnabled") is not None else True),
            focused=bool(self._get(el, "AXFocused") or False),
            meta={"ax_role": role},
        )
        children = self._get(el, "AXChildren")
        if children:
            for c in children:
                child = self._walk(c, depth + 1, counter, ref)
                if child.ref:
                    node.children.append(child)
        return node

    def is_app_running(self, app_id: str) -> bool:
        """True if an app with this bundle id / name is in the running list."""
        apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
        for a in apps:
            bid = a.bundleIdentifier() or ""
            name = a.localizedName() or ""
            if app_id in (bid, name) or bid == app_id or name == app_id:
                return True
        return False

    # -- element resolution --------------------------------------------------

    def _find_text_field(self):
        """Locate a text-input element, preferring the MAIN window's subtree.

        Safari can have several windows; typing into a non-main window's
        address bar does not navigate what the user sees."""
        app = self._frontmost_app()
        app_ax = ax.AXUIElementCreateApplication(app.processIdentifier())
        _, wins = ax.AXUIElementCopyAttributeValue(app_ax, "AXWindows", None)
        windows = list(wins or [])
        main = None
        for w in windows:
            _, is_main = ax.AXUIElementCopyAttributeValue(w, "AXMain", None)
            if is_main:
                main = w
                break
        ordered = ([main] + [w for w in windows if w is not main]) if main else windows

        for win in ordered:
            target = {"found": None}

            def visit(el, depth, counter):
                if target["found"] is not None or depth > self._max_depth:
                    return
                role = str(self._get(el, "AXRole") or "")
                if role in ("AXTextField", "AXSearchField", "AXComboBox"):
                    target["found"] = el
                    return
                children = self._get(el, "AXChildren")
                if children:
                    for c in children:
                        visit(c, depth + 1, counter)

            visit(win, 0, {})
            if target["found"]:
                return target["found"]
        return None

    def _find_ax(self, ref: str):
        """Locate a live AXUIElement by our ref (re-walk; refs are snapshot-local)."""
        app = self._frontmost_app()
        app_ax = ax.AXUIElementCreateApplication(app.processIdentifier())
        target = {"found": None}

        def visit(el, depth, counter):
            if target["found"] is not None or depth > self._max_depth:
                return
            role = self._role(el)
            if self._ref(el, role, counter) == ref:
                target["found"] = el
                return
            children = self._get(el, "AXChildren")
            if children:
                for c in children:
                    visit(c, depth + 1, counter)

        visit(app_ax, 0, {})
        if target["found"] is None:
            raise ElementNotFoundError(f"element ref not found in current snapshot: {ref}")
        return target["found"]

    def _resolve_pos(self, action: Action):
        """Element ref first, then normalized coordinates."""
        if action.target:
            el = self._find_ax(action.target)
            bounds = self._ax_rect(self._get(el, "AXFrame"))
            if bounds:
                return (bounds.x + bounds.w / 2, bounds.y + bounds.h / 2), el
            raise ElementNotFoundError(f"no frame for element {action.target}")
        if action.pos:
            return self._native(action.pos), None
        raise BackendError(f"action {action.kind} needs target or pos")

    # -- execution -----------------------------------------------------------

    def act(self, action: Action) -> ActionResult:
        try:
            return self._act(action)
        except ActionNotSupportedError as e:
            return ActionResult(False, action, error=str(e))
        except ElementNotFoundError as e:
            return ActionResult(False, action, error=str(e))
        except Exception as e:  # pragma: no cover - defensive
            return ActionResult(False, action, error=f"{type(e).__name__}: {e}")

    def _act(self, action: Action) -> ActionResult:
        kind = action.kind
        if kind == "wait":
            time.sleep(max(0.0, action.duration_s))
            return ActionResult(True, action, detail=f"waited {action.duration_s}s", method="sleep")
        if kind == "open_app":
            name = action.text or action.target or ""
            # bundle ids (com.apple.calculator) need `open -b`; app names need `open -a`
            if "." in name and not name.endswith(".app"):
                subprocess.run(["open", "-b", name], check=False)
                detail = f"launched bundle {name}"
            else:
                subprocess.run(["open", "-a", name], check=False)
                detail = f"launched {name}"
            self._activate_app(name)
            return ActionResult(True, action, detail=detail + " + activated", method="open")
        if kind in ("back", "home", "app_switch"):
            return ActionResult(True, action, detail=f"{kind} is a no-op on macOS", method="noop")
        if kind == "copy":
            subprocess.run(["pbcopy"], check=False, input=action.text or "", text=True)
            return ActionResult(True, action, detail="copied to clipboard", method="pbcopy")
        if kind == "paste":
            out = subprocess.run(["pbpaste"], check=False, capture_output=True, text=True)
            return ActionResult(True, action, detail=f"paste ({out.stdout[:40]!r})", method="pbpaste")

        if kind == "tap":
            return self._tap(action)
        if kind == "type":
            return self._type(action)
        if kind == "key":
            return self._key(action)
        if kind == "shortcut":  # tolerate LLM emitting shortcut for key combos
            return self._key(action)
        if kind == "scroll":
            return self._scroll(action)
        if kind == "swipe":
            return self._swipe(action)
        if kind in ("long_press", "pinch"):
            raise ActionNotSupportedError(f"{kind} is not supported on macOS")
        if kind == "done":
            return ActionResult(True, action, detail="done", method="none")
        raise ActionNotSupportedError(f"unhandled action kind: {kind}")

    def _tap(self, action: Action) -> ActionResult:
        """Semantic press first (no coordinates needed), coordinates as fallback."""
        if action.target:
            el = self._find_ax(action.target)
            err = ax.AXUIElementPerformAction(el, ax.kAXPressAction)
            if err == 0:
                return ActionResult(True, action, detail=f"pressed {action.target}", method="ax-press")
            center = self._element_center(el)
            if center:
                return self._cg_click(center, action)
            raise ElementNotFoundError(f"no frame/position for element {action.target}")
        if action.pos:
            return self._cg_click(self._native(action.pos), action)
        raise BackendError("tap needs target or pos")

    def _cg_click(self, pos: tuple[float, float], action: Action) -> ActionResult:
        pt = Quartz.CGPointMake(pos[0], pos[1])
        for evt_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            evt = Quartz.CGEventCreateMouseEvent(None, evt_type, pt, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        return ActionResult(True, action, detail=f"cg-click at {pos}", method="cg-click")

    def _focus_for_input(self, el) -> bool:
        """Mouse-click an element to give it focus before typing.

        Measured on Safari: a real mouse click makes setValue + Enter
        navigation reliable, while synthetic Cmd+L focus does not always.
        """
        center = self._element_center(el)
        if center:
            self._cg_click(center, Action(kind="tap", note="focus"))
            return True
        # Safari's address bar exposes no frame: click the address-bar area
        # of the main window (upper-center) as a fallback.
        app = self._frontmost_app()
        app_ax = ax.AXUIElementCreateApplication(app.processIdentifier())
        _, wins = ax.AXUIElementCopyAttributeValue(app_ax, "AXWindows", None)
        for w in (wins or []):
            _, is_main = ax.AXUIElementCopyAttributeValue(w, "AXMain", None)
            if is_main:
                rect = self._ax_rect(self._get(w, "AXFrame"))
                if rect:
                    self._cg_click((rect.x + rect.w * 0.45, rect.y + 40),
                                   Action(kind="tap", note="focus-address-bar"))
                    return True
        return False

    def _type(self, action: Action) -> ActionResult:
        text = action.text or ""
        el = None
        if action.target:
            try:
                el = self._find_ax(action.target)
            except ElementNotFoundError:
                el = None
        if el is None:
            # Auto-locate the address/search field: direct setValue is far more
            # reliable than synthesized keyboard events into the focused app.
            el = self._find_text_field()
        if el is not None:
            self._focus_for_input(el)
            err = ax.AXUIElementSetAttributeValue(el, "AXValue", text)
            if err == 0:
                return ActionResult(True, action,
                                    detail=f"set AXValue on text field ({text[:30]!r})",
                                    method="ax-value")
            # fall through to keyboard
        # CGEvent unicode keyboard entry, delivered to the target app directly
        for ch in text:
            evt_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(evt_down, 1, ch)
            self._post_event(evt_down)
            self._post_event(Quartz.CGEventCreateKeyboardEvent(None, 0, False))
        return ActionResult(True, action, detail=f"typed {len(text)} chars", method="cg-keyboard-unicode")

    def _post_event(self, evt) -> None:
        """Post a CGEvent to the global HID tap.

        Measured on Safari: CGEventPostToPid keyboard events are ignored, but
        HID-tap events work once the target app is OS-frontmost (open_app now
        activates the app via NSWorkspace)."""
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)

    def _activate_app(self, app_id: str) -> bool:
        """Bring an app to the OS front (makes keyboard events land)."""
        ws = AppKit.NSWorkspace.sharedWorkspace()
        for a in ws.runningApplications():
            bid = a.bundleIdentifier() or ""
            name = a.localizedName() or ""
            if app_id in (bid, name):
                a.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
                return True
        return False

    def _key(self, action: Action) -> ActionResult:
        from backends._mac_keys import KEYCODES, MODIFIER_FLAGS
        key = (action.key or "").lower()
        if key not in KEYCODES:
            raise BackendError(f"unknown key: {key}")
        flags = 0
        for m in action.modifiers:
            flags |= MODIFIER_FLAGS.get(m.lower(), 0)
        kc = KEYCODES[key]
        evt_down = Quartz.CGEventCreateKeyboardEvent(None, kc, True)
        Quartz.CGEventSetFlags(evt_down, flags)
        self._post_event(evt_down)
        evt_up = Quartz.CGEventCreateKeyboardEvent(None, kc, False)
        Quartz.CGEventSetFlags(evt_up, flags)
        self._post_event(evt_up)
        return ActionResult(True, action, detail=f"key {key} -> pid", method="cg-keyboard-virtual-key")

    def _scroll(self, action: Action) -> ActionResult:
        dir_map = {"down": -1.0, "up": 1.0, "left": 1.0, "right": -1.0}
        val = dir_map.get((action.dir or "down").lower(), -1.0)
        pos, _ = self._resolve_pos(action) if (action.target or action.pos) else ((self._sw/2, self._sh/2), None)
        evt = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 1, int(val * 3))
        Quartz.CGEventSetLocation(evt, Quartz.CGPointMake(pos[0], pos[1]))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        return ActionResult(True, action, detail=f"scroll {action.dir}", method="cg-scroll-wheel")

    def _swipe(self, action: Action) -> ActionResult:
        if not action.pos or not action.to:
            raise BackendError("swipe needs pos and to")
        src = self._native(action.pos)
        dst = self._native(action.to)
        evt = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown,
            Quartz.CGPointMake(src[0], src[1]), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        steps = 10
        for i in range(1, steps + 1):
            x = src[0] + (dst[0] - src[0]) * i / steps
            y = src[1] + (dst[1] - src[1]) * i / steps
            evt = Quartz.CGEventCreateMouseEvent(
                None, Quartz.kCGEventLeftMouseDragged,
                Quartz.CGPointMake(x, y), Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
            time.sleep(0.01)
        evt = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp,
            Quartz.CGPointMake(dst[0], dst[1]), Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        return ActionResult(True, action, detail="swipe executed", method="cg-drag")
