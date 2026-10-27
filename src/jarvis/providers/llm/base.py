"""LLM provider interfaces."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from jarvis.core.models import LLMResponse

Message = dict[str, str]


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def health(self) -> bool: ...

    def warmup(self) -> bool: ...

    def chat(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        tools: list[dict] | None = None,
    ) -> LLMResponse: ...

    def chat_stream(
        self, messages: list[Message], *, temperature: float | None = None
    ) -> Iterator[str]: ...

    def close(self) -> None: ...
