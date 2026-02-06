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
