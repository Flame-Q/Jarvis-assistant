"""Repository tests against a temporary SQLite database."""

from __future__ import annotations

import time

from jarvis.storage.db import Database
from jarvis.storage.repositories import (
    CommandRepository,
    HistoryRepository,
    NotesRepository,
    TimerRepository,
)


def test_history_roundtrip(db: Database) -> None:
    repo = HistoryRepository(db)
    repo.add_turn("user", "привет")
    repo.add_turn("assistant", "здравствуйте")
    turns = repo.recent(10)
    assert [turn.text for turn in turns] == ["привет", "здравствуйте"]
    assert [turn.role for turn in turns] == ["user", "assistant"]
    repo.clear()
    assert repo.recent() == []


def test_history_limit_returns_latest_in_order(db: Database) -> None:
    repo = HistoryRepository(db)
    for index in range(5):
        repo.add_turn("user", f"msg-{index}")
    turns = repo.recent(3)
    assert [turn.text for turn in turns] == ["msg-2", "msg-3", "msg-4"]


def test_commands_are_logged(db: Database) -> None:
    repo = CommandRepository(db)
    repo.log("weather", {"city": "Москва"}, "ok")
    repo.log("timer", {"seconds": 60}, "failed")
    rows = repo.recent()
    assert len(rows) == 2
    assert rows[0]["intent"] == "timer"
    assert rows[1]["status"] == "ok"


def test_notes_lifecycle(db: Database) -> None:
    repo = NotesRepository(db)
    note_id = repo.add("купить хлеб")
    assert note_id > 0
    assert [note["text"] for note in repo.pending()] == ["купить хлеб"]
    assert repo.complete(note_id) is True
    assert repo.pending() == []
    assert repo.complete(9999) is False


def test_timers_lifecycle(db: Database) -> None:
    repo = TimerRepository(db)
    timer_id = repo.add("позвонить", time.time() + 60)
    pending = repo.pending()
    assert len(pending) == 1
    assert pending[0]["text"] == "позвонить"
    repo.mark_fired(timer_id)
    assert repo.pending() == []
