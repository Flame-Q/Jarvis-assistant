"""Configuration loading tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.config import AppConfig, load_config


def test_defaults() -> None:
    config = AppConfig()
    assert config.llm.model == "qwen2.5:3b-instruct"
    assert config.stt.language == "ru"
    assert config.skills.aliases["дискорд"] == "discord://"
    assert config.skills.shell_enabled is False
    assert config.assistant.wake_word_enabled is True
    assert config.assistant.manual_hotkey == "ctrl+alt+space"
    assert config.stt.manual_max_utterance_s == 60.0
    assert config.tts.provider == "sapi5"


def test_missing_file_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.assistant.name == "Джарвис"


def test_partial_toml_is_merged(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[llm]\nmodel = "qwen3:4b"\n\n[assistant]\nsensitivity = 0.5\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.llm.model == "qwen3:4b"
    assert config.assistant.sensitivity == 0.5
    # untouched keys keep defaults
    assert config.stt.model == "small"


def test_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "custom.toml"
    path.write_text('[weather]\ndefault_city = "Казань"\n', encoding="utf-8")
    config = load_config(tmp_path, path)
    assert config.weather.default_city == "Казань"


def test_invalid_sensitivity_is_rejected(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[assistant]\nsensitivity = 5.0\n", encoding="utf-8"
    )
    with pytest.raises(ValidationError):
        load_config(tmp_path)


def test_data_path_creates_directory(tmp_path: Path) -> None:
    config = AppConfig()
    config.assistant.data_dir = "runtime"
    path = config.data_path(tmp_path)
    assert path.is_dir()
    assert path.name == "runtime"


def test_settings_dump_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from jarvis.ui.settings_window import write_config

    config = AppConfig()
    config.assistant.sensitivity = 0.35
    config.assistant.wake_word_enabled = False
    config.assistant.manual_hotkey = "ctrl+alt+shift+m"
    config.stt.manual_max_utterance_s = 45.0
    config.weather.default_city = "Казань"
    config.skills.aliases["тест"] = r"C:\Tools\test.exe"

    path = tmp_path / "config.toml"
    write_config(path, config)
    loaded = load_config(path=path)

    assert loaded.assistant.sensitivity == 0.35
    assert loaded.assistant.wake_word_enabled is False
    assert loaded.assistant.manual_hotkey == "ctrl+alt+shift+m"
    assert loaded.stt.manual_max_utterance_s == 45.0
    assert loaded.weather.default_city == "Казань"
    assert loaded.skills.aliases["тест"] == r"C:\Tools\test.exe"
