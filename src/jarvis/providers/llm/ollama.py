"""Local LLM provider backed by Ollama's OpenAI-compatible API."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any, cast

import httpx
from loguru import logger
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from jarvis.config import LLMSettings
from jarvis.core.errors import OllamaUnavailable, ProviderError
from jarvis.core.models import LLMResponse, ToolCall
from jarvis.providers.llm.base import Message


class OllamaProvider:
    """Talks to a locally running Ollama instance. No API key is required."""

    name = "ollama"

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings
        self._base_url = settings.base_url.rstrip("/")
        self._client = OpenAI(
            base_url=f"{self._base_url}/v1",
            api_key="ollama",
            timeout=settings.timeout_s,
            max_retries=1,
        )

    @property
    def model(self) -> str:
        return self._settings.model

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def models(self) -> list[str]:
        try:
            response = httpx.get(f"{self._base_url}/api/tags", timeout=3.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnavailable(f"Ollama is not reachable: {exc}") from exc
        payload = response.json()
        return [item.get("name", "") for item in payload.get("models", [])]

    def warmup(self) -> bool:
        if not self.health():
            return False
        try:
            self.chat([{"role": "user", "content": "ping"}], temperature=0.0)
            return True
        except ProviderError:
            logger.warning("Ollama warmup failed")
            return False

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": (
                self._settings.temperature_chat if temperature is None else temperature
            ),
            "stream": False,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["temperature"] = self._settings.temperature_tools

        try:
            completion = self._client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            raise ProviderError("Локальная модель не ответила вовремя.") from exc
        except APIConnectionError as exc:
            raise OllamaUnavailable("Локальная модель недоступна.") from exc
        except APIStatusError as exc:
            raise ProviderError(f"Ошибка модели: {exc.status_code}") from exc

        if not completion.choices:
            return LLMResponse(text="", model=self._settings.model)

        message = completion.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                logger.warning("Model returned invalid tool arguments: {}", call.function.arguments)
                continue
            if isinstance(arguments, dict):
                tool_calls.append(ToolCall(name=call.function.name, arguments=arguments))

        return LLMResponse(
            text=(message.content or "").strip(),
            tool_calls=tool_calls,
            model=self._settings.model,
        )

    def chat_stream(
        self, messages: list[Message], *, temperature: float | None = None
    ) -> Iterator[str]:
        try:
            stream = cast(
                Iterable[Any],
                self._client.chat.completions.create(
                    model=self._settings.model,
                    messages=cast(Any, messages),
                    temperature=(
                        self._settings.temperature_chat if temperature is None else temperature
                    ),
                    stream=True,
                ),
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except APIConnectionError as exc:
            raise OllamaUnavailable("Локальная модель недоступна.") from exc
        except APITimeoutError as exc:
            raise ProviderError("Локальная модель не ответила вовремя.") from exc
        except APIStatusError as exc:
            raise ProviderError(f"Ошибка модели: {exc.status_code}") from exc

    def close(self) -> None:
        self._client.close()
