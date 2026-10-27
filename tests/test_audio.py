"""Audio helpers that can be tested without a microphone or real models."""

from __future__ import annotations

import numpy as np
import pytest

from jarvis.audio.wakeword import FRAME_SAMPLES, WakeWordDetector

BLOCK = 320  # 20 ms at 16 kHz


class FakeWakeModel:
    def __init__(self) -> None:
        self.sizes: list[int] = []
        self.reset_calls = 0

    def predict(self, chunk: np.ndarray) -> dict[str, float]:
        self.sizes.append(int(chunk.size))
        return {"hey_jarvis": 0.9}

    def reset(self) -> None:
        self.reset_calls += 1


def _silence() -> bytes:
    return np.zeros(BLOCK, dtype=np.int16).tobytes()


def test_wakeword_accumulates_20ms_blocks_into_80ms_window() -> None:
    detector = WakeWordDetector(threshold=0.4)
    fake = FakeWakeModel()
    detector._model = fake  # noqa: SLF001 - inject fake instead of ONNX

    scores = [detector.process(_silence()) for _ in range(4)]

    assert scores[:3] == [0.0, 0.0, 0.0]
    assert scores[3] == pytest.approx(0.9)
    assert fake.sizes == [FRAME_SAMPLES]


def test_wakeword_reset_drops_partial_window() -> None:
    detector = WakeWordDetector(threshold=0.4)
    fake = FakeWakeModel()
    detector._model = fake  # noqa: SLF001

    detector.process(_silence())
    detector.process(_silence())
    detector.reset()
    scores = [detector.process(_silence()) for _ in range(4)]

    assert scores[:3] == [0.0, 0.0, 0.0]
    assert scores[3] == pytest.approx(0.9)
    assert fake.reset_calls == 1


def test_wakeword_threshold_is_clamped() -> None:
    detector = WakeWordDetector(threshold=0.4)
    detector.threshold = 5.0
    assert detector.threshold == 1.0
    detector.threshold = -2.0
    assert detector.threshold == 0.0
