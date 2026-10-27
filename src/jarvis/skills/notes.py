"""Voice notes stored in SQLite."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from jarvis.core.errors import SkillError
from jarvis.core.models import SkillResult
from jarvis.skills.base import BaseSkill, normalize_text
from jarvis.storage.repositories import NotesRepository


class NotesArgs(BaseModel):
    action: Literal["add", "list"] = "add"
    text: str = ""


class NotesSkill(BaseSkill):
    name = "notes"
    description = "Записать заметку или прочитать список текущих дел."
    examples = ["запиши заметку купить хлеб", "что у меня на сегодня"]
    triggers = ["заметка", "заметку", "запиши", "список дел", "что на сегодня", "мои дела"]
    args_model: type[BaseModel] = NotesArgs

    def __init__(self, repository: NotesRepository) -> None:
        self._repository = repository

    def extract_args(self, text: str) -> NotesArgs:
        normalized = normalize_text(text)
        if any(
            phrase in normalized
            for phrase in ("что на сегодня", "список дел", "мои дела", "покажи заметки")
        ):
            return NotesArgs(action="list")
        value = re.sub(r"\b(запиши|заметку|заметка|добавь)\b", " ", normalized)
        return NotesArgs(action="add", text=" ".join(value.split()))

    def execute(self, args: BaseModel) -> SkillResult:
        assert isinstance(args, NotesArgs)
        if args.action == "list":
            notes = self._repository.pending(limit=10)
            if not notes:
                return SkillResult.success("Список дел пуст.")
            lines = [f"{index}. {note['text']}" for index, note in enumerate(notes, 1)]
            return SkillResult.success("Ваши дела: " + "; ".join(lines) + ".")

        if not args.text:
            return SkillResult.failure("Что записать?")
        try:
            self._repository.add(args.text)
        except Exception as exc:  # pragma: no cover - sqlite failure
            raise SkillError(f"Не удалось сохранить заметку: {exc}") from exc
        return SkillResult.success(f"Записал: {args.text}.")
