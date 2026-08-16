"""Android 后端：adb + UIAutomator + scrcpy。

骨架 —— 统一模型到 Android 原语的映射：

  UIAutomator XML 节点                    -> core.Element
    resource-id / text / class / bounds      ref / text / role / Rect
    bounds="[l,t][r,b]"                      归一化 0-1000

  统一 Action            -> Android 机制
    tap(ref)                adb shell input tap（由归一化 bounds 换算）
    type(text)              ADBKeyboard / Appium IME（原生 input text
                             不支持中文）
    swipe / scroll          adb shell input swipe
    key(back/home)          adb shell input keyevent 4 / 3
    open_app(pkg)           adb shell am start -n pkg/activity
    screenshot              adb exec-out screencap -p
    long_press / pinch      motionevent / 多点触控注入

移植时的实现步骤：
  1. `adb devices` - 要求有一台设备（已开启 USB 调试）
  2. `adb shell uiautomator dump /sdcard/ui.xml && adb pull` 取 UI 树
  3. 解析 XML 为 Element 树（按屏幕尺寸归一化 bounds）
  4. 动态页面用 scrcpy 做实时屏幕流
  5. 处理弹窗干扰：权限弹窗、广告、更新提示
"""

from __future__ import annotations

import shutil
from typing import Optional

from core.types import Action, ActionResult, Element, Rect, ScreenState
from backends.base import BackendError, DeviceBackend


class AndroidBackend(DeviceBackend):
    """通过 adb 控制 Android 设备（骨架）。"""

    platform = "android"

    def __init__(self, serial: Optional[str] = None):
        if not shutil.which("adb"):
            raise BackendError("PATH 中找不到 adb；请安装 platform-tools")
        self.serial = serial
        self._device = ["adb"] + (["-s", serial] if serial else [])

    def _sh(self, *args: str) -> str:
        """运行一条 adb 命令，返回 stdout。"""
        import subprocess
        proc = subprocess.run(self._device + list(args), capture_output=True, text=True)
        if proc.returncode != 0:
            raise BackendError(f'adb {args[0]} 失败: {proc.stderr.strip()}')
        return proc.stdout

    # -- 观察 ---------------------------------------------------------------

    def perceive(self) -> ScreenState:
        """TODO: uiautomator dump -> XML -> Element 树 + screencap。"""
        raise NotImplementedError("AndroidBackend.perceive：见 docstring")

    # -- 执行 ---------------------------------------------------------------

    def act(self, action: Action) -> ActionResult:
        """TODO: 把统一 Action 映射到 adb 原语。"""
        raise NotImplementedError("AndroidBackend.act：见 docstring")


def parse_uiautomator_xml(xml: str, screen_w: int, screen_h: int) -> Element:
    """把 uiautomator dump 解析为归一化的 Element 树。

    节点映射：
      resource-id -> ref，text/content-desc -> text，
      class -> role（android.widget.Button -> button ...），
      bounds="[l,t][r,b]" -> 归一化 Rect。
    """
    raise NotImplementedError("parse_uiautomator_xml：实现 Android 时移植")
