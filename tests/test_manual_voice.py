"""Push-to-talk tests: no microphone, Whisper, Ollama or speakers."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

import numpy as np
from tests.conftest import FakeLLM, FakeTTS, make_assistant

from jarvis.audio.loop import VoiceLoop
from jarvis.config import AppConfig
from jarvis.core.events import EventBus

BLOCK = 320  # 20 ms at 16 kHz


class FakeMic:
    def __init__(self, frames: list[bytes] | None = None) -> None:
        self.frames = deque(frames or [])
        self.drain_calls = 0
        self.read_calls = 0

    def drain(self) -> None:
        self.drain_calls += 1

    def read(self, timeout: float = 0.2) -> bytes | None:
        self.read_calls += 1
        if self.frames:
            return self.frames.popleft()
        time.sleep(0.002)
        return None


class FakeSTT:
    def __init__(self, text: str = "привет") -> None:
        self.text = text
        self.audio_sizes: list[int] = []
        self.warmup_calls = 0

    def warmup(self) -> None:
        self.warmup_calls += 1

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        self.audio_sizes.append(int(audio.size))
        return self.text


def _silence(count: int = 1) -> list[bytes]:
    return [np.zeros(BLOCK, dtype=np.int16).tobytes() for _ in range(count)]


def _wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _loop(
    monkeypatch,
    *,
    text: str = "привет",
    frames: list[bytes] | None = None,
) -> tuple[VoiceLoop, FakeMic, FakeSTT, FakeTTS]:
    monkeypatch.setattr("jarvis.audio.loop.beep", lambda *args, **kwargs: None)
    config = AppConfig()
    assistant, tts, _llm, _history, _registry = make_assistant(
        [], config=config, llm=FakeLLM("ответ")
    )
    stt = FakeSTT(text)
    loop = VoiceLoop(
        config=config,
        assistant=assistant,
        stt=stt,
        tts=tts,
        bus=EventBus(),
    )
    mic = FakeMic(frames)
    loop._mic = mic  # noqa: SLF001 - inject a fake capture device
    loop._running = True  # noqa: SLF001 - start() would open the real device
    return loop, mic, stt, tts


def test_manual_recording_processes_audio_after_second_press(monkeypatch) -> None:
    loop, mic, stt, tts = _loop(monkeypatch, text="который час", frames=_silence(3))

    assert loop.start_manual_recording()
    assert loop.recording
    assert loop.stop_manual_recording()
    assert _wait_until(lambda: not loop.busy)

    assert mic.drain_calls == 1
    assert stt.audio_sizes == [3 * BLOCK]
    assert "ответ" in " ".join(tts.spoken)
    assert not loop.recording


def test_manual_recording_rejects_empty_capture(monkeypatch) -> None:
    loop, _mic, stt, tts = _loop(monkeypatch, frames=[])

    assert loop.start_manual_recording()
    assert loop.stop_manual_recording()
    assert _wait_until(lambda: not loop.busy)

    assert stt.audio_sizes == []
    assert any("Не расслышал" in phrase for phrase in tts.spoken)


def test_manual_recording_cannot_start_while_busy(monkeypatch) -> None:
    loop, _mic, _stt, _tts = _loop(monkeypatch)

    assert loop._busy.acquire(blocking=False)  # noqa: SLF001
    try:
        assert not loop.start_manual_recording()
    finally:
        loop._busy.release()  # noqa: SLF001


def test_manual_recording_cannot_start_while_tts_speaks(monkeypatch) -> None:
    loop, _mic, _stt, tts = _loop(monkeypatch)
    tts.is_speaking = True

    assert not loop.start_manual_recording()


def test_toggle_manual_starts_and_stops(monkeypatch) -> None:
    loop, _mic, _stt, _tts = _loop(monkeypatch, frames=_silence(1))

    assert loop.toggle_manual()
    assert loop.recording
    assert loop.toggle_manual()
    assert _wait_until(lambda: not loop.busy)
    assert not loop.recording
