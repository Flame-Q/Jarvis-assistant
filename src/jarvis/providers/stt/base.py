"""Speech-to-text provider interface."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class STTProvider(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str: ...

    def warmup(self) -> None: ...
