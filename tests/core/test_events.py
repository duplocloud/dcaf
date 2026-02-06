# tests/core/test_events.py
"""Tests for the unified Event class."""

import pytest
from datetime import datetime


def test_event_creation():
    """Event can be created with type and data."""
    from dcaf.core.events import Event

    event = Event(
        type="tool_call_started",
        data={"tool_name": "weather", "tool_call_id": "abc123"}
    )

    assert event.type == "tool_call_started"
    assert event.data["tool_name"] == "weather"
    assert event.data["tool_call_id"] == "abc123"
    assert isinstance(event.timestamp, datetime)


def test_event_tool_name_accessor():
    """Event provides convenient accessor for tool_name."""
    from dcaf.core.events import Event

    event = Event(
        type="tool_call_started",
        data={"tool_name": "weather"}
    )

    assert event.tool_name == "weather"


def test_event_tool_name_accessor_returns_none_when_missing():
    """Event.tool_name returns None when not present."""
    from dcaf.core.events import Event

    event = Event(type="text_delta", data={"text": "hello"})

    assert event.tool_name is None


def test_event_text_accessor():
    """Event provides convenient accessor for text."""
    from dcaf.core.events import Event

    event = Event(type="text_delta", data={"text": "Hello world"})

    assert event.text == "Hello world"


def test_event_text_accessor_returns_none_when_missing():
    """Event.text returns None when not present."""
    from dcaf.core.events import Event

    event = Event(type="tool_call_started", data={"tool_name": "weather"})

    assert event.text is None


def test_event_registry_subscribe():
    """Can subscribe a handler to an event type."""
    from dcaf.core.events import EventRegistry

    registry = EventRegistry()

    async def my_handler(event):
        pass

    registry.subscribe("tool_call_started", my_handler)

    assert registry.has_subscribers("tool_call_started")
    assert not registry.has_subscribers("text_delta")


def test_event_registry_subscribe_multiple_types():
    """Can subscribe a handler to multiple event types."""
    from dcaf.core.events import EventRegistry

    registry = EventRegistry()

    async def my_handler(event):
        pass

    registry.subscribe("tool_call_started", my_handler)
    registry.subscribe("tool_call_completed", my_handler)

    assert registry.has_subscribers("tool_call_started")
    assert registry.has_subscribers("tool_call_completed")


def test_event_registry_get_handlers():
    """Can retrieve handlers for an event type."""
    from dcaf.core.events import EventRegistry

    registry = EventRegistry()

    async def handler1(event):
        pass

    async def handler2(event):
        pass

    registry.subscribe("tool_call_started", handler1)
    registry.subscribe("tool_call_started", handler2)

    handlers = registry.get_handlers("tool_call_started")

    assert len(handlers) == 2
    assert handler1 in handlers
    assert handler2 in handlers


def test_event_registry_get_handlers_returns_empty_for_no_subscribers():
    """get_handlers returns empty list when no subscribers."""
    from dcaf.core.events import EventRegistry

    registry = EventRegistry()

    handlers = registry.get_handlers("nonexistent_event")

    assert handlers == []
