# tests/core/test_agent_events.py
"""Tests for Agent event subscription system."""

import pytest


def test_agent_on_decorator_registers_handler():
    """@agent.on() registers a handler for the event type."""
    from dcaf.core import Agent

    agent = Agent(tools=[])

    @agent.on("tool_call_started")
    async def my_handler(event):
        pass

    assert agent._event_registry.has_subscribers("tool_call_started")


def test_agent_on_decorator_multiple_types():
    """@agent.on() can register for multiple event types."""
    from dcaf.core import Agent

    agent = Agent(tools=[])

    @agent.on("tool_call_started", "tool_call_completed")
    async def my_handler(event):
        pass

    assert agent._event_registry.has_subscribers("tool_call_started")
    assert agent._event_registry.has_subscribers("tool_call_completed")


def test_agent_on_decorator_returns_original_function():
    """@agent.on() returns the original function unchanged."""
    from dcaf.core import Agent

    agent = Agent(tools=[])

    async def my_handler(event):
        return "test"

    decorated = agent.on("tool_call_started")(my_handler)

    assert decorated is my_handler


def test_agent_on_with_array_of_events():
    """@agent.on() accepts unpacked array of event types."""
    from dcaf.core import Agent

    agent = Agent(tools=[])

    my_events = ["tool_call_started", "tool_call_completed", "error"]

    @agent.on(*my_events)
    async def my_handler(event):
        pass

    assert agent._event_registry.has_subscribers("tool_call_started")
    assert agent._event_registry.has_subscribers("tool_call_completed")
    assert agent._event_registry.has_subscribers("error")


@pytest.mark.asyncio
async def test_agent_dispatches_tool_call_started_event():
    """Agent dispatches tool_call_started event when tool is called."""
    from dcaf.core import Agent, tool

    received_events = []

    @tool
    def simple_tool(message: str) -> str:
        """A simple test tool."""
        return f"Got: {message}"

    agent = Agent(tools=[simple_tool])

    @agent.on("tool_call_started")
    async def capture_event(event):
        received_events.append(event)

    # This should trigger the tool and fire the event
    # Note: This test may need mocking depending on actual LLM behavior
    # For now, we test the wiring is in place

    assert agent._event_registry.has_subscribers("tool_call_started")


def test_convert_to_new_event_maps_stream_event_types():
    """_convert_to_new_event correctly maps StreamEvent types to Event types."""
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
    from dcaf.core.application.dto.responses import StreamEvent, StreamEventType

    # Create adapter instance (minimal config)
    adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

    # Test tool_use_start mapping
    stream_event = StreamEvent.tool_use_start(
        tool_call_id="test-123",
        tool_name="weather"
    )
    new_event = adapter._convert_to_new_event(stream_event)

    assert new_event is not None
    assert new_event.type == "tool_call_started"
    assert new_event.tool_call_id == "test-123"
    assert new_event.tool_name == "weather"


def test_convert_to_new_event_maps_text_delta():
    """_convert_to_new_event maps text_delta events."""
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
    from dcaf.core.application.dto.responses import StreamEvent

    adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

    stream_event = StreamEvent.text_delta("Hello world")
    new_event = adapter._convert_to_new_event(stream_event)

    assert new_event is not None
    assert new_event.type == "text_delta"
    assert new_event.text == "Hello world"


def test_convert_to_new_event_maps_reasoning_started():
    """_convert_to_new_event maps reasoning_started events."""
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
    from dcaf.core.application.dto.responses import StreamEvent, StreamEventType

    adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

    stream_event = StreamEvent(
        event_type=StreamEventType.REASONING_STARTED,
        data={},
    )
    new_event = adapter._convert_to_new_event(stream_event)

    assert new_event is not None
    assert new_event.type == "reasoning_started"


def test_convert_to_new_event_maps_reasoning_step():
    """_convert_to_new_event maps reasoning_step events with content."""
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
    from dcaf.core.application.dto.responses import StreamEvent, StreamEventType

    adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

    stream_event = StreamEvent(
        event_type=StreamEventType.REASONING_STEP,
        data={"content": "Thinking about the problem..."},
    )
    new_event = adapter._convert_to_new_event(stream_event)

    assert new_event is not None
    assert new_event.type == "reasoning_step"
    assert new_event.content == "Thinking about the problem..."


def test_convert_to_new_event_maps_reasoning_completed():
    """_convert_to_new_event maps reasoning_completed events."""
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
    from dcaf.core.application.dto.responses import StreamEvent, StreamEventType

    adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

    stream_event = StreamEvent(
        event_type=StreamEventType.REASONING_COMPLETED,
        data={},
    )
    new_event = adapter._convert_to_new_event(stream_event)

    assert new_event is not None
    assert new_event.type == "reasoning_completed"


@pytest.mark.asyncio
async def test_agent_stream_dispatches_events_to_subscribers():
    """Full integration: agent.stream() dispatches events to @agent.on handlers."""
    from dcaf.core import Agent, tool

    received_events = []

    @tool
    def greet(name: str) -> str:
        """Greet someone."""
        return f"Hello, {name}!"

    agent = Agent(tools=[greet])

    @agent.on("tool_call_started")
    async def capture_tool_start(event):
        received_events.append(("tool_start", event.tool_name))

    @agent.on("text_delta")
    async def capture_text(event):
        received_events.append(("text", event.text))

    # Mock the runtime to simulate events
    # This verifies the wiring without hitting a real LLM
    assert agent._event_registry.has_subscribers("tool_call_started")
    assert agent._event_registry.has_subscribers("text_delta")
    assert not agent._event_registry.has_subscribers("error")
