"""
Tests for A2A (Agent-to-Agent) integration.

These tests verify that the A2A protocol works correctly for
agent discovery and communication.
"""

import pytest
from fastapi.testclient import TestClient

from dcaf.core import Agent, create_app, tool
from dcaf.core.a2a import generate_agent_card


@tool(description="Echo back the message")
def echo_tool(message: str) -> str:
    """Simple echo tool for testing."""
    return f"Echo: {message}"


@tool(description="Add two numbers")
def add_tool(a: int, b: int) -> int:
    """Simple addition tool for testing."""
    return a + b


class TestAgentCard:
    """Tests for agent card generation and discovery."""

    def test_generate_agent_card(self):
        """Test that agent cards are generated correctly."""
        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool, add_tool],
        )

        card = generate_agent_card(agent, "http://localhost:8000")

        assert card.name == "test-agent"
        assert card.description == "A test agent"
        assert card.url == "http://localhost:8000"
        assert "echo_tool" in card.skills
        assert "add_tool" in card.skills
        assert len(card.skills) == 2

    def test_agent_card_endpoint(self):
        """Test that the agent card endpoint works."""
        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        app = create_app(agent, a2a=True)
        client = TestClient(app)

        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200

        card_data = response.json()
        assert card_data["name"] == "test-agent"
        assert card_data["description"] == "A test agent"
        assert "echo_tool" in card_data["skills"]


class TestTaskExecution:
    """Tests for A2A task execution."""

    def test_task_send_endpoint(self):
        """Test that tasks can be sent and executed."""
        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        app = create_app(agent, a2a=True)
        client = TestClient(app)

        # Send a task
        task_data = {
            "id": "test_task_123",
            "message": "Test message",
            "context": {},
            "status": "pending",
        }

        response = client.post("/a2a/tasks/send", json=task_data)
        assert response.status_code == 200

        result_data = response.json()
        assert result_data["task_id"] == "test_task_123"
        assert result_data["status"] in ["completed", "failed"]
        assert "text" in result_data

    def test_task_with_approval_needed(self):
        """Test that tasks requiring approval are handled correctly."""

        @tool(description="Dangerous operation", requires_approval=True)
        def dangerous_tool(action: str) -> str:
            return f"Executed: {action}"

        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[dangerous_tool],
        )

        app = create_app(agent, a2a=True)
        client = TestClient(app)

        task_data = {
            "id": "test_task_456",
            "message": "Do something dangerous",
            "context": {},
            "status": "pending",
        }

        response = client.post("/a2a/tasks/send", json=task_data)
        assert response.status_code == 200

        result_data = response.json()
        # Task should complete but may need approval
        assert result_data["status"] in ["completed", "failed", "pending"]


class TestRemoteAgent:
    """Tests for RemoteAgent client (integration tests require running server)."""

    def test_remote_agent_as_tool(self):
        """Test that RemoteAgent can be converted to a tool."""
        # This is a unit test that doesn't require a running server
        # We just test the tool creation logic
        from dcaf.core.a2a.client import RemoteAgent
        from dcaf.core.a2a.models import AgentCard

        # Create a RemoteAgent with a mocked card
        remote = RemoteAgent.__new__(RemoteAgent)
        remote.url = "http://test:8000"
        remote._name = "test-agent"
        remote._card = AgentCard(
            name="test-agent",
            description="Test description",
            url="http://test:8000",
            skills=["skill1", "skill2"],
        )

        # Convert to tool
        tool = remote.as_tool()

        assert tool.name == "test-agent"
        assert "Test description" in tool.description
        # Tool object should be a valid Tool instance
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")


class TestA2ARouting:
    """Tests for A2A route registration."""

    def test_a2a_routes_are_registered(self):
        """Test that A2A routes are properly registered when enabled."""
        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        app = create_app(agent, a2a=True)

        # Check that A2A routes are registered
        routes = [route.path for route in app.routes]
        assert "/.well-known/agent.json" in routes
        assert "/a2a/tasks/send" in routes
        assert "/a2a/tasks/{task_id}" in routes

    def test_a2a_routes_not_registered_when_disabled(self):
        """Test that A2A routes are not registered when disabled."""
        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        app = create_app(agent, a2a=False)

        # Check that A2A routes are NOT registered
        routes = [route.path for route in app.routes]
        assert "/.well-known/agent.json" not in routes
        assert "/a2a/tasks/send" not in routes


class TestCustomAgentCard:
    """Tests for custom a2a_agent_card support."""

    def test_custom_agent_card_via_agentcard_instance(self):
        """Test that a custom AgentCard is served instead of auto-generated."""
        from dcaf.core.a2a.models import AgentCard

        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        custom_card = AgentCard(
            name="custom-agent",
            description="A custom description",
            url="",
            skills=["custom_skill_1", "custom_skill_2"],
            version="2.0",
            metadata={"org": "duplocloud"},
        )

        app = create_app(agent, a2a=True, a2a_agent_card=custom_card)
        client = TestClient(app)

        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200

        card_data = response.json()
        assert card_data["name"] == "custom-agent"
        assert card_data["description"] == "A custom description"
        assert card_data["skills"] == ["custom_skill_1", "custom_skill_2"]
        assert card_data["version"] == "2.0"
        assert card_data["metadata"]["org"] == "duplocloud"

    def test_custom_agent_card_via_dict(self):
        """Test that a custom dict card is served with arbitrary A2A spec fields."""
        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        custom_card = {
            "name": "dict-agent",
            "description": "From a dict",
            "skills": ["skill_a"],
            "authentication": {"schemes": ["bearer"]},
            "capabilities": {"streaming": True, "pushNotifications": False},
        }

        app = create_app(agent, a2a=True, a2a_agent_card=custom_card)
        client = TestClient(app)

        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200

        card_data = response.json()
        assert card_data["name"] == "dict-agent"
        assert card_data["description"] == "From a dict"
        assert card_data["authentication"] == {"schemes": ["bearer"]}
        assert card_data["capabilities"]["streaming"] is True

    def test_auto_generated_card_when_no_custom_card(self):
        """Test that auto-generated card is used when a2a_agent_card is not provided."""
        agent = Agent(
            name="auto-agent",
            description="Auto generated",
            tools=[echo_tool, add_tool],
        )

        app = create_app(agent, a2a=True)
        client = TestClient(app)

        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200

        card_data = response.json()
        assert card_data["name"] == "auto-agent"
        assert card_data["description"] == "Auto generated"
        assert "echo_tool" in card_data["skills"]
        assert "add_tool" in card_data["skills"]

    def test_custom_card_url_set_dynamically(self):
        """Test that url is set from request.base_url even with custom AgentCard."""
        from dcaf.core.a2a.models import AgentCard

        agent = Agent(
            name="test-agent",
            description="A test agent",
            tools=[echo_tool],
        )

        custom_card = AgentCard(
            name="custom-agent",
            description="Custom",
            url="http://should-be-overridden",
            skills=[],
        )

        app = create_app(agent, a2a=True, a2a_agent_card=custom_card)
        client = TestClient(app, base_url="http://testserver")

        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200

        card_data = response.json()
        # URL should be set from the request, not the static value
        assert "testserver" in card_data["url"]


# Integration test that requires a running server (marked for manual testing)
@pytest.mark.skip(
    reason="Requires running server - use examples/a2a_example.py for integration testing"
)
def test_full_a2a_workflow():
    """
    Full integration test for A2A workflow.

    To test manually:
    1. Start an agent: python examples/a2a_example.py k8s
    2. Run the client: python examples/a2a_example.py client
    """
    pass
