"""Optional online TTS (edge-tts) used only when explicitly enabled.

Requires the optional extras: pip install ".[edge]" (edge-tts + miniaudio).
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from loguru import logger

from jarvis.config import TTSSettings
from jarvis.core.errors import ProviderError


class EdgeTTS:
    name = "edge-tts"

    def __init__(self, settings: TTSSettings, voice: str = "ru-RU-DariyaNeural") -> None:
        self._settings = settings
        self._voice = voice
        self._speaking = threading.Event()
        self._available = self._check()

    def _check(self) -> bool:
        try:
            import edge_tts  # noqa: F401
            import miniaudio  # noqa: F401
        except ImportError:
            logger.warning("edge-tts/miniaudio not installed; cloud TTS disabled")
            return False
        return True

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def speak(self, text: str) -> None:
        if not self._available:
            raise ProviderError("edge-tts не установлен.")
        self._speaking.set()
        try:
            import asyncio

            import edge_tts
            import miniaudio

            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "speech.mp3"
                asyncio.run(self._synthesize(edge_tts, text, path))
                stream = miniaudio.stream_file(str(path))
                with miniaudio.PlaybackDevice() as device:
                    device.start(stream)
                    while device.running:
                        pass
        finally:
            self._speaking.clear()

    async def _synthesize(self, edge_tts: object, text: str, path: Path) -> None:
        communicate = edge_tts.Communicate(text, self._voice)  # type: ignore[attr-defined]
        await communicate.save(str(path))

    def stop(self) -> None:
        self._speaking.clear()

    def close(self) -> None:
        self._speaking.clear()
