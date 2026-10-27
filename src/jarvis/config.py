"""Configuration models and TOML loading.

The project deliberately avoids cloud credentials: all providers run locally.
Configuration lives in ``config/config.toml`` (optional) and is merged over
built-in defaults, so the application always starts even without a config file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

DEFAULT_ALIASES: dict[str, str] = {
    "дискорд": "discord://",
    "хром": "Google Chrome",
    "браузер": "Google Chrome",
    "стим": "steam://open/main",
    "телеграм": "Telegram",
    "блокнот": "notepad",
    "калькулятор": "calc",
    "проводник": "explorer",
    "ютуб": "https://www.youtube.com",
    "youtube": "https://www.youtube.com",
}


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AssistantSettings(_Section):
    name: str = "Джарвис"
    wake_word: str = "hey_jarvis"
    wake_word_enabled: bool = True
    sensitivity: float = Field(default=0.4, ge=0.0, le=1.0)
    hotkey: str = "ctrl+alt+j"
    manual_hotkey: str = "ctrl+alt+space"
    language: str = "ru"
    data_dir: str = "data"


class STTSettings(_Section):
    model: str = "small"
    compute_type: str = "int8"
    device: str = "cpu"
    language: str = "ru"
    beam_size: int = 1
    vad_silence_ms: int = Field(default=800, ge=200, le=3000)
    max_utterance_s: float = Field(default=12.0, ge=2.0, le=60.0)
    manual_max_utterance_s: float = Field(default=60.0, ge=5.0, le=300.0)


class TTSSettings(_Section):
    provider: str = "sapi5"
    voice: str = "ru"
    rate: int = Field(default=180, ge=80, le=350)
    volume: float = Field(default=1.0, ge=0.0, le=1.0)


class LLMSettings(_Section):
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b-instruct"
    num_ctx: int = 4096
    keep_alive: str = "30m"
    temperature_chat: float = 0.7
    temperature_tools: float = 0.2
    history_turns: int = 12
    timeout_s: float = 60.0


class WeatherSettings(_Section):
    default_city: str = "Москва"
    cache_ttl_s: int = 600


class SkillSettings(_Section):
    shell_enabled: bool = False
    aliases: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_ALIASES))


class UISettings(_Section):
    tray: bool = True
    theme: str = "dark"


class LoggingSettings(_Section):
    level: str = "INFO"
    file: str = "data/jarvis.log"


class AppConfig(BaseModel):
    """Root configuration object."""

    model_config = ConfigDict(extra="ignore")

    assistant: AssistantSettings = Field(default_factory=AssistantSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    weather: WeatherSettings = Field(default_factory=WeatherSettings)
    skills: SkillSettings = Field(default_factory=SkillSettings)
    ui: UISettings = Field(default_factory=UISettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    def data_path(self, root: Path | None = None) -> Path:
        base = Path(self.assistant.data_dir)
        if not base.is_absolute() and root is not None:
            base = root / base
        base.mkdir(parents=True, exist_ok=True)
        return base


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(root: Path | None = None, path: Path | None = None) -> AppConfig:
    """Load configuration, merging a TOML file over defaults.

    Lookup order: explicit ``path``, then ``config/config.toml``,
    then ``config/config.example.toml``. A missing file is not an error.
    """

    root = root or Path.cwd()
    candidates: list[Path] = []
    if path is not None:
        candidates.append(path)
    else:
        candidates.extend(
            [root / "config" / "config.toml", root / "config" / "config.example.toml"]
        )

    defaults = AppConfig().model_dump()
    for candidate in candidates:
        if candidate.is_file():
            with candidate.open("rb") as handle:
                raw = tomllib.load(handle)
            return AppConfig.model_validate(_merge(defaults, raw))
    return AppConfig.model_validate(defaults)
