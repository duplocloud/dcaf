"""Tests for forwarding top-level request fields through the agent pipeline."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dcaf.agent_server import create_chat_app
from dcaf.schemas.events import DoneEvent, TextDeltaEvent
from dcaf.schemas.messages import AgentMessage


# ---------------------------------------------------------------------------
# Mock agents that capture what they receive
# ---------------------------------------------------------------------------


class CapturingSyncAgent:
    """Agent that captures the full dict passed to invoke/invoke_stream."""

    def __init__(self):
        self.last_invoke_input: dict[str, Any] | None = None
        self.last_stream_input: dict[str, Any] | None = None

    def invoke(self, messages: dict[str, Any]) -> AgentMessage:
        self.last_invoke_input = messages
        return AgentMessage(role="assistant", content="ok")

    def invoke_stream(self, messages: dict[str, Any]) -> Iterator[Any]:
        self.last_stream_input = messages
        yield TextDeltaEvent(text="ok")
        yield DoneEvent()


class CapturingAsyncAgent:
    """Async agent that captures the full dict passed to invoke/invoke_stream."""

    def __init__(self):
        self.last_invoke_input: dict[str, Any] | None = None
        self.last_stream_input: dict[str, Any] | None = None

    async def invoke(self, messages: dict[str, Any]) -> AgentMessage:
        self.last_invoke_input = messages
        return AgentMessage(role="assistant", content="async ok")

    async def invoke_stream(self, messages: dict[str, Any]) -> AsyncIterator[Any]:
        self.last_stream_input = messages
        yield TextDeltaEvent(text="async ok")
        yield DoneEvent()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_agent() -> CapturingSyncAgent:
    return CapturingSyncAgent()


@pytest.fixture
def sync_client(sync_agent: CapturingSyncAgent) -> TestClient:
    app = create_chat_app(sync_agent)
    return TestClient(app)


@pytest.fixture
def async_agent() -> CapturingAsyncAgent:
    return CapturingAsyncAgent()


@pytest.fixture
def async_client(async_agent: CapturingAsyncAgent) -> TestClient:
    app = create_chat_app(async_agent)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUEST_WITH_FIELDS = {
    "thread_id": "ai-260204162205",
    "tenant_id": "32d6aa2b-xxxx",
    "messages": [{"role": "user", "content": "list namespaces"}],
    "source": "help-desk",
}

REQUEST_WITHOUT_FIELDS = {
    "messages": [{"role": "user", "content": "hello"}],
}


# ---------------------------------------------------------------------------
# Tests: /api/chat (non-streaming)
# ---------------------------------------------------------------------------


class TestChatRequestFields:
    """Tests for top-level field forwarding via /api/chat."""

    def test_request_fields_forwarded_to_agent(
        self, sync_client: TestClient, sync_agent: CapturingSyncAgent
    ):
        """Top-level fields are attached as _request_fields in the dict passed to agent."""
        response = sync_client.post("/api/chat", json=REQUEST_WITH_FIELDS)
        assert response.status_code == 200

        # Agent received _request_fields
        assert sync_agent.last_invoke_input is not None
        rf = sync_agent.last_invoke_input.get("_request_fields", {})
        assert rf["thread_id"] == "ai-260204162205"
        assert rf["tenant_id"] == "32d6aa2b-xxxx"
        assert rf["source"] == "help-desk"
        # messages should NOT be in _request_fields
        assert "messages" not in rf

    def test_request_fields_echoed_in_response(self, sync_client: TestClient):
        """Top-level fields are echoed back in meta_data.request_context."""
        response = sync_client.post("/api/chat", json=REQUEST_WITH_FIELDS)
        assert response.status_code == 200
        data = response.json()

        rc = data.get("meta_data", {}).get("request_context", {})
        assert rc["thread_id"] == "ai-260204162205"
        assert rc["tenant_id"] == "32d6aa2b-xxxx"
        assert rc["source"] == "help-desk"

    def test_no_extra_fields_still_works(self, sync_client: TestClient):
        """Requests without extra top-level fields work normally."""
        response = sync_client.post("/api/chat", json=REQUEST_WITHOUT_FIELDS)
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "ok"
        # No request_context when no extra fields
        assert "request_context" not in data.get("meta_data", {})

    def test_async_agent_receives_fields(
        self, async_client: TestClient, async_agent: CapturingAsyncAgent
    ):
        """Async agent also receives _request_fields."""
        response = async_client.post("/api/chat", json=REQUEST_WITH_FIELDS)
        assert response.status_code == 200

        assert async_agent.last_invoke_input is not None
        rf = async_agent.last_invoke_input.get("_request_fields", {})
        assert rf["thread_id"] == "ai-260204162205"


# ---------------------------------------------------------------------------
# Tests: /api/chat-stream (streaming)
# ---------------------------------------------------------------------------


class TestStreamRequestFields:
    """Tests for top-level field forwarding via /api/chat-stream."""

    def test_request_fields_forwarded_to_stream(
        self, sync_client: TestClient, sync_agent: CapturingSyncAgent
    ):
        """Top-level fields are attached as _request_fields in the dict passed to invoke_stream."""
        response = sync_client.post(
            "/api/chat-stream", json=REQUEST_WITH_FIELDS
        )
        assert response.status_code == 200

        assert sync_agent.last_stream_input is not None
        rf = sync_agent.last_stream_input.get("_request_fields", {})
        assert rf["thread_id"] == "ai-260204162205"
        assert rf["tenant_id"] == "32d6aa2b-xxxx"

    def test_no_extra_fields_stream_still_works(self, sync_client: TestClient):
        """Streaming without extra fields works normally."""
        response = sync_client.post(
            "/api/chat-stream", json=REQUEST_WITHOUT_FIELDS
        )
        assert response.status_code == 200

        events = [json.loads(line) for line in response.text.strip().split("\n") if line.strip()]
        types = [e["type"] for e in events]
        assert "text_delta" in types
        assert "done" in types


# ---------------------------------------------------------------------------
# Tests: /api/chat-ws (WebSocket)
# ---------------------------------------------------------------------------


class TestWebSocketRequestFields:
    """Tests for top-level field forwarding via /api/chat-ws."""

    def test_request_fields_forwarded_via_websocket(
        self, sync_client: TestClient, sync_agent: CapturingSyncAgent
    ):
        """Top-level fields are forwarded through the WebSocket handler."""
        with sync_client.websocket_connect("/api/chat-ws") as ws:
            ws.send_text(json.dumps(REQUEST_WITH_FIELDS))

            event1 = ws.receive_json()
            assert event1["type"] == "text_delta"

            event2 = ws.receive_json()
            assert event2["type"] == "done"

        assert sync_agent.last_stream_input is not None
        rf = sync_agent.last_stream_input.get("_request_fields", {})
        assert rf["thread_id"] == "ai-260204162205"
        assert rf["tenant_id"] == "32d6aa2b-xxxx"

    def test_no_extra_fields_websocket_still_works(
        self, sync_client: TestClient, sync_agent: CapturingSyncAgent
    ):
        """WebSocket without extra fields works normally."""
        with sync_client.websocket_connect("/api/chat-ws") as ws:
            ws.send_text(json.dumps(REQUEST_WITHOUT_FIELDS))

            event1 = ws.receive_json()
            assert event1["type"] == "text_delta"

            event2 = ws.receive_json()
            assert event2["type"] == "done"


# ---------------------------------------------------------------------------
# Tests: Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Ensure existing behavior is not broken."""

    def test_empty_request_fields_not_echoed(self, sync_client: TestClient):
        """When no extra fields, meta_data should not contain request_context."""
        response = sync_client.post("/api/chat", json=REQUEST_WITHOUT_FIELDS)
        assert response.status_code == 200
        data = response.json()
        meta = data.get("meta_data", {})
        assert "request_context" not in meta

    def test_messages_not_duplicated_in_request_fields(
        self, sync_client: TestClient, sync_agent: CapturingSyncAgent
    ):
        """The 'messages' key should never appear in _request_fields."""
        response = sync_client.post("/api/chat", json=REQUEST_WITH_FIELDS)
        assert response.status_code == 200

        rf = sync_agent.last_invoke_input.get("_request_fields", {})
        assert "messages" not in rf
