"""Console presentation tests: Rich output without a real terminal."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from jarvis.ui.console import EXIT_COMMANDS, ConsoleUI


def _ui() -> tuple[ConsoleUI, StringIO]:
    stream = StringIO()
    console = Console(file=stream, force_terminal=False, color_system=None, width=100)
    return ConsoleUI(console), stream


def test_banner_uses_rich_panel() -> None:
    ui, stream = _ui()

    ui.banner()

    output = stream.getvalue()
    assert "J A R V I S" in output
    assert "JARVIS" in output
    assert "локально" in output


def test_command_table_lists_skills_and_examples() -> None:
    ui, stream = _ui()
    skills = [
        SimpleNamespace(name="weather", examples=["какая погода в Москве"]),
        SimpleNamespace(name="timer", examples=["таймер на 5 минут"]),
    ]

    ui.commands(skills)

    output = stream.getvalue()
    assert "Зарегистрированные команды" in output
    assert "weather" in output
    assert "какая погода в Москве" in output
    assert "timer" in output


def test_assistant_answer_has_label() -> None:
    ui, stream = _ui()

    ui.assistant("Готово")

    assert "Джарвис:" in stream.getvalue()
    assert "Готово" in stream.getvalue()


def test_exit_aliases_include_q_quit_and_exit() -> None:
    assert {"q", "quit", "exit"} <= EXIT_COMMANDS
