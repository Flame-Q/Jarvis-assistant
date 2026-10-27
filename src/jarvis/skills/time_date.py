"""Current time and date."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text

MONTHS = (
    "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
)
WEEKDAYS = "понедельник вторник среда четверг пятница суббота воскресенье".split()


class TimeDateArgs(BaseModel):
    kind: Literal["time", "date"] = "time"


class TimeDateSkill(BaseSkill):
    name = "time_date"
    description = "Сообщить текущее время или сегодняшнюю дату."
    examples = ["который час", "сколько времени", "какое сегодня число"]
    triggers = ["который час", "сколько времени", "время", "дата", "какое число"]
    args_model: type[BaseModel] = TimeDateArgs

    def can_handle(self, text: str) -> float:
        normalized = normalize_text(text)
        if "который час" in normalized or "сколько времени" in normalized:
            return 1.0
        if "дата" in normalized or "какое число" in normalized:
            return 1.0
        # Bare "время" is ambiguous ("во сколько время"), keep it weaker.
        if normalized.startswith("время") or normalized in {"время"}:
            return 0.8
        return 0.0

    def extract_args(self, text: str) -> TimeDateArgs:
        normalized = normalize_text(text)
        if "дата" in normalized or "число" in normalized:
            return TimeDateArgs(kind="date")
        return TimeDateArgs(kind="time")

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, TimeDateArgs)
        now = datetime.now()
        if args.kind == "date":
            text = (
                f"Сегодня {now.day} {MONTHS[now.month - 1]} {now.year} года, "
                f"{WEEKDAYS[now.weekday()]}."
            )
        else:
            text = f"Сейчас {now.hour} часов {now.minute:02d} минут."
        return SkillResult.success(text)
