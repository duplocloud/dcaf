"""
Live integration tests for the Agno adapter with real LLM calls.

These tests make actual API calls to AWS Bedrock to verify:
1. Tool call responses don't contain spurious '[]'
2. Content extraction works correctly
3. The full request/response cycle works as expected

Run with: pytest tests/test_agno_live.py -v -s

Requirements:
- AWS credentials configured (profile or env vars)
- Access to AWS Bedrock with Claude models

Skip these tests in CI by setting: SKIP_LIVE_LLM_TESTS=true
"""

import logging
import os

import pytest

# Configure logging to see debug output
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Skip conditions
# =============================================================================

SKIP_LIVE_TESTS = os.getenv("SKIP_LIVE_LLM_TESTS", "false").lower() == "true"
SKIP_REASON = "Live LLM tests disabled (set SKIP_LIVE_LLM_TESTS=false to enable)"


def requires_aws_credentials():
    """Check if AWS credentials are available."""
    has_profile = os.getenv("AWS_PROFILE") is not None
    has_keys = os.getenv("AWS_ACCESS_KEY_ID") is not None
    has_region = os.getenv("AWS_REGION") is not None or os.getenv("AWS_DEFAULT_REGION") is not None
    return has_profile or (has_keys and has_region)


# =============================================================================
# Test Tools
# =============================================================================


def create_test_tools():
    """Create test tools for LLM testing."""
    from dcaf.tools import tool

    @tool(description="Execute a terminal command to interact with the system")
    def execute_terminal_cmd(command: str, explanation: str = "") -> str:
        """Execute a terminal command."""
        return f"Command scheduled for execution: {command}"

    @tool(description="Get the current weather for a location")
    def get_weather(location: str, unit: str = "celsius") -> str:
        """Get weather for a location."""
        return f"Weather in {location}: 22 degrees {unit}"

    @tool(description="Search for information on a topic")
    def search(query: str) -> str:
        """Search for information."""
        return f"Search results for '{query}': Found 10 relevant documents"

    return [execute_terminal_cmd, get_weather, search]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tools():
    """Provide test tools."""
    return create_test_tools()


@pytest.fixture
def agno_adapter():
    """Create a real AgnoAdapter for live testing."""
    from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

    # Use default Bedrock configuration
    model_id = os.getenv("TEST_BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")
    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))

    adapter = AgnoAdapter(
        model_id=model_id,
        provider="bedrock",
        aws_region=region,
        aws_profile=os.getenv("AWS_PROFILE"),
    )

    return adapter


@pytest.fixture
def dcaf_agent(tools):
    """Create a DCAF Agent for live testing."""
    from dcaf.core import Agent

    model_id = os.getenv("TEST_BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")

    agent = Agent(
        tools=tools,
        model=model_id,
        provider="bedrock",
        system_prompt="You are a helpful assistant. Use tools when needed.",
    )

    return agent


# =============================================================================
# Test: Content doesn't contain []
# =============================================================================


@pytest.mark.skipif(SKIP_LIVE_TESTS, reason=SKIP_REASON)
@pytest.mark.skipif(not requires_aws_credentials(), reason="AWS credentials not configured")
class TestContentDoesNotContainBrackets:
    """Tests ensuring response content doesn't have spurious []."""

    @pytest.mark.asyncio
    async def test_tool_call_response_no_brackets(self, agno_adapter, tools):
        """
        CRITICAL TEST: Verify tool call responses don't contain '[]'.

        This test reproduces the bug where agent responses had '[]' appended:
        "I'll check what pods are running in your namespace.[]"

        The [] appears when the model responds with text AND a tool call.
        """
        messages = [{"role": "user", "content": "List the pods running in the default namespace"}]

        response = await agno_adapter.invoke(
            messages=messages,
            tools=tools,
            system_prompt="You are a Kubernetes assistant. Use the execute_terminal_cmd tool to run kubectl commands.",
        )

        logger.info(f"Response text: {repr(response.text)}")
        logger.info(f"Tool calls: {response.data.tool_calls if response.data else 'None'}")

        # THE CRITICAL ASSERTION
        if response.text:
            assert not response.text.endswith("[]"), (
                f"Response text ends with '[]'! This is the bug.\nText: {repr(response.text)}"
            )
            assert "[]" not in response.text, (
                f"Response text contains '[]'! This may be the bug.\nText: {repr(response.text)}"
            )

    @pytest.mark.asyncio
    async def test_simple_response_no_brackets(self, agno_adapter, tools):
        """Test that simple responses (no tool calls) don't have []."""
        messages = [{"role": "user", "content": "What is 2 + 2? Just tell me the answer."}]

        response = await agno_adapter.invoke(
            messages=messages,
            tools=tools,
            system_prompt="You are a helpful assistant. Answer questions directly without using tools unless necessary.",
        )

        logger.info(f"Response text: {repr(response.text)}")

        if response.text:
            assert not response.text.endswith("[]"), (
                f"Response text ends with '[]'!\nText: {repr(response.text)}"
            )

    @pytest.mark.asyncio
    async def test_weather_tool_response_no_brackets(self, agno_adapter, tools):
        """Test weather query which should trigger get_weather tool."""
        messages = [{"role": "user", "content": "What's the weather like in Seattle?"}]

        response = await agno_adapter.invoke(
            messages=messages,
            tools=tools,
            system_prompt="You are a weather assistant. Use the get_weather tool to check weather.",
        )

        logger.info(f"Response text: {repr(response.text)}")
        logger.info(f"Tool calls: {response.data.tool_calls if response.data else 'None'}")

        if response.text:
            assert not response.text.endswith("[]"), (
                f"Response text ends with '[]'!\nText: {repr(response.text)}"
            )


# =============================================================================
# Test: Using DCAF Agent directly
# =============================================================================


@pytest.mark.skipif(SKIP_LIVE_TESTS, reason=SKIP_REASON)
@pytest.mark.skipif(not requires_aws_credentials(), reason="AWS credentials not configured")
class TestDCAFAgentNoBrackets:
    """Tests using the DCAF Agent class directly."""

    @pytest.mark.asyncio
    async def test_agent_run_no_brackets(self, dcaf_agent):
        """Test that Agent.run() responses don't contain []."""
        messages = [{"role": "user", "content": "Check what processes are running on the system"}]

        response = await dcaf_agent.arun(messages=messages)

        logger.info(f"Agent response: {response}")

        # Check the response content
        content = None
        if hasattr(response, "text"):
            content = response.text
        elif hasattr(response, "content"):
            content = response.content
        elif isinstance(response, dict):
            content = response.get("text") or response.get("content")

        logger.info(f"Response content: {repr(content)}")

        if content:
            assert not content.endswith("[]"), (
                f"Agent response ends with '[]'!\nContent: {repr(content)}"
            )

    @pytest.mark.asyncio
    async def test_agent_to_message_no_brackets(self, dcaf_agent):
        """Test that to_message() output doesn't contain []."""
        messages = [{"role": "user", "content": "Run kubectl get pods"}]

        response = await dcaf_agent.arun(messages=messages)

        # Convert to message format (as would be sent to HelpDesk)
        if hasattr(response, "to_message"):
            message = response.to_message()
            logger.info(f"Message: {message}")

            if hasattr(message, "content") and message.content:
                assert not message.content.endswith("[]"), (
                    f"Message content ends with '[]'!\nContent: {repr(message.content)}"
                )


# =============================================================================
# Test: Content type inspection
# =============================================================================


@pytest.mark.skipif(SKIP_LIVE_TESTS, reason=SKIP_REASON)
@pytest.mark.skipif(not requires_aws_credentials(), reason="AWS credentials not configured")
class TestContentTypeInspection:
    """Tests that inspect the type and structure of response content."""

    @pytest.mark.asyncio
    async def test_inspect_run_output_content_type(self, agno_adapter, tools):  # noqa: ARG002
        """
        Inspect the actual type of run_output.content.

        This helps diagnose whether [] comes from:
        - String concatenation
        - Object __str__ method
        - List/array serialization
        """
        import aioboto3
        from agno.agent import Agent as AgnoAgent
        from agno.models.aws import AwsBedrock
        from agno.tools import tool as agno_tool

        # Create tools using Agno's decorator directly
        @agno_tool(name="test_cmd", description="Run a command")
        def test_cmd(command: str) -> str:
            return f"Executed: {command}"

        # Create Agno agent directly (bypassing DCAF)
        region = os.getenv("AWS_REGION", "us-west-2")
        model_id = os.getenv("TEST_BEDROCK_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")

        async_session = aioboto3.Session(region_name=region)

        model = AwsBedrock(
            id=model_id,
            aws_region=region,
            async_session=async_session,
        )

        agent = AgnoAgent(
            model=model,
            tools=[test_cmd],
            instructions="You are a helpful assistant. Use tools when appropriate.",
        )

        # Run the agent
        run_output = await agent.arun("List the files in the current directory")

        # Inspect the content
        logger.info(f"run_output type: {type(run_output)}")
        logger.info(f"run_output.content type: {type(run_output.content)}")
        logger.info(f"run_output.content repr: {repr(run_output.content)}")
        logger.info(f"run_output.content_type: {run_output.content_type}")

        if run_output.content is not None:
            logger.info(
                f"run_output.content class: {run_output.content.__class__.__module__}.{run_output.content.__class__.__name__}"
            )

            if hasattr(run_output.content, "__dict__"):
                logger.info(f"run_output.content __dict__: {run_output.content.__dict__}")

        # Log tools and other fields
        logger.info(f"run_output.tools: {run_output.tools}")
        logger.info(f"run_output.images: {run_output.images}")
        logger.info(f"run_output.videos: {run_output.videos}")
        logger.info(f"run_output.audio: {run_output.audio}")

        # Check for []
        content_str = str(run_output.content) if run_output.content else ""
        if "[]" in content_str:
            logger.warning("FOUND [] in content!")
            logger.warning(f"Content ends with []: {content_str.endswith('[]')}")

            # Try to understand where it comes from
            if hasattr(run_output, "get_content_as_string"):
                official_content = run_output.get_content_as_string()
                logger.warning(f"get_content_as_string(): {repr(official_content)}")

        # The test - content should not end with []
        if run_output.content:
            content_repr = repr(run_output.content)
            assert not content_repr.endswith("[]'"), (
                f"Content ends with []!\nType: {type(run_output.content)}\nRepr: {content_repr}"
            )


# =============================================================================
# Test: Comparison with and without tools
# =============================================================================


@pytest.mark.skipif(SKIP_LIVE_TESTS, reason=SKIP_REASON)
@pytest.mark.skipif(not requires_aws_credentials(), reason="AWS credentials not configured")
class TestWithAndWithoutTools:
    """Compare responses with and without tools to isolate the issue."""

    @pytest.mark.asyncio
    async def test_same_prompt_with_and_without_tools(self, agno_adapter, tools):
        """
        Run the same prompt with and without tools to see if [] only appears with tools.
        """
        prompt = "Hello, how are you today?"
        messages = [{"role": "user", "content": prompt}]

        # With tools
        response_with_tools = await agno_adapter.invoke(
            messages=messages,
            tools=tools,
            system_prompt="You are a helpful assistant.",
        )

        # Without tools
        response_without_tools = await agno_adapter.invoke(
            messages=messages,
            tools=[],
            system_prompt="You are a helpful assistant.",
        )

        logger.info(f"WITH tools - text: {repr(response_with_tools.text)}")
        logger.info(f"WITHOUT tools - text: {repr(response_without_tools.text)}")

        # Check both
        has_brackets_with = "[]" in response_with_tools.text if response_with_tools.text else False

        if response_without_tools.text:
            has_brackets_without = "[]" in response_without_tools.text
        else:
            has_brackets_without = False

        logger.info(f"Has [] with tools: {has_brackets_with}")
        logger.info(f"Has [] without tools: {has_brackets_without}")

        # Neither should have []
        assert not has_brackets_with, "Response WITH tools has []"
        assert not has_brackets_without, "Response WITHOUT tools has []"


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    # Run with verbose output
    pytest.main([__file__, "-v", "-s", "--tb=short"])
