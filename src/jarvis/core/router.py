"""Deterministic intent routing (first stage of the hybrid NLU)."""

from __future__ import annotations

from jarvis.core.models import RouteResult
from jarvis.core.registry import SkillRegistry
from jarvis.skills.base import Skill, normalize_text


class IntentRouter:
    """Pick the most confident skill above a threshold.

    Deterministic matching is intentionally the first stage: it is fast,
    predictable and works fully offline. The LLM is only consulted when
    nothing matches.
    """

    def __init__(self, registry: SkillRegistry, threshold: float = 0.65) -> None:
        self._registry = registry
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def route(self, text: str) -> RouteResult | None:
        if not normalize_text(text):
            return None

        best: tuple[Skill, float] | None = None
        for skill in self._registry.all():
            score = skill.can_handle(text)
            if best is None or score > best[1]:
                best = (skill, score)

        if best is None or best[1] < self._threshold:
            return None

        skill, score = best
        args = skill.extract_args(text)
        return RouteResult(skill=skill, args=args, score=score)
