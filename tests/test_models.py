"""Domain model tests."""

from __future__ import annotations

from jarvis.core.models import LLMResponse, PendingAction, SkillResult, ToolCall, Turn


def test_success_result() -> None:
    result = SkillResult.success("готово", path="a.txt")
    assert result.ok is True
    assert result.text == "готово"
    assert result.data["path"] == "a.txt"
    assert result.speak is True


def test_failure_result() -> None:
    result = SkillResult.failure("ошибка")
    assert result.ok is False
    assert result.text == "ошибка"


def test_llm_response_defaults() -> None:
    response = LLMResponse(text="привет")
    assert response.tool_calls == []
    assert response.model == ""


def test_tool_call_arguments() -> None:
    call = ToolCall(name="weather", arguments={"city": "Москва"})
    assert call.name == "weather"
    assert call.arguments["city"] == "Москва"


def test_turn_timestamp_is_set() -> None:
    turn = Turn(role="user", text="привет")
    assert turn.created_at > 0


def test_pending_action_roundtrip() -> None:
    pending = PendingAction(skill_name="system", args={"action": "shutdown"})
    assert pending.args["action"] == "shutdown"
