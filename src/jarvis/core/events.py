"""Minimal thread-safe event bus (Observer pattern)."""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from loguru import logger

Handler = Callable[..., None]


class EventBus:
    """Synchronous publish/subscribe bus.

    Handlers must be fast and non-blocking; long work belongs in worker
    threads. A failing handler never breaks the publisher.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._handlers.get(topic, []):
                    self._handlers[topic].remove(handler)

        return unsubscribe

    def publish(self, event_topic: str, /, **payload: Any) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event_topic, [])) + list(
                self._handlers.get("*", [])
            )
        for handler in handlers:
            try:
                handler(**payload)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Event handler failed for topic {}", event_topic)

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()

    def topics(self) -> list[str]:
        with self._lock:
            return sorted(self._handlers)
