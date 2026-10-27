"""Offline Russian speech synthesis through Windows SAPI5 (pyttsx3).

A dedicated worker thread owns the engine: pyttsx3 is not thread-safe and
``runAndWait`` blocks, so it must never run on the UI or audio thread.
"""

from __future__ import annotations

import queue
import threading
from typing import Any

from loguru import logger

from jarvis.config import TTSSettings


class Pyttsx3TTS:
    name = "pyttsx3"

    def __init__(self, settings: TTSSettings) -> None:
        self._settings = settings
        self._queue: queue.Queue[object] = queue.Queue()
        self._ready = threading.Event()
        self._speaking = threading.Event()
        self._available = True
        self._engine: Any = None
        self._thread = threading.Thread(target=self._worker, name="tts", daemon=True)
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
            import pyttsx3

            engine = pyttsx3.init()
            self._apply_voice(engine, self._settings.voice)
            engine.setProperty("rate", self._settings.rate)
            engine.setProperty("volume", self._settings.volume)
            self._engine = engine
        except Exception as exc:  # pragma: no cover - depends on Windows SAPI
            logger.error("TTS initialization failed: {}", exc)
            self._available = False
            self._ready.set()
            return

        self._ready.set()
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            if isinstance(item, tuple):
                try:
                    command, value = item
                    if command == "voice":
                        self._settings.voice = str(value)
                        self._apply_voice(engine, str(value))
                    elif command == "rate":
                        self._settings.rate = int(value)
                        engine.setProperty("rate", int(value))
                except Exception:  # pragma: no cover
                    logger.exception("Cannot apply TTS setting")
                finally:
                    self._queue.task_done()
                continue
            text = str(item)
            try:
                self._speaking.set()
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception:  # pragma: no cover - engine can die on device changes
                logger.exception("TTS failed to speak")
            finally:
                self._speaking.clear()
                self._queue.task_done()

        try:
            self._engine.stop()
        except Exception:  # pragma: no cover
            pass

    def _apply_voice(self, engine: Any, voice: str) -> None:
        try:
            voices: Any = engine.getProperty("voices")
        except Exception:  # pragma: no cover
            return

        needle = voice.lower()
        for candidate in voices:
            haystack = f"{candidate.id} {candidate.name}".lower()
            if needle and needle in haystack:
                engine.setProperty("voice", candidate.id)
                logger.info("TTS voice: {}", candidate.name)
                return
        logger.warning(
            "Russian voice not found (looked for '{}'). "
            "Install Russian speech package in Windows settings.",
            voice,
        )

    def set_voice(self, voice: str) -> None:
        self._queue.put(("voice", voice))

    def set_rate(self, rate: int) -> None:
        self._queue.put(("rate", rate))

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
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:  # pragma: no cover
                pass
        # Drop phrases that were queued but not spoken yet.
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._queue.task_done()

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=3.0)
