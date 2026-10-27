"""TTS helpers that do not touch real speakers or Windows COM."""

from __future__ import annotations

from jarvis.config import TTSSettings
from jarvis.providers.tts.sapi5_tts import Sapi5TTS, rate_to_sapi, volume_to_sapi


class FakeToken:
    def __init__(self, description: str, token_id: str) -> None:
        self._description = description
        self.Id = token_id

    def GetDescription(self) -> str:
        return self._description


class FakeTokens:
    def __init__(self, tokens: list[FakeToken]) -> None:
        self._tokens = tokens
        self.Count = len(tokens)

    def Item(self, index: int) -> FakeToken:
        return self._tokens[index]


class FakeEngine:
    def __init__(self, tokens: list[FakeToken]) -> None:
        self._tokens = FakeTokens(tokens)
        self.Voice: FakeToken | None = None

    def GetVoices(self) -> FakeTokens:
        return self._tokens


def _tts_without_worker() -> Sapi5TTS:
    tts = object.__new__(Sapi5TTS)
    tts._settings = TTSSettings()
    return tts


def test_rate_is_mapped_to_sapi_scale() -> None:
    assert rate_to_sapi(180) == 0
    assert rate_to_sapi(80) == -10
    assert rate_to_sapi(350) == 10


def test_volume_is_mapped_to_sapi_scale() -> None:
    assert volume_to_sapi(0.0) == 0
    assert volume_to_sapi(0.5) == 50
    assert volume_to_sapi(1.0) == 100


def test_apply_voice_matches_russian_token() -> None:
    tts = _tts_without_worker()
    irina = FakeToken("Microsoft Irina Desktop - Russian", "irina-id")
    zira = FakeToken("Microsoft Zira Desktop - English", "zira-id")
    engine = FakeEngine([zira, irina])

    tts._apply_voice(engine, "ru")  # noqa: SLF001

    assert engine.Voice is irina


def test_apply_voice_keeps_default_when_nothing_matches() -> None:
    tts = _tts_without_worker()
    zira = FakeToken("Microsoft Zira Desktop - English", "zira-id")
    engine = FakeEngine([zira])

    tts._apply_voice(engine, "does-not-exist")  # noqa: SLF001

    assert engine.Voice is None
