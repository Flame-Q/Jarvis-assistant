"""Assistant orchestration tests with fakes (no audio, no network)."""

from __future__ import annotations

from pydantic import BaseModel

from conftest import FakeLLM, StaticSkill
from jarvis.core.models import ToolCall
from jarvis.storage.db import Database


def test_rule_skill_executes_and_is_spoken(assistant_factory, db: Database) -> None:
    skill = StaticSkill(triggers=["тест"], text="эхо")
    assistant, tts, _, history, _ = assistant_factory([skill])

    result = assistant.handle_text("тест команда")

    assert result.ok is True
    assert result.text == "эхо"
    assert skill.executed == 1
    assert tts.spoken == ["эхо"]
    assert [turn.text for turn in history.recent(10)] == ["тест команда", "эхо"]


def test_unknown_phrase_goes_to_llm(assistant_factory) -> None:
    llm = FakeLLM(text="Питон — это язык программирования.", healthy=True)
    assistant, tts, _, _, _ = assistant_factory([], llm=llm)

    result = assistant.handle_text("расскажи про питон")

    assert result.text.startswith("Питон")
    assert tts.spoken == [result.text]
    assert llm.calls, "LLM must be called for unmatched phrases"


def test_chat_response_is_streamed_by_sentences(assistant_factory) -> None:
    llm = FakeLLM(text="Первое предложение. Второе предложение.", healthy=True)
    assistant, tts, _, _, _ = assistant_factory([], llm=llm)

    result = assistant.handle_text("расскажи интересное")

    assert tts.spoken == ["Первое предложение.", "Второе предложение."]
    assert result.speak is False
    assert "Первое" in result.text and "Второе" in result.text


def test_unavailable_llm_degrades_gracefully(assistant_factory) -> None:
    llm = FakeLLM(healthy=False)
    assistant, _, _, _, _ = assistant_factory([], llm=llm)

    result = assistant.handle_text("расскажи про питон")

    assert result.ok is False
    assert "недоступна" in result.text.lower()


def test_llm_tool_call_is_validated_and_executed(assistant_factory) -> None:
    skill = StaticSkill(name="echo", triggers=["никогда"], text="через инструмент")
    llm = FakeLLM(text="", tool_calls=[ToolCall(name="echo", arguments={})])
    assistant, _, _, _, _ = assistant_factory([skill], llm=llm)

    result = assistant.handle_text("сделай что нибудь полезное")

    assert result.text == "через инструмент"
    assert skill.executed == 1


def test_invalid_tool_arguments_fall_back_to_text(assistant_factory) -> None:
    class StrictArgs(BaseModel):
        count: int

    skill = StaticSkill(triggers=["никогда"], args_model=StrictArgs)
    llm = FakeLLM(
        text="Не понял, уточните.",
        tool_calls=[ToolCall(name="echo", arguments={"count": "много"})],
    )
    assistant, _, _, _, _ = assistant_factory([skill], llm=llm)

    result = assistant.handle_text("сделай что нибудь")

    assert result.text == "Не понял, уточните."
    assert skill.executed == 0


def test_confirmation_flow_yes(assistant_factory) -> None:
    skill = StaticSkill(triggers=["удали"], text="удалено", requires_confirmation=True)
    assistant, _, _, _, _ = assistant_factory([skill])

    first = assistant.handle_text("удали файл")
    assert "Подтвердите" in first.text
    assert skill.executed == 0
    assert assistant.pending is not None

    second = assistant.handle_text("да")
    assert second.text == "удалено"
    assert skill.executed == 1
    assert assistant.pending is None


def test_confirmation_flow_no(assistant_factory) -> None:
    skill = StaticSkill(triggers=["удали"], text="удалено", requires_confirmation=True)
    assistant, _, _, _, _ = assistant_factory([skill])

    assistant.handle_text("удали файл")
    result = assistant.handle_text("нет")

    assert result.text == "Отменено."
    assert skill.executed == 0


def test_unknown_reply_keeps_pending(assistant_factory) -> None:
    skill = StaticSkill(triggers=["удали"], requires_confirmation=True)
    assistant, _, _, _, _ = assistant_factory([skill])

    assistant.handle_text("удали файл")
    result = assistant.handle_text("может быть")

    assert "да или нет" in result.text
    assert assistant.pending is not None


def test_empty_text_is_rejected(assistant_factory) -> None:
    assistant, _, _, _, _ = assistant_factory([])
    result = assistant.handle_text("   ")
    assert result.ok is False


def test_status_reports_state_and_llm(assistant_factory) -> None:
    llm = FakeLLM(healthy=True)
    assistant, _, _, _, _ = assistant_factory([], llm=llm)
    status = assistant.status()
    assert status["state"] == "idle"
    assert status["llm"] is True
    assert status["model"]


def test_stop_stops_speech_without_llm(assistant_factory) -> None:
    from conftest import FakeTTS
    from jarvis.skills.control import ControlSkill

    shutdown_requested: list[bool] = []
    tts = FakeTTS()
    control = ControlSkill(tts, lambda: shutdown_requested.append(True))
    assistant, tts_out, llm, _, _ = assistant_factory([control], tts=tts)

    result = assistant.handle_text("стоп")

    assert result.ok is True
    assert result.speak is False
    assert tts_out.stop_calls == 1
    assert shutdown_requested == []
    assert llm.calls == []


def test_shutdown_command_sets_event(assistant_factory) -> None:
    from conftest import FakeTTS
    from jarvis.skills.control import ControlSkill

    requested: list[bool] = []
    tts = FakeTTS()
    control = ControlSkill(tts, lambda: requested.append(True))
    assistant, tts_out, _, _, _ = assistant_factory([control], tts=tts)

    result = assistant.handle_text("заверши работу")

    assert "Завершаю" in result.text
    assert requested == [True]
    assert tts_out.stop_calls == 1
