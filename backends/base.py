"""DeviceBackend 抽象层。

平台差异被吸收的唯一分叉点。orchestrator 只依赖这个接口，
因此新增平台（Android、iOS）只是再实现一个后端。

实现负责把原生 UI 状态翻译成 core.types（Element 树 + 截图），
并在真实设备上执行 core.types.Action。
"""

from __future__ import annotations

import abc
from typing import Optional

from core.types import Action, ActionResult, ScreenState


class BackendError(Exception):
    """所有后端错误的基类。"""


class PermissionError_(BackendError):
    """进程缺少所需的操作系统权限（辅助功能等）。"""


class ElementNotFoundError(BackendError):
    """目标元素 ref 无法在当前快照中重新定位。"""


class ActionNotSupportedError(BackendError):
    """平台无法执行该动作类型（例如 macOS 上的 pinch）。"""


class DeviceBackend(abc.ABC):
    """每个设备控制器都要实现的平台无关接口。"""

    platform: str = "unknown"

    # -- 观察 --------------------------------------------------------------

    @abc.abstractmethod
    def perceive(self) -> ScreenState:
        """捕获当前屏幕：UI 树（可能时附带截图）。"""

    # -- 执行 --------------------------------------------------------------

    @abc.abstractmethod
    def act(self, action: Action) -> ActionResult:
        """在真实设备上执行一个统一动作。"""

    # -- 便捷原语（基于 act 构建） ------------------------------------------

    def open_app(self, app_id: str) -> ActionResult:
        return self.act(Action(kind="open_app", text=app_id))

    def back(self) -> ActionResult:
        return self.act(Action(kind="back"))

    def home(self) -> ActionResult:
        return self.act(Action(kind="home"))

    def wait(self, seconds: float) -> ActionResult:
        return self.act(Action(kind="wait", duration_s=seconds))

    def type_text(self, text: str, target: Optional[str] = None) -> ActionResult:
        return self.act(Action(kind="type", text=text, target=target))

    def tap(self, ref: Optional[str] = None, pos=None) -> ActionResult:
        return self.act(Action(kind="tap", target=ref, pos=pos))

    # -- 辅助 --------------------------------------------------------------

    def is_app_running(self, app_id: str) -> bool:
        """应用（bundle id 或名称）当前是否在运行。

        基类实现返回 False；后端用真实检查覆盖
        （NSWorkspace / adb shell ps / WDA 应用状态）。
        """
        return False

    def close(self) -> None:
        """释放资源；会话结束时调用。"""
