"""Command parsing tests for skills (no side effects)."""

from __future__ import annotations

import threading
from pathlib import Path

from jarvis.config import AppConfig
from jarvis.os_win.apps_index import AppsIndex
from jarvis.skills.app_launcher import AppLauncherSkill
from jarvis.skills.base import normalize_text
from jarvis.skills.notes import NotesSkill
from jarvis.skills.time_date import TimeDateSkill
from jarvis.skills.timer import TimerSkill, _plural
from jarvis.skills.volume import VolumeSkill
from jarvis.skills.weather import WeatherSkill
from jarvis.storage.db import Database
from jarvis.storage.repositories import NotesRepository


def test_normalize_text() -> None:
    assert normalize_text("Открой, ДИСКОРД!") == "открой дискорд"
    assert normalize_text("ёлка") == "елка"


def test_app_launcher_extracts_target(tmp_path: Path) -> None:
    skill = AppLauncherSkill(AppConfig(), AppsIndex(tmp_path / "apps.json"))
    assert skill.extract_args("открой дискорд").target == "дискорд"
    assert skill.extract_args("запусти блокнот, пожалуйста").target == "блокнот"
    assert skill.extract_args("открой программу Steam").target == "steam"


def test_app_launcher_requires_target(tmp_path: Path) -> None:
    skill = AppLauncherSkill(AppConfig(), AppsIndex(tmp_path / "apps.json"))
    result = skill.execute(skill.args_model(target=""))
    assert result.ok is False


def test_timer_parsing() -> None:
    skill = TimerSkill(speak=lambda _: None)
    assert skill.extract_args("таймер на 5 минут").seconds == 300
    assert skill.extract_args("поставь таймер на 90 секунд").seconds == 90
    assert skill.extract_args("напомни через час позвонить маме").seconds == 3600
    assert skill.extract_args("напомни через час позвонить маме").text == "позвонить маме"
    assert skill.extract_args("таймер на полчаса").seconds == 1800


def test_timer_rejects_empty_duration() -> None:
    skill = TimerSkill(speak=lambda _: None)
    result = skill.execute(skill.args_model(seconds=0))
    assert result.ok is False
    assert "длительность" in result.text.lower()


def test_timer_fires_and_speaks() -> None:
    spoken: list[str] = []
    fired = threading.Event()

    def speak(text: str) -> None:
        spoken.append(text)
        fired.set()

    skill = TimerSkill(speak=speak)
    result = skill.execute(skill.args_model(seconds=1))

    assert result.ok is True
    assert fired.wait(2.5), "timer must fire within two seconds"
    assert spoken == ["Таймер сработал."]
    skill.cancel_all()


def test_plural_forms() -> None:
    assert _plural(1) == "1 секунду"
    assert _plural(60) == "1 минуту"
    assert _plural(90) == "1 минуту 30 секунд"
    assert _plural(300) == "5 минут"
    assert _plural(7200) == "2 часа"


def test_volume_parsing() -> None:
    skill = VolumeSkill()
    assert skill.extract_args("громкость 30").value == 30
    assert skill.extract_args("громкость 30").action == "set"
    assert skill.extract_args("сделай громче").action == "up"
    assert skill.extract_args("выключи звук").action == "mute"
    assert skill.extract_args("включи звук").action == "unmute"


def test_weather_city_parsing() -> None:
    config = AppConfig()
    skill = WeatherSkill(config)
    assert skill.extract_args("какая погода в Москве").city == "Москва"
    assert skill.extract_args("погода в питере").city == "Санкт-Петербург"
    assert skill.extract_args("погода").city == config.weather.default_city
    assert skill.extract_args("будет ли дождь").city == config.weather.default_city


def test_weather_city_stemming() -> None:
    from jarvis.skills.weather import _city_variants, _plural_ru, city_matches

    assert city_matches("москве", "Москва")
    assert city_matches("казани", "Казань")
    assert city_matches("нижнем новгороде", "Нижний Новгород")
    assert not city_matches("москве", "Москверо")
    assert "казань" in _city_variants("казани")
    assert _plural_ru(1, "градус", "градуса", "градусов") == "градус"
    assert _plural_ru(4, "градус", "градуса", "градусов") == "градуса"
    assert _plural_ru(11, "градус", "градуса", "градусов") == "градусов"


def test_time_and_date() -> None:
    skill = TimeDateSkill()
    time_result = skill.execute(skill.args_model(kind="time"))
    date_result = skill.execute(skill.args_model(kind="date"))
    assert "Сейчас" in time_result.text
    assert "Сегодня" in date_result.text


def test_notes_add_and_list(db: Database) -> None:
    skill = NotesSkill(NotesRepository(db))
    added = skill.execute(skill.args_model(action="add", text="купить хлеб"))
    assert added.ok is True

    listed = skill.execute(skill.args_model(action="list"))
    assert "купить хлеб" in listed.text


def test_notes_empty_list(db: Database) -> None:
    skill = NotesSkill(NotesRepository(db))
    result = skill.execute(skill.args_model(action="list"))
    assert "пуст" in result.text
