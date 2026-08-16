"""DeviceBackend abstraction.

The single point where platform differences are absorbed. The orchestrator
only depends on this interface, so adding a new platform (Android, iOS) is
just implementing another backend.

Implementations translate native UI state into core.types (Element tree +
screenshot) and execute core.types.Action on the real device.
"""

from __future__ import annotations

import abc
from typing import Optional

from core.types import Action, ActionResult, ScreenState


class BackendError(Exception):
    """Base error for all backend failures."""


class PermissionError_(BackendError):
    """The process lacks the required OS permission (Accessibility etc.)."""


class ElementNotFoundError(BackendError):
    """A target element ref could not be re-located in the current snapshot."""


class ActionNotSupportedError(BackendError):
    """The platform cannot perform this action kind (e.g. pinch on macOS)."""


class DeviceBackend(abc.ABC):
    """Platform-agnostic interface every device controller implements."""

    platform: str = "unknown"

    # -- observation ---------------------------------------------------------

    @abc.abstractmethod
    def perceive(self) -> ScreenState:
        """Capture the current screen: UI tree (+ screenshot when possible)."""

    # -- execution -----------------------------------------------------------

    @abc.abstractmethod
    def act(self, action: Action) -> ActionResult:
        """Perform a unified action on the real device."""

    # -- convenience primitives (built on act) ------------------------------

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

    # -- helpers -------------------------------------------------------------

    def close(self) -> None:
        """Release resources; called at the end of a session."""
