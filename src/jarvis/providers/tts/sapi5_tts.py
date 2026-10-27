"""Offline Russian speech synthesis through Windows SAPI5.

``pyttsx3`` wraps SAPI5 with a COM event sink. On some Windows installations
that path silently finishes an utterance without rendering any audio, while
the same voice works through ``SAPI.SpVoice`` directly. This provider therefore
talks to SAPI5 itself and keeps the blocking ``Speak`` call on a dedicated
worker thread.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from loguru import logger

from jarvis.config import TTSSettings

_SVSF_PURGE_BEFORE_SPEAK = 3


def rate_to_sapi(rate: int) -> int:
    """Convert words-per-minute to the SAPI ``-10..10`` scale."""

    return max(-10, min(10, round((rate - 180) / 10)))


def volume_to_sapi(volume: float) -> int:
    """Convert the config's ``0.0..1.0`` volume to SAPI's ``0..100`` scale."""

    return max(0, min(100, round(volume * 100)))


def _voice_label(token: Any) -> str:
    try:
        return str(token.GetDescription())
    except Exception:  # pragma: no cover - depends on the SAPI token type
        return str(getattr(token, "Id", "unknown"))


def list_voices() -> list[tuple[str, str]]:
    """Return ``(description, token id)`` pairs exposed by Windows SAPI5."""

    try:
        import comtypes.client

        engine = comtypes.client.CreateObject("SAPI.SpVoice")
        tokens = engine.GetVoices()
        return [
            (_voice_label(tokens.Item(index)), str(getattr(tokens.Item(index), "Id", "")))
            for index in range(tokens.Count)
        ]
    except Exception as exc:  # pragma: no cover - depends on Windows SAPI
        logger.warning("Cannot enumerate SAPI5 voices: {}", exc)
        return []


class Sapi5TTS:
    """Queue-based, local TTS provider backed by Windows SAPI5."""

    name = "sapi5"

    def __init__(self, settings: TTSSettings) -> None:
        self._settings = settings
        self._queue: queue.Queue[object] = queue.Queue()
        self._ready = threading.Event()
        self._speaking = threading.Event()
        self._stop = threading.Event()
        self._available = True
        self._engine: Any = None
        self._thread = threading.Thread(target=self._worker, name="tts-sapi5", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=8.0)

    @property
    def available(self) -> bool:
        return self._available

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def _worker(self) -> None:
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            engine = comtypes.client.CreateObject("SAPI.SpVoice")
            self._engine = engine
            self._apply_voice(engine, self._settings.voice)
            engine.Rate = rate_to_sapi(self._settings.rate)
            engine.Volume = volume_to_sapi(self._settings.volume)
        except Exception as exc:  # pragma: no cover - depends on Windows SAPI
            logger.error("SAPI5 TTS initialization failed: {}", exc)
            self._available = False
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    self._queue.task_done()
                    break
                if isinstance(item, tuple):
                    self._handle_command(item)
                    continue

                text = str(item)
                started = time.perf_counter()
                try:
                    self._stop.clear()
                    self._speaking.set()
                    # Asynchronous Speak + short waits let stop() interrupt
                    # the current phrase without calling COM from another
                    # thread (SAPI objects are apartment-bound).
                    self._engine.Speak(text, 1)
                    while not self._engine.WaitUntilDone(100):
                        if self._stop.is_set():
                            self._engine.Speak("", _SVSF_PURGE_BEFORE_SPEAK)
                            break
                except Exception:  # pragma: no cover - device can disappear
                    logger.exception("TTS failed to speak")
                finally:
                    self._speaking.clear()
                    self._queue.task_done()
                    logger.info(
                        "TTS finished in {:.2f}s: {}",
                        time.perf_counter() - started,
                        text[:80],
                    )
        finally:
            try:
                self._engine.Speak("", _SVSF_PURGE_BEFORE_SPEAK)
            except Exception:  # pragma: no cover - engine may be gone
                pass
            try:
                comtypes.CoUninitialize()
            except Exception:  # pragma: no cover - COM state may be gone
                pass

    def _handle_command(self, item: tuple[object, object]) -> None:
        command, value = item
        try:
            if command == "voice":
                self._settings.voice = str(value)
                self._apply_voice(self._engine, str(value))
            elif command == "rate":
                self._settings.rate = int(str(value))
                self._engine.Rate = rate_to_sapi(self._settings.rate)
            elif command == "volume":
                self._settings.volume = float(str(value))
                self._engine.Volume = volume_to_sapi(self._settings.volume)
        except Exception:  # pragma: no cover - invalid setting or dead engine
            logger.exception("Cannot apply TTS setting")
        finally:
            self._queue.task_done()

    def _apply_voice(self, engine: Any, voice: str) -> None:
        try:
            tokens = engine.GetVoices()
        except Exception:  # pragma: no cover - depends on Windows SAPI
            return

        needle = voice.strip().lower()
        for index in range(tokens.Count):
            token = tokens.Item(index)
            label = _voice_label(token)
            haystack = f"{label} {getattr(token, 'Id', '')}".lower()
            if needle and needle in haystack:
                engine.Voice = token
                logger.info("TTS voice: {}", label)
                return

        if needle:
            logger.warning(
                "Russian voice not found (looked for '{}'). "
                "Install Russian speech package in Windows settings.",
                voice,
            )

    def set_voice(self, voice: str) -> None:
        self._queue.put(("voice", voice))

    def set_rate(self, rate: int) -> None:
        self._queue.put(("rate", rate))

    def set_volume(self, volume: float) -> None:
        self._queue.put(("volume", volume))

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if not self._available:
            logger.warning("TTS unavailable, cannot speak: {}", text)
            return
        self._queue.put(text)

    def wait(self) -> None:
        """Block until all queued phrases are spoken (used by scripts/tests)."""

        self._queue.join()

    def stop(self) -> None:
        # The worker owns the COM object; signal it and return immediately.
        self._stop.set()
        # Drop phrases that were queued but not spoken yet.
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._queue.task_done()

    def close(self) -> None:
        # FIFO: phrases already queued are spoken before the worker exits.
        self._queue.put(None)
        self._thread.join(timeout=3.0)
