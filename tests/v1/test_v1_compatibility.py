"""
Tests for v1 backwards compatibility.

These tests ensure that code written for v1 (main branch) continues to work
in vnext without modification. This is critical for the Strangler Fig migration
strategy outlined in ADR-006.

Tests cover:
1. Legacy API endpoints (/api/sendMessage, /api/sendMessageStream)
2. AgentProtocol with only invoke() (no invoke_stream requirement)
3. Tool class backwards compatibility (schema field)
4. V1 agent imports and instantiation
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.events import DoneEvent, TextDeltaEvent
from dcaf.schemas.messages import AgentMessage

# =============================================================================
# Test Agents
# =============================================================================


class V1AgentWithOnlyInvoke:
    """
    Simulates a v1 agent that ONLY implements invoke().

    This is the minimal v1 contract - agents were not required to implement
    invoke_stream. This test ensures such agents still work.
    """

    def invoke(self, _messages: dict[str, list[dict[str, Any]]]) -> AgentMessage:
        """Process messages and return a response."""
        return AgentMessage(role="assistant", content="Response from v1 agent with only invoke()")

    # NOTE: No invoke_stream method - this is intentional!


class V1AgentWithBothMethods:
    """
    Simulates a v1 agent that implements both invoke() and invoke_stream().

    Some v1 agents may have implemented streaming voluntarily.
    """

    def invoke(self, _messages: dict[str, list[dict[str, Any]]]) -> AgentMessage:
        return AgentMessage(role="assistant", content="Response from v1 agent")

    def invoke_stream(self, _messages: dict[str, Any]) -> Iterator[Any]:
        yield TextDeltaEvent(text="Streaming ")
        yield TextDeltaEvent(text="response")
        yield DoneEvent()


class V1AgentWithThreadId:
    """
    Simulates a v1 agent that accepts thread_id as an explicit parameter.

    NOTE: This was a documented v1 pattern but the server does NOT pass
    thread_id explicitly - agents must extract it from the messages dict
    if they need it.
    """

    def __init__(self):
        self.last_thread_id = None

    def invoke(
        self, _messages: dict[str, list[dict[str, Any]]], thread_id: str | None = None
    ) -> AgentMessage:
        """Process messages with optional thread_id parameter (v1 pattern)."""
        self.last_thread_id = thread_id
        return AgentMessage(role="assistant", content=f"Response with thread_id: {thread_id}")

    def invoke_stream(
        self, _messages: dict[str, Any], thread_id: str | None = None
    ) -> Iterator[Any]:
        """Stream with optional thread_id parameter (v1 pattern)."""
        self.last_thread_id = thread_id
        yield TextDeltaEvent(text=f"thread_id={thread_id}")
        yield DoneEvent()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def v1_agent_invoke_only() -> V1AgentWithOnlyInvoke:
    """Agent that only has invoke() method."""
    return V1AgentWithOnlyInvoke()


@pytest.fixture
def v1_agent_both_methods() -> V1AgentWithBothMethods:
    """Agent that has both invoke() and invoke_stream()."""
    return V1AgentWithBothMethods()


@pytest.fixture
def client_invoke_only(v1_agent_invoke_only: V1AgentWithOnlyInvoke) -> TestClient:
    """Test client with v1 agent that only has invoke()."""
    app = create_chat_app(v1_agent_invoke_only)
    return TestClient(app)


@pytest.fixture
def client_both_methods(v1_agent_both_methods: V1AgentWithBothMethods) -> TestClient:
    """Test client with v1 agent that has both methods."""
    app = create_chat_app(v1_agent_both_methods)
    return TestClient(app)


@pytest.fixture
def v1_agent_with_thread_id() -> V1AgentWithThreadId:
    """Agent that accepts thread_id as an explicit parameter (v1 pattern)."""
    return V1AgentWithThreadId()


@pytest.fixture
def client_thread_id(v1_agent_with_thread_id: V1AgentWithThreadId) -> TestClient:
    """Test client with v1 agent that accepts thread_id parameter."""
    app = create_chat_app(v1_agent_with_thread_id)
    return TestClient(app)


# =============================================================================
# Test: Legacy Endpoint /api/sendMessage
# =============================================================================


class TestLegacyEndpointSendMessage:
    """
    Tests for the legacy /api/sendMessage endpoint.

    Per ADR-007, this endpoint should be preserved (deprecated) for
    backwards compatibility with existing clients.
    """

    def test_legacy_endpoint_exists(self, client_both_methods: TestClient):
        """The /api/sendMessage endpoint should exist and return 200."""
        response = client_both_methods.post(
            "/api/sendMessage", json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        # Should NOT be 404
        assert response.status_code == 200, (
            f"Legacy endpoint /api/sendMessage returned {response.status_code}. "
            "Per ADR-007, this endpoint should be preserved for backwards compatibility."
        )

    def test_legacy_endpoint_returns_agent_message(self, client_both_methods: TestClient):
        """The /api/sendMessage endpoint should return a valid AgentMessage."""
        response = client_both_methods.post(
            "/api/sendMessage", json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert "role" in data
        assert data["role"] == "assistant"
        assert "content" in data


# =============================================================================
# Test: Legacy Endpoint /api/sendMessageStream
# =============================================================================


class TestLegacyEndpointSendMessageStream:
    """
    Tests for the legacy /api/sendMessageStream endpoint.

    Per ADR-007, this endpoint should be preserved (deprecated) for
    backwards compatibility with existing clients.
    """

    def test_legacy_stream_endpoint_exists(self, client_both_methods: TestClient):
        """The /api/sendMessageStream endpoint should exist and return 200."""
        response = client_both_methods.post(
            "/api/sendMessageStream", json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        # Should NOT be 404
        assert response.status_code == 200, (
            f"Legacy endpoint /api/sendMessageStream returned {response.status_code}. "
            "Per ADR-007, this endpoint should be preserved for backwards compatibility."
        )

    def test_legacy_stream_endpoint_returns_ndjson(self, client_both_methods: TestClient):
        """The /api/sendMessageStream endpoint should return NDJSON events."""
        response = client_both_methods.post(
            "/api/sendMessageStream", json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert response.status_code == 200

        # Parse NDJSON response
        lines = [line for line in response.text.strip().split("\n") if line.strip()]
        events = [json.loads(line) for line in lines]

        # Should have at least one event
        assert len(events) > 0

        # Should end with a done event
        event_types = [e.get("type") for e in events]
        assert "done" in event_types


# =============================================================================
# Test: AgentProtocol Without invoke_stream
# =============================================================================


class TestAgentProtocolBackwardsCompatibility:
    """
    Tests that agents implementing only invoke() (no invoke_stream) still work.

    The v1 AgentProtocol only required invoke(). Adding invoke_stream as a
    requirement would break all existing agents.
    """

    def test_agent_with_only_invoke_passes_protocol_check(self):
        """An agent with only invoke() should satisfy AgentProtocol."""
        agent = V1AgentWithOnlyInvoke()

        # This should NOT raise TypeError
        # The isinstance check in create_chat_app should pass
        assert isinstance(agent, AgentProtocol), (
            "Agent with only invoke() should satisfy AgentProtocol. "
            "The protocol should not require invoke_stream."
        )

    def test_create_chat_app_accepts_invoke_only_agent(self):
        """create_chat_app should accept an agent with only invoke()."""
        agent = V1AgentWithOnlyInvoke()

        # This should NOT raise TypeError
        try:
            app = create_chat_app(agent)
            assert app is not None
        except TypeError as e:
            pytest.fail(
                f"create_chat_app rejected agent with only invoke(): {e}. "
                "V1 agents were not required to implement invoke_stream."
            )

    def test_invoke_only_agent_handles_legacy_endpoint(self, client_invoke_only: TestClient):
        """Agent with only invoke() should handle /api/sendMessage requests."""
        response = client_invoke_only.post(
            "/api/sendMessage", json={"messages": [{"role": "user", "content": "Hello"}]}
        )

        assert response.status_code == 200

    def test_stream_endpoint_graceful_fallback_for_invoke_only_agent(
        self, client_invoke_only: TestClient
    ):
        """
        Streaming endpoints should handle agents without invoke_stream gracefully.

        Options:
        1. Return 501 Not Implemented
        2. Fall back to invoke() and wrap result in stream events
        3. Return an error event in the stream

        Any of these is acceptable - the key is no crash/500.
        """
        response = client_invoke_only.post(
            "/api/sendMessageStream", json={"messages": [{"role": "user", "content": "Hello"}]}
        )

        # Should not be a 500 server error
        assert response.status_code != 500, (
            "Streaming endpoint crashed when agent doesn't have invoke_stream. "
            "Should handle gracefully (501, fallback, or error event)."
        )


# =============================================================================
# Test: Tool.schema Backwards Compatibility
# =============================================================================


class TestToolSchemaBackwardsCompatibility:
    """
    Tests that the old Tool(schema=...) syntax still works.

    V1 used `schema` field containing the full tool spec.
    """

    def test_tool_creation_with_schema_field(self):
        """Tool should accept the 'schema' field name."""
        from dcaf.tools import Tool

        def dummy_func(x: str) -> str:
            return x

        # V1 style: schema contains full tool spec
        full_schema = {
            "name": "my_tool",
            "description": "A test tool",
            "input_schema": {
                "type": "object",
                "properties": {"x": {"type": "string", "description": "Input value"}},
                "required": ["x"],
            },
        }

        # This should NOT raise an error
        tool = Tool(func=dummy_func, name="my_tool", description="A test tool", schema=full_schema)
        assert tool is not None

    def test_tool_get_schema_returns_full_spec(self):
        """Tool.get_schema() should return full tool spec."""
        from dcaf.tools import Tool

        def dummy_func(x: str) -> str:
            return x

        full_schema = {
            "name": "my_tool",
            "description": "A test tool",
            "input_schema": {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            },
        }

        tool = Tool(func=dummy_func, name="my_tool", description="A test tool", schema=full_schema)

        schema = tool.get_schema()

        # Should have all required fields for LLM consumption
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema
        assert schema["name"] == "my_tool"

    def test_tool_decorator_requires_approval_default_is_true(self):
        """
        @tool decorator should default to requires_approval=True.

        V1 used requires_approval=True as the safe default. This ensures
        tools require explicit approval unless opted out.

        This is a SECURITY-CRITICAL backwards compatibility requirement.
        """
        from dcaf.tools import tool

        @tool(
            schema={
                "name": "my_tool",
                "description": "Test tool",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                },
            }
        )
        def my_tool(x: str) -> str:
            return x

        # V1 default: requires_approval=True
        assert my_tool.requires_approval is True, (
            "V1 SECURITY REGRESSION: @tool decorator's requires_approval "
            "must default to True. Tools should be safe by default."
        )

    def test_tool_decorator_with_v1_style_schema(self):
        """@tool decorator should accept v1-style schema parameter."""
        from dcaf.tools import tool

        @tool(
            schema={
                "name": "get_weather",
                "description": "Get weather for a city",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string", "description": "City name"}},
                    "required": ["city"],
                },
            }
        )
        def get_weather(city: str) -> str:
            """Get weather for a city."""
            return f"Weather in {city}: Sunny"

        assert get_weather is not None
        assert get_weather.name == "get_weather"
        assert get_weather.requires_approval is True  # V1 default


# =============================================================================
# Test: V1 Agent Imports
# =============================================================================


class TestV1AgentImports:
    """
    Tests that all v1 agents can be imported from their expected locations.

    Import paths should not change between v1 and vnext.
    """

    def test_import_agent_protocol(self):
        """AgentProtocol should be importable from dcaf.agent_server."""
        from dcaf.agent_server import AgentProtocol

        assert AgentProtocol is not None

    def test_import_create_chat_app(self):
        """create_chat_app should be importable from dcaf.agent_server."""
        from dcaf.agent_server import create_chat_app

        assert create_chat_app is not None

    def test_import_bedrock_llm(self):
        """BedrockLLM should be importable from dcaf.llm."""
        from dcaf.llm import BedrockLLM

        assert BedrockLLM is not None

    def test_import_agent_message(self):
        """AgentMessage should be importable from dcaf.schemas.messages."""
        from dcaf.schemas.messages import AgentMessage

        assert AgentMessage is not None

    def test_import_tool_decorator(self):
        """tool decorator should be importable from dcaf.tools."""
        from dcaf.tools import tool

        assert tool is not None

    def test_import_tool_class(self):
        """Tool class should be importable from dcaf.tools."""
        from dcaf.tools import Tool

        assert Tool is not None

    def test_top_level_exports(self):
        """Key classes should be importable from dcaf package."""
        from dcaf import (
            AgentMessage,
            AgentProtocol,
            BedrockLLM,
            create_chat_app,
        )

        assert AgentProtocol is not None
        assert create_chat_app is not None
        assert BedrockLLM is not None
        assert AgentMessage is not None


# =============================================================================
# Test: V1 Agent Subclasses (if importable)
# =============================================================================


class TestV1AgentSubclassImports:
    """
    Tests that specific v1 agent implementations can be imported.

    Note: These may fail if the agents have broken imports, which is
    a separate issue to fix.
    """

    def test_import_tool_calling_cmd_agent(self):
        """ToolCallingCmdAgent should be importable."""
        try:
            from dcaf.agents.tool_calling_cmd_agent import ToolCallingCmdAgent

            assert ToolCallingCmdAgent is not None
        except ImportError as e:
            pytest.fail(f"Failed to import ToolCallingCmdAgent: {e}")

    def test_import_echo_agent(self):
        """EchoAgent should be importable."""
        try:
            from dcaf.agents.echo_agent import EchoAgent

            assert EchoAgent is not None
        except ImportError as e:
            pytest.fail(f"Failed to import EchoAgent: {e}")

    def test_import_boilerplate_agent(self):
        """BoilerplateAgent should be importable."""
        try:
            from dcaf.agents.boilerplate_agent import BoilerplateAgent

            assert BoilerplateAgent is not None
        except ImportError as e:
            pytest.fail(f"Failed to import BoilerplateAgent: {e}")

    def test_import_llm_passthrough_agent(self):
        """LLMPassthroughAgent should be importable."""
        try:
            from dcaf.agents.llm_passthrough_agent import LLMPassthroughAgent

            assert LLMPassthroughAgent is not None
        except ImportError as e:
            pytest.fail(f"Failed to import LLMPassthroughAgent: {e}")
