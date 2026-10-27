"""Assistant facade: orchestrates FSM, routing, skills, TTS and the local LLM."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger
from pydantic import BaseModel, ValidationError

from jarvis.config import AppConfig
from jarvis.core.errors import ProviderError
from jarvis.core.events import EventBus
from jarvis.core.fsm import AssistantFSM, State
from jarvis.core.models import PendingAction, RouteResult, SkillResult
from jarvis.core.registry import SkillRegistry
from jarvis.core.router import IntentRouter
from jarvis.providers.llm.base import LLMProvider
from jarvis.providers.tts.base import TTSProvider
from jarvis.skills.base import Skill, normalize_text
from jarvis.skills.chat import ChatSkill
from jarvis.storage.repositories import CommandRepository, HistoryRepository

YES_WORDS = {"да", "ага", "конечно", "подтверждаю", "да подтверждаю", "верно", "yes"}
NO_WORDS = {"нет", "не", "отмена", "отмени", "не надо", "no", "стоп"}
COMMAND_VERBS = {
    "открой",
    "открыть",
    "запусти",
    "запустить",
    "включи",
    "выключи",
    "поставь",
    "напомни",
    "найди",
    "покажи",
    "сделай",
    "переключи",
    "заблокируй",
    "перезагрузи",
    "обнови",
    "запиши",
    "удали",
    "выполни",
    "отправь",
    "позвони",
}


class AssistantService:
    """Single entry point for a user utterance (Facade pattern)."""

    def __init__(
        self,
        *,
        config: AppConfig,
        bus: EventBus,
        fsm: AssistantFSM,
        registry: SkillRegistry,
        router: IntentRouter,
        chat: ChatSkill,
        tts: TTSProvider,
        llm: LLMProvider,
        history: HistoryRepository,
        commands: CommandRepository,
    ) -> None:
        self._config = config
        self._bus = bus
        self._fsm = fsm
        self._registry = registry
        self._router = router
        self._chat = chat
        self._tts = tts
        self._llm = llm
        self._history = history
        self._commands = commands
        self._pending: PendingAction | None = None
        self._llm_ok = False
        self._llm_checked_at = 0.0

    @property
    def fsm(self) -> AssistantFSM:
        return self._fsm

    @property
    def pending(self) -> PendingAction | None:
        return self._pending

    def handle_text(self, text: str) -> SkillResult:
        cleaned = text.strip()
        if not cleaned:
            return SkillResult.failure("Не расслышал команду.")

        self._enter_routing()
        started = time.perf_counter()
        self._history.add_turn("user", cleaned)
        self._bus.publish("user_text", text=cleaned)

        try:
            result = self._dispatch(cleaned)
        except Exception as exc:  # pragma: no cover - last-resort safety net
            logger.exception("Unhandled error while processing utterance")
            result = SkillResult.failure(f"Произошла ошибка: {exc}")

        if result.text:
            self._history.add_turn("assistant", result.text)
            self._bus.publish("assistant_text", text=result.text)
            if result.speak:
                self._tts.speak(result.text)
        logger.info(
            "Handled in {:.3f}s (skill/tool/chat): {}",
            time.perf_counter() - started,
            result.text[:80],
        )
        return result

    def llm_available(self) -> bool:
        now = time.time()
        if now - self._llm_checked_at > 15:
            self._llm_ok = self._llm.health()
            self._llm_checked_at = now
        return self._llm_ok

    def status(self) -> dict[str, Any]:
        return {
            "state": self._fsm.state.value,
            "llm": self.llm_available(),
            "model": self._config.llm.model,
            "pending": self._pending.skill_name if self._pending else None,
        }

    # -- internals -------------------------------------------------------

    def _dispatch(self, text: str) -> SkillResult:
        if self._pending is not None:
            return self._handle_confirmation(text)

        match = self._router.route(text)
        if match is not None:
            logger.info("Routed to {} (score {:.2f})", match.skill.name, match.score)
            return self._run_skill(match)

        return self._llm_answer(text)

    def _enter_routing(self) -> None:
        if self._fsm.state == State.TRANSCRIBING:
            self._fsm.transition(State.ROUTING)
            return
        if self._fsm.state not in (State.IDLE, State.MUTED):
            self._fsm.force(State.IDLE)
        if self._fsm.state == State.MUTED:
            self._fsm.transition(State.IDLE)
        self._fsm.transition(State.ROUTING)

    def _finish(self, result: SkillResult) -> SkillResult:
        self._sync_state(State.SPEAKING)
        self._sync_state(State.IDLE)
        return result

    def _sync_state(self, target: State) -> None:
        if self._fsm.state == target:
            return
        if not self._fsm.transition(target):
            self._fsm.force(target)

    def _run_skill(self, match: RouteResult) -> SkillResult:
        skill: Skill = match.skill
        args: BaseModel = match.args
        if self._needs_confirmation(skill, args):
            self._pending = PendingAction(
                skill_name=skill.name, args=args.model_dump(), prompt=text_of(skill, args)
            )
            return self._finish(SkillResult.success(self._confirmation_prompt(skill, args)))
        return self._execute(skill, args)

    def _execute(self, skill: Skill, args: BaseModel) -> SkillResult:
        if self._fsm.state != State.EXECUTING:
            self._sync_state(State.EXECUTING)
        try:
            result = skill.execute(args)
        except Exception as exc:
            logger.exception("Skill {} failed", skill.name)
            result = SkillResult.failure(f"Навык {skill.name} не смог выполнить команду: {exc}")
        status = "ok" if result.ok else "failed"
        try:
            self._commands.log(skill.name, args.model_dump(), status)
        except Exception:  # pragma: no cover - logging must never break the flow
            logger.exception("Cannot write command log")
        return self._finish(result)

    def _llm_answer(self, text: str) -> SkillResult:
        self._sync_state(State.THINKING)
        if not self.llm_available():
            return self._finish(
                SkillResult.failure(
                    "Локальная модель недоступна. Команды работают, но чат временно нет."
                )
            )

        if not self._looks_like_command(text):
            return self._stream_chat(text)

        try:
            response = self._chat.ask_with_tools(text, self._registry.tool_schemas())
        except ProviderError as exc:
            return self._finish(SkillResult.failure(str(exc)))

        for call in response.tool_calls:
            skill = self._registry.get(call.name)
            if skill is None:
                logger.warning("Model requested unknown tool {}", call.name)
                continue
            try:
                args = skill.args_model.model_validate(call.arguments)
            except ValidationError:
                logger.warning("Invalid arguments for {}: {}", call.name, call.arguments)
                continue
            if self._needs_confirmation(skill, args):
                self._pending = PendingAction(
                    skill_name=skill.name, args=args.model_dump(), prompt=text_of(skill, args)
                )
                return self._finish(
                    SkillResult.success(self._confirmation_prompt(skill, args))
                )
            return self._execute(skill, args)

        if response.text:
            return self._finish(SkillResult.success(response.text))
        return self._finish(SkillResult.failure("Не понял вопрос. Переформулируйте, пожалуйста."))

    def _stream_chat(self, text: str) -> SkillResult:
        """Speak the answer sentence by sentence while the model is generating."""

        parts: list[str] = []
        try:
            for sentence in self._chat.stream(text):
                if not sentence:
                    continue
                parts.append(sentence)
                self._tts.speak(sentence)
                self._sync_state(State.SPEAKING)
        except ProviderError as exc:
            if parts:
                return self._finish(SkillResult(ok=True, text=" ".join(parts), speak=False))
            return self._finish(SkillResult.failure(str(exc)))

        answer = " ".join(parts).strip()
        if not answer:
            return self._finish(SkillResult.failure("Модель не дала ответа."))
        return self._finish(SkillResult(ok=True, text=answer, speak=False))

    @staticmethod
    def _looks_like_command(text: str) -> bool:
        normalized = normalize_text(text)
        if not normalized:
            return False
        first = normalized.split()[0]
        return first in COMMAND_VERBS

    def _handle_confirmation(self, text: str) -> SkillResult:
        normalized = normalize_text(text)
        if normalized in YES_WORDS or normalized.startswith("да "):
            pending = self._pending
            self._pending = None
            assert pending is not None
            skill = self._registry.get(pending.skill_name)
            if skill is None:
                return self._finish(SkillResult.failure("Команда больше недоступна."))
            try:
                args = skill.args_model.model_validate(pending.args)
            except ValidationError:
                return self._finish(SkillResult.failure("Не удалось восстановить параметры команды."))
            return self._execute(skill, args)

        if normalized in NO_WORDS or normalized.startswith("нет "):
            self._pending = None
            return self._finish(SkillResult.success("Отменено."))

        return self._finish(SkillResult.success("Подтвердите, пожалуйста: да или нет."))

    @staticmethod
    def _needs_confirmation(skill: Skill, args: BaseModel) -> bool:
        checker = getattr(skill, "needs_confirmation", None)
        if callable(checker):
            return bool(checker(args))
        return bool(skill.requires_confirmation)

    @staticmethod
    def _confirmation_prompt(skill: Skill, args: BaseModel) -> str:
        builder = getattr(skill, "confirmation_prompt", None)
        if callable(builder):
            return str(builder(args))
        return f"Подтвердите действие: {skill.description}. Скажите да или нет."


def text_of(skill: Skill, args: BaseModel) -> str:
    return f"{skill.name}:{args.model_dump()}"
