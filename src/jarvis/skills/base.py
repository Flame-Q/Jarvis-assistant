"""Skill contract and shared matching helpers."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from rapidfuzz import fuzz

from jarvis.core.models import SkillResult

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+", re.UNICODE)


class EmptyArgs(BaseModel):
    """Argument model for skills without parameters."""


def normalize_text(text: str) -> str:
    """Lowercase, unify ё/е and strip punctuation for stable matching."""

    lowered = text.lower().replace("ё", "е")
    cleaned = _PUNCT_RE.sub(" ", lowered)
    return _SPACE_RE.sub(" ", cleaned).strip()


@runtime_checkable
class Skill(Protocol):
    """Every capability of the assistant implements this contract.

    ``name``, ``description`` and ``args_model`` are also used to build the
    JSON schema exposed to the local LLM as a tool.
    """

    name: str
    description: str
    examples: list[str]
    args_model: type[BaseModel]
    requires_confirmation: bool

    def can_handle(self, text: str) -> float: ...

    def extract_args(self, text: str) -> BaseModel: ...

    def execute(self, args: BaseModel) -> SkillResult: ...


class BaseSkill:
    """Default trigger + fuzzy matching used by all concrete skills."""

    name: str = "base"
    description: str = ""
    examples: list[str] = []
    triggers: list[str] = []
    args_model: type[BaseModel] = EmptyArgs
    requires_confirmation: bool = False

    def can_handle(self, text: str) -> float:
        normalized = normalize_text(text)
        if not normalized:
            return 0.0

        tokens = normalized.split()
        best_trigger = 0.0
        for trigger in self.triggers:
            trigger_norm = normalize_text(trigger)
            if not trigger_norm:
                continue
            if trigger_norm in normalized:
                return 1.0
            for token in tokens:
                ratio = fuzz.ratio(trigger_norm, token) / 100.0
                fuzzy_gate = 0.8 if len(trigger_norm) >= 5 else 0.9
                if ratio >= fuzzy_gate:
                    best_trigger = max(best_trigger, 0.9)
        if best_trigger:
            return best_trigger

        best_example = 0.0
        for example in self.examples:
            best_example = max(
                best_example, fuzz.token_set_ratio(normalize_text(example), normalized) / 100.0
            )
        # Examples alone never cross the routing threshold, they only help
        # ranking when several skills are plausible.
        return min(best_example * 0.6, 0.55)

    def extract_args(self, text: str) -> BaseModel:
        return self.args_model()

    def execute(self, args: BaseModel) -> SkillResult:  # pragma: no cover - abstract
        raise NotImplementedError


def strip_triggers(text: str, triggers: list[str]) -> str:
    """Remove a leading trigger phrase ("открой ...", "таймер на ...")."""

    normalized = normalize_text(text)
    for trigger in sorted(triggers, key=len, reverse=True):
        trigger_norm = normalize_text(trigger)
        if normalized == trigger_norm:
            return ""
        if normalized.startswith(trigger_norm + " "):
            return normalized[len(trigger_norm) + 1 :].strip()
    return normalized


def parse_number(token: str) -> int | None:
    """Parse Arabic or common Russian numeral words used in voice commands."""

    words = {
        "ноль": 0,
        "один": 1,
        "одну": 1,
        "два": 2,
        "две": 2,
        "три": 3,
        "четыре": 4,
        "пять": 5,
        "шесть": 6,
        "семь": 7,
        "восемь": 8,
        "девять": 9,
        "десять": 10,
        "пятнадцать": 15,
        "двадцать": 20,
        "тридцать": 30,
        "сорок": 40,
        "пятьдесят": 50,
        "шестьдесят": 60,
        "девяносто": 90,
        "сто": 100,
    }
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return words.get(token)
