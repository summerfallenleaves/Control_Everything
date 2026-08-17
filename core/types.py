"""Control_Everything 的平台无关数据模型。

所有后端（macOS / Android / iOS）都把各自原生的 UI 表示翻译成这些类型。
orchestrator 与 LLM 只见到本模型，永远接触不到平台专属概念
（如 AXFrame、resource-id）。

坐标统一归一化到 0-1000 空间，使截图与元素边界在差异巨大的分辨率之间
（macOS 2560x1440 vs 手机 1080x2400）可以互相比较。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# 几何（归一化 0-1000 空间）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    x: float  # 左边距
    y: float  # 上边距
    w: float
    h: float

    @property
    def center(self) -> Point:
        return Point(self.x + self.w / 2, self.y + self.h / 2)

    def contains(self, p: Point) -> bool:
        return self.x <= p.x <= self.x + self.w and self.y <= p.y <= self.y + self.h


# ---------------------------------------------------------------------------
# 元素树（唯一的中间表示）
# ---------------------------------------------------------------------------

# 跨平台归一化的元素角色。
ElementRole = Literal[
    "window", "button", "text_field", "text", "image", "tab", "checkbox",
    "radio", "menu", "menu_item", "list", "link", "dialog", "scroll_area",
    "group", "table", "cell", "switch", "slider", "other",
]


@dataclass
class Element:
    """可访问性树中的一个 UI 节点。

    ref 是跨快照重定位元素的稳定平台锚点
    （macOS 的 AXIdentifier、Android 的 resource-id、iOS 的 identifier）。
    当平台不暴露标识符时，各后端回退到 (role, text, nth) 路径。
    """

    ref: str
    role: ElementRole
    text: str = ""
    bounds: Optional[Rect] = None
    children: list["Element"] = field(default_factory=list)
    enabled: bool = True
    focused: bool = False
    meta: dict[str, Any] = field(default_factory=dict)  # 平台原始信息

    def flatten(self) -> list["Element"]:
        """前序遍历子树。"""
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
    """设备某一时刻的完整可观察状态。"""

    tree: Element
    screenshot: Optional[Any] = None  # PIL Image（可用时）
    screenshot_path: Optional[str] = None
    app: str = ""            # bundle id / 包名 / 应用名
    platform: str = ""       # "macos" | "android" | "ios"
    meta: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 动作空间（LLM 可以输出的动作；每个后端都要实现它们）
# ---------------------------------------------------------------------------

ActionKind = Literal[
    "tap",            # 语义点击元素（或按坐标）
    "type",           # 向聚焦的文本输入框输入文字
    "swipe",          # 从 a 拖到 b 的手势
    "scroll",         # 滚动滚动区域（dir: up/down/left/right）
    "key",            # 按键/快捷键（名称、修饰键）
    "open_app",       # 启动应用（标识）
    "set_address_bar",  # 浏览器地址栏导航：聚焦地址栏 -> 输入 URL -> 回车（一步完成）
    "new_tab",        # 浏览器新建标签页（不影响已有标签页）
    "back",           # 平台返回导航（macOS 上为空操作）
    "home",           # 回到平台主页（macOS 上为空操作）
    "app_switch",     # 切换最近应用（macOS 上为空操作）
    "wait",           # 等待 N 秒（如等待异步内容）
    "copy",           # 复制选中内容/剪贴板
    "paste",          # 粘贴剪贴板内容
    "long_press",     # 移动端手势（macOS 不支持）
    "pinch",          # 移动端手势
    "done",           # Agent 宣告任务完成
    "ask_user",       # 向用户提问（如需要人工登录/确认），text=问题
]


@dataclass
class Action:
    kind: ActionKind
    target: str | None = None   # 元素 ref；由后端解析
    pos: Point | None = None    # 归一化坐标兜底
    text: str | None = None     # type 用
    dir: str | None = None      # scroll 用：up/down/left/right
    key: str | None = None      # key 用：如 "return"、"v"
    modifiers: list[str] = field(default_factory=list)  # command/option/...
    duration_s: float = 0.5     # wait 用
    to: Point | None = None     # swipe 用
    note: str = ""              # 人/LLM 的推理说明，后端忽略

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
    method: str = ""        # 实际执行的底层机制（ax-press、cg-click……）
    error: str | None = None


@dataclass
class Decision:
    """LLM 在某一步的决定。

    宽松（auto）tool_choice 意味着模型可能以纯文本回应
    （一个观察、一个等待请求、一个计划）而不是动作。
    orchestrator 记录文本并继续循环；只对 action 执行。
    """

    action: Action | None = None
    text: str = ""

    @property
    def is_action(self) -> bool:
        return self.action is not None
