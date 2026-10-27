"""Wake word detection with openWakeWord (ONNX, fully offline)."""

from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger

FRAME_SAMPLES = 1280  # 80 ms at 16 kHz


class WakeWordDetector:
    """Accumulates 20 ms blocks into 80 ms windows expected by openWakeWord."""

    def __init__(
        self,
        model_name: str = "hey_jarvis",
        threshold: float = 0.4,
        inference_framework: str = "onnx",
    ) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._framework = inference_framework
        self._model: Any = None
        self._pending = np.zeros(0, dtype=np.int16)

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        self._threshold = max(0.0, min(1.0, value))

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            import openwakeword
            from openwakeword.model import Model

            try:
                openwakeword.utils.download_models()
            except Exception as exc:  # pragma: no cover - offline first run
                logger.warning("openWakeWord model download failed: {}", exc)
            self._model = Model(
                wakeword_models=[self._model_name],
                inference_framework=self._framework,
            )
            logger.info("Wake word model loaded: {}", self._model_name)
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.error("Cannot load wake word model: {}", exc)
            raise

    def process(self, frame: bytes) -> float:
        self._ensure_model()
        samples = np.frombuffer(frame, dtype=np.int16)
        if samples.size == 0:
            return 0.0

        # openWakeWord expects non-overlapping 80 ms windows. The microphone
        # delivers 20 ms blocks, so accumulate four blocks before predicting.
        self._pending = np.concatenate([self._pending, samples])
        if self._pending.size < FRAME_SAMPLES:
            return 0.0

        best = 0.0
        while self._pending.size >= FRAME_SAMPLES:
            chunk = self._pending[:FRAME_SAMPLES]
            self._pending = self._pending[FRAME_SAMPLES:]
            predictions: dict[str, float] = (
                self._model.predict(chunk) if self._model is not None else {}
            )
            if predictions:
                best = max(best, float(max(predictions.values())))
        return best

    def warmup(self) -> None:
        """Load the model and initialise its internal buffers with silence."""

        self._ensure_model()
        if self._model is not None:
            self._model.predict(np.zeros(FRAME_SAMPLES, dtype=np.int16))
        self.reset()

    def reset(self) -> None:
        self._pending = np.zeros(0, dtype=np.int16)
        if self._model is not None:
            try:
                self._model.reset()
            except Exception:  # pragma: no cover
                pass
