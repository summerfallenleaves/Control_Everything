"""Platform-agnostic data model for Control_Everything.

All backends (macOS / Android / iOS) translate their native UI representation
into these types. The orchestrator and LLM only ever see this model, never
platform-specific concepts like AXFrame or resource-id.

Coordinates are normalized to a 0-1000 space so screenshots and element bounds
are comparable across wildly different resolutions (macOS 2560x1440 vs a phone
1080x2400).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Geometry (normalized 0-1000 space)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    x: float  # left
    y: float  # top
    w: float
    h: float

    @property
    def center(self) -> Point:
        return Point(self.x + self.w / 2, self.y + self.h / 2)

    def contains(self, p: Point) -> bool:
        return self.x <= p.x <= self.x + self.w and self.y <= p.y <= self.y + self.h


# ---------------------------------------------------------------------------
# Element tree (the single intermediate representation)
# ---------------------------------------------------------------------------

# Normalized element roles across platforms.
ElementRole = Literal[
    "window", "button", "text_field", "text", "image", "tab", "checkbox",
    "radio", "menu", "menu_item", "list", "link", "dialog", "scroll_area",
    "group", "table", "cell", "switch", "slider", "other",
]


@dataclass
class Element:
    """One UI node in the accessibility tree.

    ref is the stable platform anchor used to re-locate the element across
    snapshots (AXIdentifier on macOS, resource-id on Android, identifier on
    iOS). Falls back to (role, text, nth) paths inside each backend when the
    platform exposes no identifier.
    """

    ref: str
    role: ElementRole
    text: str = ""
    bounds: Optional[Rect] = None
    children: list["Element"] = field(default_factory=list)
    enabled: bool = True
    focused: bool = False
    meta: dict[str, Any] = field(default_factory=dict)  # platform raw info

    def flatten(self) -> list["Element"]:
        """Pre-order walk of the subtree."""
        out: list[Element] = [self]
        for c in self.children:
            out.extend(c.flatten())
        return out

    def find(self, *, role: str | None = None, text: str | None = None,
             ref: str | None = None) -> list["Element"]:
        return [e for e in self.flatten()
                if (role is None or e.role == role)
                and (text is None or text in e.text)
                and (ref is None or e.ref == ref)]


@dataclass
class ScreenState:
    """Full observable state of the device at one moment."""

    tree: Element
    screenshot: Optional[Any] = None  # PIL Image when available
    screenshot_path: Optional[str] = None
    app: str = ""            # bundle id / package name / app name
    platform: str = ""       # "macos" | "android" | "ios"
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Action space (what the LLM may emit; every backend implements these)
# ---------------------------------------------------------------------------

ActionKind = Literal[
    "tap",            # semantic click on an element (or pos)
    "type",           # enter text into the focused/text-field element
    "swipe",          # gesture drag from a to b
    "scroll",         # scroll a scroll area (dir: up/down/left/right)
    "key",            # press a key / shortcut (name, modifiers)
    "open_app",       # launch an application (id)
    "back",           # platform back navigation (no-op on macOS)
    "home",           # go to platform home (no-op on macOS)
    "app_switch",     # switch between recent apps (no-op on macOS)
    "wait",           # wait N seconds (e.g. for async content)
    "copy",           # copy selected/clipboard content
    "paste",          # paste clipboard content
    "long_press",     # gesture reserved for mobile (unsupported on macOS)
    "pinch",          # gesture reserved for mobile
    "done",           # agent declares the task finished
]


@dataclass
class Action:
    kind: ActionKind
    target: str | None = None   # element ref; resolved by the backend
    pos: Point | None = None    # normalized coordinate fallback
    text: str | None = None     # for type
    dir: str | None = None      # for scroll: up/down/left/right
    key: str | None = None      # for key: e.g. "return", "v"
    modifiers: list[str] = field(default_factory=list)  # command/option/...
    duration_s: float = 0.5     # for wait
    to: Point | None = None     # for swipe
    note: str = ""              # human/LLM reasoning, ignored by backends

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        for f in ("target", "text", "dir", "key", "duration_s", "note"):
            v = getattr(self, f)
            if v:
                d[f] = v
        if self.pos:
            d["pos"] = {"x": round(self.pos.x, 2), "y": round(self.pos.y, 2)}
        if self.to:
            d["to"] = {"x": round(self.to.x, 2), "y": round(self.to.y, 2)}
        if self.modifiers:
            d["modifiers"] = self.modifiers
        return d


@dataclass
class ActionResult:
    ok: bool
    action: Action
    detail: str = ""
    method: str = ""        # which underlying mechanism ran (ax-press, cg-click...)
    error: str | None = None
