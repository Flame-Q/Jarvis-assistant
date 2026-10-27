"""Timers and spoken reminders."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text, parse_number
from jarvis.storage.repositories import TimerRepository

_DURATION_RE = re.compile(
    r"(?:через|на)\s+(?:(\d+|[а-я]+)\s+)?"
    r"(секунд[а-я]*|сек|минут[а-я]*|мин|час[а-я]*|ч)\b"
)
_BARE_RE = re.compile(r"(\d+|[а-я]+)\s*(секунд[а-я]*|сек|минут[а-я]*|мин|час[а-я]*|ч)\b")

_UNIT_SECONDS = {
    "секунд": 1,
    "сек": 1,
    "минут": 60,
    "мин": 60,
    "час": 3600,
    "ч": 3600,
}


def _plural(seconds: int) -> str:
    if seconds >= 3600 and seconds % 3600 == 0:
        hours = seconds // 3600
        word = "час" if hours == 1 else ("часа" if hours in (2, 3, 4) else "часов")
        return f"{hours} {word}"
    if seconds >= 60:
        minutes, rest = divmod(seconds, 60)
        word = "минуту" if minutes == 1 else ("минуты" if minutes in (2, 3, 4) else "минут")
        text = f"{minutes} {word}"
        if rest:
            tail = "секунду" if rest == 1 else ("секунды" if rest in (2, 3, 4) else "секунд")
            text += f" {rest} {tail}"
        return text
    word = "секунду" if seconds == 1 else ("секунды" if seconds in (2, 3, 4) else "секунд")
    return f"{seconds} {word}"


class TimerArgs(BaseModel):
    seconds: int = 0
    text: str = ""


class TimerSkill(BaseSkill):
    name = "timer"
    description = "Поставить таймер или напоминание на заданное время."
    examples = ["таймер на 5 минут", "напомни через час позвонить маме"]
    triggers = ["таймер", "напомни", "напоминание", "будильник"]
    args_model: type[BaseModel] = TimerArgs

    def __init__(
        self,
        speak: Callable[[str], None],
        repository: TimerRepository | None = None,
    ) -> None:
        self._speak = speak
        self._repository = repository
        self._timers: list[threading.Timer] = []
        self._lock = threading.Lock()

    def extract_args(self, text: str) -> TimerArgs:
        normalized = normalize_text(text)
        match = _DURATION_RE.search(normalized) or _BARE_RE.search(normalized)
        seconds = 0
        remainder = normalized
        if match:
            raw_amount = match.group(1) or "1"
            amount = parse_number(raw_amount)
            if amount is None:
                amount = 1 if raw_amount.startswith(("час", "минут")) else 0
            unit = match.group(2)
            multiplier = 1
            for prefix, value in _UNIT_SECONDS.items():
                if unit.startswith(prefix):
                    multiplier = value
                    break
            seconds = amount * multiplier
            remainder = (normalized[: match.start()] + " " + normalized[match.end() :]).strip()

        if "полчаса" in normalized:
            seconds = 1800
            remainder = normalized.replace("полчаса", " ")

        for trigger in ("таймер", "напомни", "напоминание", "будильник", "на", "через"):
            remainder = re.sub(rf"\b{trigger}\b", " ", remainder)
        reminder = " ".join(remainder.split())
        return TimerArgs(seconds=seconds, text=reminder)

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, TimerArgs)
        if args.seconds <= 0:
            return SkillResult.failure(
                "Не понял длительность. Скажите, например: таймер на пять минут."
            )
        if args.seconds > 24 * 3600:
            return SkillResult.failure("Слишком долгий таймер, максимум сутки.")

        reminder = args.text
        timer_id = 0
        if self._repository is not None:
            timer_id = self._repository.add(reminder, time.time() + args.seconds)

        timer = threading.Timer(args.seconds, self._fire, args=(reminder, timer_id))
        timer.daemon = True
        with self._lock:
            self._timers = [item for item in self._timers if item.is_alive()]
            self._timers.append(timer)
        timer.start()

        duration = _plural(args.seconds)
        if reminder:
            return SkillResult.success(f"Напоминание через {duration}: {reminder}.")
        return SkillResult.success(f"Таймер на {duration} поставлен.")

    def _fire(self, reminder: str, timer_id: int) -> None:
        if reminder:
            self._speak(f"Напоминаю: {reminder}.")
        else:
            self._speak("Таймер сработал.")
        if self._repository is not None and timer_id:
            self._repository.mark_fired(timer_id)

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers:
                timer.cancel()
            self._timers.clear()
