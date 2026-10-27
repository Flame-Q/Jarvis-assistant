"""Repositories: the only place that knows SQL (Repository pattern)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from jarvis.core.models import Turn
from jarvis.storage.db import Database


class HistoryRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._lock = threading.RLock()

    def add_turn(self, role: str, text: str) -> Turn:
        turn = Turn(role=role, text=text)  # type: ignore[arg-type]
        with self._lock:
            self._db.connection.execute(
                "INSERT INTO turns (role, text, created_at) VALUES (?, ?, ?)",
                (role, text, turn.created_at),
            )
            self._db.connection.commit()
        return turn

    def recent(self, limit: int = 20) -> list[Turn]:
        with self._lock:
            rows = self._db.connection.execute(
                "SELECT role, text, created_at FROM turns ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Turn(role=row["role"], text=row["text"], created_at=row["created_at"])
            for row in reversed(rows)
        ]

    def clear(self) -> None:
        with self._lock:
            self._db.connection.execute("DELETE FROM turns")
            self._db.connection.commit()


class CommandRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._lock = threading.RLock()

    def log(self, intent: str, args: dict[str, Any], status: str) -> None:
        with self._lock:
            self._db.connection.execute(
                "INSERT INTO commands (intent, args_json, status, created_at) VALUES (?, ?, ?, ?)",
                (intent, json.dumps(args, ensure_ascii=False), status, time.time()),
            )
            self._db.connection.commit()

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.connection.execute(
                "SELECT intent, args_json, status, created_at FROM commands "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


class NotesRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._lock = threading.RLock()

    def add(self, text: str) -> int:
        with self._lock:
            cursor = self._db.connection.execute(
                "INSERT INTO notes (text, created_at) VALUES (?, ?)", (text, time.time())
            )
            self._db.connection.commit()
            return int(cursor.lastrowid or 0)

    def pending(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.connection.execute(
                "SELECT id, text, created_at FROM notes WHERE done = 0 "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def complete(self, note_id: int) -> bool:
        with self._lock:
            cursor = self._db.connection.execute(
                "UPDATE notes SET done = 1 WHERE id = ?", (note_id,)
            )
            self._db.connection.commit()
            return cursor.rowcount > 0

    def clear(self) -> None:
        with self._lock:
            self._db.connection.execute("DELETE FROM notes")
            self._db.connection.commit()


class TimerRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._lock = threading.RLock()

    def add(self, text: str, due_at: float) -> int:
        with self._lock:
            cursor = self._db.connection.execute(
                "INSERT INTO timers (text, due_at) VALUES (?, ?)", (text, due_at)
            )
            self._db.connection.commit()
            return int(cursor.lastrowid or 0)

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.connection.execute(
                "SELECT id, text, due_at FROM timers WHERE fired = 0 ORDER BY due_at"
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_fired(self, timer_id: int) -> None:
        with self._lock:
            self._db.connection.execute("UPDATE timers SET fired = 1 WHERE id = ?", (timer_id,))
            self._db.connection.commit()
