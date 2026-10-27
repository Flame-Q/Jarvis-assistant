"""Microphone capture with a bounded queue."""

from __future__ import annotations

import queue
from types import TracebackType

import numpy as np
import sounddevice as sd
from loguru import logger

SAMPLE_RATE = 16000
BLOCK_MS = 20
BLOCK_SIZE = SAMPLE_RATE * BLOCK_MS // 1000


class MicrophoneStream:
    """16 kHz mono int16 stream, delivered as fixed 20 ms blocks."""

    def __init__(self, device: int | str | None = None, sample_rate: int = SAMPLE_RATE) -> None:
        self._sample_rate = sample_rate
        self._device = device
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self._stream: sd.RawInputStream | None = None

    def open(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.RawInputStream(
            samplerate=self._sample_rate,
            blocksize=BLOCK_SIZE,
            dtype="int16",
            channels=1,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        logger.info("Microphone opened: {}", self.describe())

    def _callback(self, indata: bytes, frames: int, time_info: object, status: object) -> None:
        if status:
            logger.debug("Audio status: {}", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(bytes(indata))
            except queue.Empty:  # pragma: no cover - race
                pass

    def read(self, timeout: float = 0.2) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    @staticmethod
    def describe() -> str:
        try:
            device = sd.query_devices(kind="input")
            return f"{device['name']} ({int(device['default_samplerate'])} Hz)"
        except Exception:  # pragma: no cover - depends on host API
            return "default input device"

    @staticmethod
    def devices() -> list[dict]:
        return list(sd.query_devices())

    def __enter__(self) -> MicrophoneStream:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def to_int16(audio: np.ndarray) -> np.ndarray:
    if audio.dtype == np.int16:
        return audio
    return np.clip(audio, -32768, 32767).astype(np.int16)
