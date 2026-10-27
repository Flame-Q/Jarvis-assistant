"""Skill storage and JSON-schema generation for LLM tools."""

from __future__ import annotations

from typing import Any

from jarvis.skills.base import Skill


class SkillRegistry:
    """Registry/Factory for skills (Command pattern container)."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill, *, replace: bool = False) -> None:
        if not replace and skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def names(self) -> list[str]:
        return list(self._skills)

    def __len__(self) -> int:
        return len(self._skills)

    def tool_schemas(self) -> list[dict[str, Any]]:
        """Build an OpenAI-compatible tool list from skill argument models."""

        tools: list[dict[str, Any]] = []
        for skill in self._skills.values():
            schema = skill.args_model.model_json_schema()
            schema.pop("title", None)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": skill.name,
                        "description": skill.description,
                        "parameters": schema,
                    },
                }
            )
        return tools
