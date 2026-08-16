"""iOS 后端：Appium / WebDriverAgent（WDA）。

骨架 —— iOS 是限制最多的平台：
  - 真机需要开发者证书 + WDA 服务
  - 截图只能经 WDA（没有直接的 screencap）

  统一 Action            -> iOS 机制
    tap(ref)                WDA POST /session/:id/wda/tap（frame 转坐标）
    type(text)              WDA sendKeys（支持中文）
    swipe / scroll          WDA swipe / scroll 端点
    key(home)               WDA pressButton("home")
    open_app(bundle)        WDA app activate / springboard launch
    screenshot              WDA GET /screenshot（PNG base64）

说明：
  - WDA 层级 JSON 与统一模型几乎一一对应
    （type -> role，label -> text，identifier -> ref，frame -> Rect）
  - 权限弹窗与 SpringBoard 提示需要显式处理关闭
"""

from __future__ import annotations

from core.types import Action, ActionResult, ScreenState
from backends.base import DeviceBackend


class IOSBackend(DeviceBackend):
    """通过 Appium WebDriverAgent 控制 iOS 设备（骨架）。"""

    platform = "ios"

    def __init__(self, wda_url: str = "http://127.0.0.1:8100"):
        self.wda_url = wda_url.rstrip("/")

    def perceive(self) -> ScreenState:
        """TODO: WDA GET /session/:id/source + /screenshot。"""
        raise NotImplementedError("IOSBackend.perceive")

    def act(self, action: Action) -> ActionResult:
        """TODO: 把统一 Action 映射到 WDA 端点。"""
        raise NotImplementedError("IOSBackend.act")
