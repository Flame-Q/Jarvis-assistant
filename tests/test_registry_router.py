"""Registry and router tests."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from conftest import StaticSkill
from jarvis.core.registry import SkillRegistry
from jarvis.core.router import IntentRouter
from jarvis.skills.base import BaseSkill


class TargetArgs(BaseModel):
    target: str = ""


class TargetSkill(BaseSkill):
    name = "target"
    description = "open a target"
    examples = ["открой дискорд"]
    triggers = ["открой"]
    args_model = TargetArgs


def test_register_get_and_duplicates() -> None:
    registry = SkillRegistry()
    skill = StaticSkill(name="echo")
    registry.register(skill)
    assert registry.get("echo") is skill
    assert registry.names() == ["echo"]
    assert len(registry) == 1

    with pytest.raises(ValueError):
        registry.register(skill)


def test_register_with_replace() -> None:
    registry = SkillRegistry()
    first = StaticSkill(name="echo")
    second = StaticSkill(name="echo", text="новый")
    registry.register(first)
    registry.register(second, replace=True)
    assert registry.get("echo") is second


def test_tool_schema_contains_arguments() -> None:
    registry = SkillRegistry()
    registry.register(TargetSkill())
    schemas = registry.tool_schemas()
    assert len(schemas) == 1
    function = schemas[0]["function"]
    assert function["name"] == "target"
    assert "target" in function["parameters"]["properties"]


def test_router_matches_trigger_and_extracts_args() -> None:
    registry = SkillRegistry()
    registry.register(TargetSkill())
    router = IntentRouter(registry)
    result = router.route("открой дискорд")
    assert result is not None
    assert result.skill.name == "target"
    assert result.score == 1.0


def test_router_returns_none_below_threshold() -> None:
    registry = SkillRegistry()
    registry.register(TargetSkill())
    router = IntentRouter(registry)
    assert router.route("расскажи анекдот") is None


def test_router_ignores_empty_text() -> None:
    registry = SkillRegistry()
    registry.register(TargetSkill())
    router = IntentRouter(registry)
    assert router.route("   ") is None


def test_trigger_typo_is_tolerated() -> None:
    registry = SkillRegistry()
    registry.register(TargetSkill())
    router = IntentRouter(registry)
    result = router.route("аткрой дискорд")
    assert result is not None
    assert result.score >= 0.9
