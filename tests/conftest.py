"""Shared fixtures and fakes for unit tests (no microphone, no network)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from jarvis.config import AppConfig
from jarvis.core.assistant import AssistantService
from jarvis.core.events import EventBus
from jarvis.core.fsm import AssistantFSM
from jarvis.core.models import LLMResponse, SkillResult, ToolCall
from jarvis.core.registry import SkillRegistry
from jarvis.core.router import IntentRouter
from jarvis.skills.chat import ChatSkill
from jarvis.storage.db import Database
from jarvis.storage.repositories import CommandRepository, HistoryRepository


class FakeLLM:
    name = "fake"

    def __init__(
        self,
        text: str = "ответ модели",
        *,
        healthy: bool = True,
        tool_calls: list[ToolCall] | None = None,
    ) -> None:
        self.text = text
        self.healthy = healthy
        self.tool_calls = tool_calls or []
        self.calls: list[list[dict[str, str]]] = []

    def health(self) -> bool:
        return self.healthy

    def chat(self, messages, *, temperature=None, tools=None) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(text=self.text, tool_calls=self.tool_calls, model="fake")

    def chat_stream(self, messages, *, temperature=None) -> Iterator[str]:
        self.calls.append(messages)
        yield self.text

    def close(self) -> None:
        pass


class FakeTTS:
    name = "fake"

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.available = True
        self.is_speaking = False
        self.stop_calls = 0

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.stop_calls += 1

    def close(self) -> None:
        pass


@pytest.fixture()
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture()
def db(tmp_path) -> Iterator[Database]:
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def make_assistant(
    skills: list,
    *,
    config: AppConfig | None = None,
    llm: FakeLLM | None = None,
    tts: FakeTTS | None = None,
    db: Database | None = None,
) -> tuple[AssistantService, FakeTTS, FakeLLM, HistoryRepository, SkillRegistry]:
    config = config or AppConfig()
    fake_tts = tts or FakeTTS()
    fake_llm = llm or FakeLLM()
    database = db or Database(Path(":memory:"))
    history = HistoryRepository(database)
    commands = CommandRepository(database)
    bus = EventBus()
    fsm = AssistantFSM(bus)
    registry = SkillRegistry()
    for skill in skills:
        registry.register(skill)
    router = IntentRouter(registry)
    chat = ChatSkill(config, fake_llm, history)
    assistant = AssistantService(
        config=config,
        bus=bus,
        fsm=fsm,
        registry=registry,
        router=router,
        chat=chat,
        tts=fake_tts,
        llm=fake_llm,
        history=history,
        commands=commands,
    )
    return assistant, fake_tts, fake_llm, history, registry


@pytest.fixture()
def assistant_factory(db):
    def factory(skills: list, **kwargs):
        return make_assistant(skills, db=db, **kwargs)

    return factory


class StaticSkill:
    """Minimal skill used across tests."""

    def __init__(
        self,
        name: str = "echo",
        *,
        triggers: list[str] | None = None,
        text: str = "готово",
        requires_confirmation: bool = False,
        args_model=None,
    ) -> None:
        from jarvis.skills.base import EmptyArgs

        self.name = name
        self.description = "тестовый навык"
        self.examples = triggers or ["тест"]
        self.triggers = triggers or ["тест"]
        self.args_model = args_model or EmptyArgs
        self.requires_confirmation = requires_confirmation
        self.text = text
        self.executed = 0
        self.last_args = None

    def can_handle(self, text: str) -> float:
        return 1.0 if any(trigger in text.lower() for trigger in self.triggers) else 0.0

    def extract_args(self, text: str):
        return self.args_model()

    def execute(self, args) -> SkillResult:
        self.executed += 1
        self.last_args = args
        return SkillResult.success(self.text)
