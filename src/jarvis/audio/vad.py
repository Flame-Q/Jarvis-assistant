"""Voice activity detection on 20 ms frames."""

from __future__ import annotations

import webrtcvad


class VoiceActivityDetector:
    def __init__(self, aggressiveness: int = 2) -> None:
        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, frame: bytes, sample_rate: int = 16000) -> bool:
        try:
            return bool(self._vad.is_speech(frame, sample_rate))
        except Exception:  # pragma: no cover - malformed frame
            return False
