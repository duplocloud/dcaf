"""Tests for the WebSocket /api/chat-ws endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dcaf.core import create_app
from dcaf.core.schemas.events import DoneEvent, TextDeltaEvent
from dcaf.core.schemas.messages import AgentMessage

# ---------------------------------------------------------------------------
# Mock agents
# ---------------------------------------------------------------------------


class SyncMockAgent:
    """Synchronous agent that yields a text delta then done."""

    def invoke(self, _messages: dict[str, Any]) -> AgentMessage:
        return AgentMessage(role="assistant", content="hello")

    def invoke_stream(self, _messages: dict[str, Any]) -> Iterator[Any]:
        yield TextDeltaEvent(text="hello")
        yield DoneEvent()


class AsyncMockAgent:
    """Async agent that yields a text delta then done."""

    async def invoke(self, _messages: dict[str, Any]) -> AgentMessage:
        return AgentMessage(role="assistant", content="async hello")

    async def invoke_stream(self, _messages: dict[str, Any]) -> AsyncIterator[Any]:
        yield TextDeltaEvent(text="async hello")
        yield DoneEvent()


class ErrorMockAgent:
    """Agent whose invoke_stream raises an exception."""

    def invoke(self, _messages: dict[str, Any]) -> AgentMessage:
        return AgentMessage(role="assistant", content="")

    def invoke_stream(self, _messages: dict[str, Any]) -> Iterator[Any]:
        raise RuntimeError("agent exploded")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_client() -> TestClient:
    app = create_app(SyncMockAgent())
    return TestClient(app)


@pytest.fixture
def async_client() -> TestClient:
    app = create_app(AsyncMockAgent())
    return TestClient(app)


@pytest.fixture
def error_client() -> TestClient:
    app = create_app(ErrorMockAgent())
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

VALID_MESSAGE = '{"messages": [{"role": "user", "content": "hi"}]}'


def test_single_turn(sync_client: TestClient):
    """Send one message and receive text_delta + done."""
    with sync_client.websocket_connect("/api/chat-ws") as ws:
        ws.send_text(VALID_MESSAGE)

        event1 = ws.receive_json()
        assert event1["type"] == "text_delta"
        assert event1["text"] == "hello"

        event2 = ws.receive_json()
        assert event2["type"] == "done"


def test_multi_turn(sync_client: TestClient):
    """Two turns on the same connection."""
    with sync_client.websocket_connect("/api/chat-ws") as ws:
        for _ in range(2):
            ws.send_text(VALID_MESSAGE)

            event1 = ws.receive_json()
            assert event1["type"] == "text_delta"

            event2 = ws.receive_json()
            assert event2["type"] == "done"


def test_async_agent(async_client: TestClient):
    """Async agent path works correctly."""
    with async_client.websocket_connect("/api/chat-ws") as ws:
        ws.send_text(VALID_MESSAGE)

        event1 = ws.receive_json()
        assert event1["type"] == "text_delta"
        assert event1["text"] == "async hello"

        event2 = ws.receive_json()
        assert event2["type"] == "done"


def test_malformed_json(sync_client: TestClient):
    """Malformed JSON returns error event; connection stays open."""
    with sync_client.websocket_connect("/api/chat-ws") as ws:
        ws.send_text("not json")

        error = ws.receive_json()
        assert error["type"] == "error"
        assert "Invalid JSON" in error["error"]

        # Connection still works
        ws.send_text(VALID_MESSAGE)
        event = ws.receive_json()
        assert event["type"] == "text_delta"
        ws.receive_json()  # done


def test_missing_messages_field(sync_client: TestClient):
    """Missing 'messages' field returns error event; connection stays open."""
    with sync_client.websocket_connect("/api/chat-ws") as ws:
        ws.send_text('{"foo": "bar"}')

        error = ws.receive_json()
        assert error["type"] == "error"
        assert "messages" in error["error"]

        # Connection still works
        ws.send_text(VALID_MESSAGE)
        event = ws.receive_json()
        assert event["type"] == "text_delta"
        ws.receive_json()  # done


def test_agent_error(error_client: TestClient):
    """Agent error returns error event; connection stays open."""
    with error_client.websocket_connect("/api/chat-ws") as ws:
        ws.send_text(VALID_MESSAGE)

        error = ws.receive_json()
        assert error["type"] == "error"
        assert "agent exploded" in error["error"]
