"""Assistant finite state machine (State pattern)."""

from __future__ import annotations

import threading
import time
from enum import Enum

from loguru import logger

from jarvis.core.events import EventBus


class State(str, Enum):
    IDLE = "idle"
    ACTIVATED = "activated"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    ROUTING = "routing"
    EXECUTING = "executing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"
    MUTED = "muted"


ALLOWED: dict[State, set[State]] = {
    State.IDLE: {State.ACTIVATED, State.ROUTING, State.SPEAKING, State.MUTED, State.ERROR},
    State.ACTIVATED: {State.LISTENING, State.IDLE, State.ERROR},
    State.LISTENING: {State.TRANSCRIBING, State.IDLE, State.ERROR},
    State.TRANSCRIBING: {State.ROUTING, State.IDLE, State.ERROR},
    State.ROUTING: {State.EXECUTING, State.THINKING, State.SPEAKING, State.IDLE, State.ERROR},
    State.EXECUTING: {State.SPEAKING, State.IDLE, State.ERROR},
    State.THINKING: {State.SPEAKING, State.EXECUTING, State.IDLE, State.ERROR},
    State.SPEAKING: {State.IDLE, State.ACTIVATED, State.MUTED, State.ERROR},
    State.ERROR: {State.IDLE, State.MUTED},
    State.MUTED: {State.IDLE, State.ROUTING, State.ACTIVATED},
}


class AssistantFSM:
    """Thread-safe state machine that publishes ``state_changed`` events."""

    def __init__(self, bus: EventBus | None = None, initial: State = State.IDLE) -> None:
        self._state = initial
        self._lock = threading.RLock()
        self._bus = bus
        self._history: list[tuple[State, State, float]] = []

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    @property
    def history(self) -> list[tuple[State, State, float]]:
        with self._lock:
            return list(self._history)

    def can_transition(self, target: State) -> bool:
        with self._lock:
            return target in ALLOWED[self._state]

    def transition(self, target: State) -> bool:
        with self._lock:
            if target not in ALLOWED[self._state]:
                logger.warning("Invalid transition {} -> {}", self._state.value, target.value)
                return False
            previous, self._state = self._state, target
            self._history.append((previous, target, time.time()))
        if self._bus is not None:
            self._bus.publish("state_changed", previous=previous, current=target)
        return True

    def force(self, target: State) -> None:
        """Recover from an unexpected state (used on errors and shutdown)."""

        with self._lock:
            previous, self._state = self._state, target
            self._history.append((previous, target, time.time()))
        if self._bus is not None:
            self._bus.publish("state_changed", previous=previous, current=target)

    def reset(self) -> None:
        self.force(State.IDLE)
