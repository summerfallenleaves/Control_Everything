"""环境恢复工具：把 macOS 环境重置到干净的测试起点。

用于多次运行基准测试/重复试验之间的一致性恢复，避免上一轮
任务残留的状态（导航到的页面、打开的应用等）污染下一轮结果：

  1. 清理测试残留应用（计算器、文本编辑）
  2. 激活 Safari 到前台
  3. 把主窗口导航到 about:blank（带验证与 3 次重试）

用法：
  uv run python tools/restore_env.py
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ApplicationServices as ax
import AppKit
import Quartz


def cleanup_test_apps() -> None:
    """清理测试过程中可能残留的应用。"""
    for app in ("Calculator", "TextEdit"):
        subprocess.run(["pkill", "-x", app], check=False)


def activate_safari() -> bool:
    """把 Safari 激活到 OS 前台，返回是否成功。"""
    ws = AppKit.NSWorkspace.sharedWorkspace()
    for a in ws.runningApplications():
        if a.bundleIdentifier() == "com.apple.Safari":
            a.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
            return True
    return False


def find_address(el, depth: int = 0):
    if depth > 7:
        return None
    _, ident = ax.AXUIElementCopyAttributeValue(el, "AXIdentifier", None)
    if ident and "ADDRESS_AND_SEARCH" in str(ident):
        return el
    _, children = ax.AXUIElementCopyAttributeValue(el, "AXChildren", None)
    if children:
        for c in children:
            r = find_address(c, depth + 1)
            if r:
                return r
    return None


def main_window(safari_ax):
    _, wins = ax.AXUIElementCopyAttributeValue(safari_ax, "AXWindows", None)
    for w in wins or []:
        _, is_main = ax.AXUIElementCopyAttributeValue(w, "AXMain", None)
        if is_main:
            return w
    return (wins or [None])[0]


def window_title(w):
    _, t = ax.AXUIElementCopyAttributeValue(w, "AXTitle", None)
    return str(t) if t else ""


def navigate_to_blank(safari_ax) -> bool:
    """把主窗口导航到 about:blank；带聚焦验证与 3 次重试。"""
    for attempt in range(1, 4):
        w0 = main_window(safari_ax)
        if w0 is None:
            return False
        title = window_title(w0)
        if title and "DeepSeek" not in title:
            print(f"第{attempt}次检查：当前标题 {title!r}，已非目标页")
            return True
        # 点击地址栏区域（窗口上部中央）
        _, fv = ax.AXUIElementCopyAttributeValue(w0, "AXFrame", None)
        ok, rect = ax.AXValueGetValue(fv, ax.kAXValueCGRectType, None)
        cx = rect.origin.x + rect.size.width * 0.45
        cy = rect.origin.y + 40
        pt = Quartz.CGPointMake(cx, cy)
        for t in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
            e = Quartz.CGEventCreateMouseEvent(None, t, pt, Quartz.kCGMouseButtonLeft)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)
        time.sleep(0.6)
        ab = find_address(w0)
        if ab is None:
            print(f"第{attempt}次：找不到地址栏")
            continue
        _, focused = ax.AXUIElementCopyAttributeValue(ab, "AXFocused", None)
        if not focused:
            print(f"第{attempt}次：地址栏未聚焦，重试")
            continue
        ax.AXUIElementSetAttributeValue(ab, "AXValue", "about:blank")
        time.sleep(0.3)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, 36, True))
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateKeyboardEvent(None, 36, False))
        time.sleep(2)
        new_title = window_title(w0)
        if new_title != title or "DeepSeek" not in new_title:
            print(f"第{attempt}次：导航成功，标题 {new_title!r}")
            return True
        print(f"第{attempt}次：导航未生效，重试")
    return False


def main() -> int:
    cleanup_test_apps()
    if not activate_safari():
        print("Safari 未运行")
        return 1
    time.sleep(1)
    ws = AppKit.NSWorkspace.sharedWorkspace()
    safari = [a for a in ws.runningApplications() if a.bundleIdentifier() == "com.apple.Safari"]
    if not safari:
        print("Safari 未运行")
        return 1
    safari_ax = ax.AXUIElementCreateApplication(safari[0].processIdentifier())
    ok = navigate_to_blank(safari_ax)
    print("恢复" + ("成功" if ok else "失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
