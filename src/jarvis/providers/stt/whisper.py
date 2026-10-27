"""Local speech recognition with faster-whisper."""

from __future__ import annotations

import threading

import numpy as np
from loguru import logger

from jarvis.config import STTSettings
from jarvis.core.errors import ProviderError


class WhisperSTT:
    """Lazy-loaded faster-whisper model (CPU, int8 by default)."""

    name = "faster-whisper"

    def __init__(self, settings: STTSettings) -> None:
        self._settings = settings
        self._model = None
        self._lock = threading.Lock()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - dependency issue
                raise ProviderError("faster-whisper не установлен.") from exc

            logger.info(
                "Loading Whisper model '{}' ({}, {})",
                self._settings.model,
                self._settings.device,
                self._settings.compute_type,
            )
            try:
                self._model = WhisperModel(
                    self._settings.model,
                    device=self._settings.device,
                    compute_type=self._settings.compute_type,
                )
            except Exception as exc:  # pragma: no cover - model download/runtime
                raise ProviderError(f"Не удалось загрузить модель Whisper: {exc}") from exc

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        self._ensure_model()
        if audio.size == 0:
            return ""

        samples = audio.astype(np.float32)
        if np.abs(samples).max(initial=0.0) > 1.5:
            samples = samples / 32768.0
        if sample_rate != 16000:
            target_len = int(len(samples) * 16000 / sample_rate)
            samples = np.interp(
                np.linspace(0, len(samples), target_len, endpoint=False),
                np.arange(len(samples)),
                samples,
            ).astype(np.float32)

        try:
            model = self._model
            if model is None:
                raise ProviderError("Модель Whisper не загружена.")
            segments, info = model.transcribe(
                samples,
                language=self._settings.language,
                beam_size=self._settings.beam_size,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # pragma: no cover - engine failure
            raise ProviderError(f"Ошибка распознавания речи: {exc}") from exc

        logger.debug("STT ({}): {!r}", info.language, text)
        return text

    def warmup(self) -> None:
        self._ensure_model()
        try:
            self.transcribe(np.zeros(8000, dtype=np.float32), 16000)
        except ProviderError:
            logger.warning("STT warmup failed")
