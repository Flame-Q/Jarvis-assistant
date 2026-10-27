"""Event bus tests."""

from __future__ import annotations

from jarvis.core.events import EventBus


def test_publish_delivers_payload() -> None:
    bus = EventBus()
    received: list[str] = []
    bus.subscribe("greeting", lambda text: received.append(text))
    bus.publish("greeting", text="привет")
    assert received == ["привет"]


def test_wildcard_receives_everything() -> None:
    bus = EventBus()
    topics: list[str] = []

    def handler(**payload: object) -> None:
        topics.append(str(payload.get("topic", "?")))

    bus.subscribe("*", handler)
    bus.publish("one", topic="one")
    bus.publish("two", topic="two")
    assert topics == ["one", "two"]


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[int] = []
    unsubscribe = bus.subscribe("n", lambda value: received.append(value))
    bus.publish("n", value=1)
    unsubscribe()
    bus.publish("n", value=2)
    assert received == [1]


def test_failing_handler_does_not_break_others() -> None:
    bus = EventBus()
    received: list[str] = []

    def broken() -> None:
        raise RuntimeError("boom")

    bus.subscribe("topic", broken)
    bus.subscribe("topic", lambda: received.append("ok"))
    bus.publish("topic")
    assert received == ["ok"]


def test_topics_and_clear() -> None:
    bus = EventBus()
    bus.subscribe("a", lambda: None)
    bus.subscribe("b", lambda: None)
    assert bus.topics() == ["a", "b"]
    bus.clear()
    assert bus.topics() == []
