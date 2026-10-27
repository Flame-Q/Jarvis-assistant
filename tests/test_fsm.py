"""State machine tests."""

from __future__ import annotations

from jarvis.core.events import EventBus
from jarvis.core.fsm import AssistantFSM, State


def test_initial_state_is_idle() -> None:
    fsm = AssistantFSM()
    assert fsm.state is State.IDLE
    assert fsm.history == []


def test_valid_transition_and_history() -> None:
    fsm = AssistantFSM()
    assert fsm.transition(State.ACTIVATED) is True
    assert fsm.transition(State.LISTENING) is True
    assert fsm.state is State.LISTENING
    assert [item[0] for item in fsm.history] == [State.IDLE, State.ACTIVATED]


def test_invalid_transition_is_rejected() -> None:
    fsm = AssistantFSM()
    assert fsm.transition(State.EXECUTING) is False
    assert fsm.state is State.IDLE


def test_force_and_reset_recover_from_error() -> None:
    fsm = AssistantFSM()
    fsm.force(State.ERROR)
    assert fsm.state is State.ERROR
    fsm.reset()
    assert fsm.state is State.IDLE


def test_state_change_is_published() -> None:
    bus = EventBus()
    events: list[tuple[State, State]] = []
    bus.subscribe("state_changed", lambda previous, current: events.append((previous, current)))
    fsm = AssistantFSM(bus)
    fsm.transition(State.ACTIVATED)
    assert events == [(State.IDLE, State.ACTIVATED)]


def test_full_happy_path() -> None:
    fsm = AssistantFSM()
    for state in (
        State.ACTIVATED,
        State.LISTENING,
        State.TRANSCRIBING,
        State.ROUTING,
        State.EXECUTING,
        State.SPEAKING,
        State.IDLE,
    ):
        assert fsm.transition(state), state
