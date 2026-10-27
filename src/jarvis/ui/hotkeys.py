"""Global hotkey registration helper (Windows, via the keyboard package)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger


class HotkeyManager:
    """Registers a single global hotkey and makes re-registration safe."""

    def __init__(self) -> None:
        self._handle: Any = None
        self._hotkey: str | None = None

    @property
    def hotkey(self) -> str | None:
        return self._hotkey

    def register(self, hotkey: str, callback: Callable[[], None]) -> bool:
        try:
            import keyboard
        except ImportError:  # pragma: no cover - optional on non-Windows
            logger.warning("keyboard package is not installed; hotkey disabled")
            return False

        self.unregister()
        try:
            self._handle = keyboard.add_hotkey(hotkey, callback)
        except Exception as exc:  # pragma: no cover - global hook permissions
            logger.warning("Cannot register hotkey {}: {}", hotkey, exc)
            return False
        self._hotkey = hotkey
        logger.info("Hotkey registered: {}", hotkey)
        return True

    def unregister(self) -> None:
        if self._handle is None:
            return
        try:
            import keyboard

            keyboard.remove_hotkey(self._handle)
        except Exception:  # pragma: no cover
            logger.debug("Hotkey was already removed")
        finally:
            self._handle = None
            self._hotkey = None
