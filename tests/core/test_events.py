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
