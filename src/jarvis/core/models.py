"""Domain models shared by application and infrastructure layers."""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


class SkillResult(BaseModel):
    """Uniform result returned by every skill."""

    ok: bool = True
    text: str = ""
    speak: bool = True
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def success(cls, text: str, **data: Any) -> SkillResult:
        return cls(ok=True, text=text, data=data)

    @classmethod
    def failure(cls, text: str, **data: Any) -> SkillResult:
        return cls(ok=False, text=text, data=data)


class Turn(BaseModel):
    role: Role
    text: str
    created_at: float = Field(default_factory=time.time)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str = ""


class SkillMatch(BaseModel):
    skill_name: str
    score: float
    args: dict[str, Any] = Field(default_factory=dict)


class RouteResult(BaseModel):
    """Outcome of deterministic intent routing."""

    skill: Any
    args: BaseModel
    score: float

    model_config = {"arbitrary_types_allowed": True}


class PendingAction(BaseModel):
    skill_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    prompt: str = ""
