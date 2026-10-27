"""Conversation with the local LLM (fallback stage of the hybrid NLU)."""

from __future__ import annotations

import re
from collections.abc import Iterator

from jarvis.config import AppConfig
from jarvis.core.errors import ProviderError
from jarvis.core.models import LLMResponse, SkillResult
from jarvis.providers.llm.base import LLMProvider, Message
from jarvis.storage.repositories import HistoryRepository

SYSTEM_PROMPT = (
    "Ты — Джарвис, голосовой ассистент на персональном компьютере. "
    "Отвечай по-русски, кратко: одно или два предложения, без списков, markdown и эмодзи, "
    "потому что твой ответ будет произнесён вслух. "
    "Числа, даты и единицы измерения записывай словами, если это звучит естественно. "
    "Если не знаешь ответ, честно скажи «не знаю» и не выдумывай факты. "
    "Если вопрос требует действия на компьютере, а подходящего инструмента нет, "
    "объясни это коротко."
)


class ChatSkill:
    """Not registered as a command: it is the assistant's fallback."""

    name = "chat"

    def __init__(
        self,
        config: AppConfig,
        llm: LLMProvider,
        history: HistoryRepository,
    ) -> None:
        self._config = config
        self._llm = llm
        self._history = history

    def _messages(self, text: str) -> list[Message]:
        messages: list[Message] = [{"role": "system", "content": SYSTEM_PROMPT}]
        turns = self._history.recent(limit=self._config.llm.history_turns)
        for turn in turns:
            if turn.role in {"user", "assistant"}:
                messages.append({"role": turn.role, "content": turn.text})
        if not turns or turns[-1].text.strip() != text.strip():
            messages.append({"role": "user", "content": text})
        return messages

    def answer(self, text: str) -> SkillResult:
        try:
            response = self._llm.chat(
                self._messages(text), temperature=self._config.llm.temperature_chat
            )
        except ProviderError as exc:
            return SkillResult.failure(str(exc))
        if not response.text:
            return SkillResult.failure("Модель не дала ответа.")
        return SkillResult.success(response.text)

    def ask_with_tools(self, text: str, tools: list[dict]) -> LLMResponse:
        return self._llm.chat(
            self._messages(text),
            temperature=self._config.llm.temperature_tools,
            tools=tools or None,
        )

    def stream(self, text: str) -> Iterator[str]:
        """Yield complete sentences so TTS can start before the answer ends."""

        buffer = ""
        for delta in self._llm.chat_stream(self._messages(text)):
            buffer += delta
            while True:
                match = re.search(r"([.!?…])\s+", buffer)
                if match is None:
                    break
                sentence = buffer[: match.end()].strip()
                buffer = buffer[match.end() :]
                if sentence:
                    yield sentence
        if buffer.strip():
            yield buffer.strip()
