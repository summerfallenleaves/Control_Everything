"""macOS 后端：可访问性 API（pyobjc）+ CoreGraphics 事件。

已在 macOS 26.5.2 上对 Safari / TextEdit 实测验证
（见 docs/macos-accessibility-research.md）：

- AX 树遍历与元素坐标：可用
- AXValue 文本输入（含中文）：可用
- screencapture 截图：可用（已授予屏幕录制权限）

策略（三层混合）：
  1. AX 语义动作（AXPress / set AXValue）—— 首选，稳定
  2. CGEvent 坐标兜底（自绘 / WebView 控件）
  3. 截图 + 视觉（不在本模块；经 perceive().screenshot 暴露）
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

try:  # 仅 macOS；导入错误会在构造时暴露
    import ApplicationServices as ax
    import AppKit
    import Quartz
except ImportError:  # pragma: no cover - 非 macOS
    ax = AppKit = Quartz = None

# AX 角色 -> 归一化角色
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
    """通过可访问性 API + CGEvent 控制 macOS 桌面应用。"""

    platform = "macos"

    def __init__(self, screenshot: bool = True, max_depth: int = 8):
        if ax is None:
            raise BackendError("pyobjc 框架不可用（需要 macOS）")
        self._screenshot_enabled = screenshot
        self._max_depth = max_depth
        self._screen = AppKit.NSScreen.mainScreen().frame()
        self._sw = float(self._screen.size.width)
        self._sh = float(self._screen.size.height)
        if not self._check_permission():
            raise PermissionError_(
                "缺少辅助功能权限。请在「系统设置 > 隐私与安全性 > 辅助功能」中授权。"
            )

    # -- 辅助 ---------------------------------------------------------------

    def _check_permission(self) -> bool:
        return bool(ax.AXIsProcessTrusted())

    def _norm(self, x: float, y: float) -> Point:
        return Point(round(x / self._sw * 1000, 2), round(y / self._sh * 1000, 2))

    def _native(self, p: Point) -> tuple[float, float]:
        return (p.x / 1000 * self._sw, p.y / 1000 * self._sh)

    def _ax_rect(self, value) -> Optional[Rect]:
        """从 AXFrame 值提取 Rect（AXValue 包装或 CGRect）。"""
        if value is None:
            return None
        try:
            if hasattr(value, "origin"):  # CGRect
                return Rect(value.origin.x, value.origin.y,
                            value.size.width, value.size.height)
        except Exception:
            pass
        try:  # AXValue 包装
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
        """尽力获取元素中心点（frame -> pos+size -> None）。"""
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
            return f'axid:{ident}'
        counter[role] = counter.get(role, 0) + 1
        return f'{role}#{counter[role]}'

    def _text(self, el) -> str:
        for attr in ("AXTitle", "AXDescription", "AXValue"):
            v = self._get(el, attr)
            if v and str(v).strip():
                return str(v)
        return ""

    def _frontmost_app(self):
        return AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()

    # -- 观察 ---------------------------------------------------------------

    def perceive(self) -> ScreenState:
        if not self._check_permission():
            raise PermissionError_("辅助功能权限被撤销。")
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
        """带该 bundle id / 名称的应用是否在运行列表中。"""
        apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
        for a in apps:
            bid = a.bundleIdentifier() or ""
            name = a.localizedName() or ""
            if app_id in (bid, name) or bid == app_id or name == app_id:
                return True
        return False

    # -- 元素定位 ------------------------------------------------------------

    def _find_text_field(self):
        """定位文本输入元素，优先 MAIN（主）窗口的子树。

        Safari 可能有多个窗口；把文字输进非主窗口的地址栏
        不会导航用户眼前的内容。"""
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
        """按我们的 ref 定位活的 AXUIElement（重新遍历；ref 只在本轮快照有效）。

        容错匹配：LLM 有时会把整行 UI 树粘贴过来
        （"axid:X role=text_field text='...'"）而不是只用 ref。
        我们先精确匹配 ref，失败再试它按空白分割的第一个 token。
        """
        app = self._frontmost_app()
        app_ax = ax.AXUIElementCreateApplication(app.processIdentifier())

        def walk_for(candidate: str):
            target = {"found": None}

            def visit(el, depth, counter):
                if target["found"] is not None or depth > self._max_depth:
                    return
                role = self._role(el)
                if self._ref(el, role, counter) == candidate:
                    target["found"] = el
                    return
                children = self._get(el, "AXChildren")
                if children:
                    for c in children:
                        visit(c, depth + 1, counter)

            visit(app_ax, 0, {})
            return target["found"]

        found = walk_for(ref)
        if found is None and ref:
            first_token = ref.split()[0]
            if first_token != ref:
                found = walk_for(first_token)
        if found is None:
            raise ElementNotFoundError(f'当前快照中找不到元素 ref: {ref}')
        return found

    def _resolve_pos(self, action: Action):
        """优先元素 ref，其次归一化坐标。"""
        if action.target:
            el = self._find_ax(action.target)
            bounds = self._ax_rect(self._get(el, "AXFrame"))
            if bounds:
                return (bounds.x + bounds.w / 2, bounds.y + bounds.h / 2), el
            raise ElementNotFoundError(f'元素没有 frame: {action.target}')
        if action.pos:
            return self._native(action.pos), None
        raise BackendError(f'动作 {action.kind} 需要 target 或 pos')

    # -- 执行 ---------------------------------------------------------------

    def act(self, action: Action) -> ActionResult:
        try:
            return self._act(action)
        except ActionNotSupportedError as e:
            return ActionResult(False, action, error=str(e))
        except ElementNotFoundError as e:
            return ActionResult(False, action, error=str(e))
        except Exception as e:  # pragma: no cover - 防御
            return ActionResult(False, action, error=f'{type(e).__name__}: {e}')

    def _act(self, action: Action) -> ActionResult:
        kind = action.kind
        if kind == "wait":
            time.sleep(max(0.0, action.duration_s))
            return ActionResult(True, action, detail=f"等待了 {action.duration_s}s", method="sleep")
        if kind == "open_app":
            name = action.text or action.target or ""
            # bundle id（com.apple.calculator）用 `open -b`；应用名用 `open -a`
            if "." in name and not name.endswith(".app"):
                subprocess.run(["open", "-b", name], check=False)
                detail = f'启动了 bundle {name}'
            else:
                subprocess.run(["open", "-a", name], check=False)
                detail = f'启动了 {name}'
            self._activate_app(name)
            return ActionResult(True, action, detail=detail + " + 已激活", method="open")
        if kind in ("back", "home", "app_switch"):
            return ActionResult(True, action, detail=f"{kind} 在 macOS 上是空操作", method="noop")
        if kind == "copy":
            subprocess.run(["pbcopy"], check=False, input=action.text or "", text=True)
            return ActionResult(True, action, detail="已复制到剪贴板", method="pbcopy")
        if kind == "paste":
            out = subprocess.run(["pbpaste"], check=False, capture_output=True, text=True)
            return ActionResult(True, action, detail=f"粘贴 ({out.stdout[:40]!r})", method="pbpaste")

        if kind == "tap":
            return self._tap(action)
        if kind == "type":
            return self._type(action)
        if kind == "key":
            return self._key(action)
        if kind == "shortcut":  # 容忍 LLM 用 shortcut 表示组合键
            return self._key(action)
        if kind == "scroll":
            return self._scroll(action)
        if kind == "swipe":
            return self._swipe(action)
        if kind in ("long_press", "pinch"):
            raise ActionNotSupportedError(f'{kind} 在 macOS 上不支持')
        if kind == "done":
            return ActionResult(True, action, detail="完成", method="none")
        raise ActionNotSupportedError(f'未处理的动作类型: {kind}')

    def _tap(self, action: Action) -> ActionResult:
        """语义按压优先（无需坐标），坐标兜底。

        兜底顺序：AXPress -> 元素中心坐标 -> LLM 提供的 pos 坐标。
        LLM 经常同时给出 target 和 pos；target 失败时不应丢弃 pos。
        """
        if action.target:
            try:
                el = self._find_ax(action.target)
                err = ax.AXUIElementPerformAction(el, ax.kAXPressAction)
                if err == 0:
                    return ActionResult(True, action, detail=f'按压了 {action.target}', method='ax-press')
                center = self._element_center(el)
                if center:
                    return self._cg_click(center, action)
            except ElementNotFoundError:
                pass  # 落到坐标兜底
            if action.pos:
                return self._cg_click(self._native(action.pos), action)
            raise ElementNotFoundError(f'元素没有 frame/位置: {action.target}')
        if action.pos:
            return self._cg_click(self._native(action.pos), action)
        raise BackendError("tap 需要 target 或 pos")

    def _cg_click(self, pos: tuple[float, float], action: Action) -> ActionResult:
        pt = Quartz.CGPointMake(pos[0], pos[1])
        for evt_type in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            evt = Quartz.CGEventCreateMouseEvent(None, evt_type, pt, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        return ActionResult(True, action, detail=f'cg-click 于 {pos}', method='cg-click')

    def _focus_for_input(self, el) -> bool:
        """输入前用鼠标点击元素使其获得焦点。

        Safari 实测：真实鼠标点击能让 setValue + 回车导航可靠生效，
        而合成 Cmd+L 聚焦并不总是有效。"""
        center = self._element_center(el)
        if center:
            self._cg_click(center, Action(kind="tap", note="focus"))
            return True
        # Safari 地址栏不暴露 frame：兜底点击主窗口的地址栏区域（上部中央）。
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
            # 自动定位地址栏/搜索框：直接 setValue 远比
            # 向聚焦应用合成键盘事件可靠。
            el = self._find_text_field()
        if el is not None:
            self._focus_for_input(el)
            err = ax.AXUIElementSetAttributeValue(el, "AXValue", text)
            if err == 0:
                return ActionResult(True, action,
                                    detail=f'已在文本框中设置 AXValue ({text[:30]!r})',
                                    method="ax-value")
            # 落到键盘输入
        # CGEvent unicode 键盘输入，直接送达目标应用
        for ch in text:
            evt_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(evt_down, 1, ch)
            self._post_event(evt_down)
            self._post_event(Quartz.CGEventCreateKeyboardEvent(None, 0, False))
        return ActionResult(True, action, detail=f'输入了 {len(text)} 个字符', method='cg-keyboard-unicode')

    def _post_event(self, evt) -> None:
        """把 CGEvent 发布到全局 HID tap。

        Safari 实测：CGEventPostToPid 的键盘事件会被忽略，
        但只要目标应用是 OS 前台（open_app 现在会经 NSWorkspace 激活应用），
        HID-tap 事件就有效。"""
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)

    def _activate_app(self, app_id: str) -> bool:
        """把应用带到 OS 前台（让键盘事件落地）。"""
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
            raise BackendError(f'未知按键: {key}')
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
        return ActionResult(True, action, detail=f'按键 {key} -> pid', method='cg-keyboard-virtual-key')

    def _scroll(self, action: Action) -> ActionResult:
        dir_map = {"down": -1.0, "up": 1.0, "left": 1.0, "right": -1.0}
        val = dir_map.get((action.dir or "down").lower(), -1.0)
        pos, _ = self._resolve_pos(action) if (action.target or action.pos) else ((self._sw/2, self._sh/2), None)
        evt = Quartz.CGEventCreateScrollWheelEvent(
            None, Quartz.kCGScrollEventUnitLine, 1, int(val * 3))
        Quartz.CGEventSetLocation(evt, Quartz.CGPointMake(pos[0], pos[1]))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
        return ActionResult(True, action, detail=f'滚动 {action.dir}', method='cg-scroll-wheel')

    def _swipe(self, action: Action) -> ActionResult:
        if not action.pos or not action.to:
            raise BackendError("swipe 需要 pos 和 to")
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
        return ActionResult(True, action, detail="swipe 已执行", method="cg-drag")
