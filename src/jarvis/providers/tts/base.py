"""Text-to-speech provider interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    @property
    def is_speaking(self) -> bool: ...

    def speak(self, text: str) -> None: ...

    def stop(self) -> None: ...

    def close(self) -> None: ...
