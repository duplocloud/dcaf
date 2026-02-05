"""
Live test to reproduce the [] brackets issue in agent responses.

Run with:
    AWS_PROFILE=your-profile uv run pytest tests/test_brackets_issue.py -v -s

Or set environment variables:
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export AWS_REGION=us-west-2
    uv run pytest tests/test_brackets_issue.py -v -s
"""

import logging
import os

import pytest

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# =============================================================================
# Test Tools
# =============================================================================


def get_test_tool():
    """Create a simple tool that will trigger tool use."""
    from dcaf.core import tool

    @tool(description="Execute a terminal command on the system")
    def execute_terminal_cmd(command: str, explanation: str = "") -> str:
        """Execute a terminal command."""
        return f"Command scheduled: {command}"

    return execute_terminal_cmd


# =============================================================================
# Tests
# =============================================================================


class TestBracketsIssue:
    """Tests to reproduce and verify the [] brackets issue."""

    @pytest.mark.asyncio
    async def test_dcaf_agent_tool_call_no_brackets(self):
        """
        Test that DCAF Agent responses don't contain [] when tool calls are made.

        This reproduces the bug:
        "I'll check what pods are running in your namespace.[]"
        """
        from dcaf.core import Agent

        # Create agent with a tool
        agent = Agent(
            tools=[get_test_tool()],
            model=os.getenv("TEST_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            provider="bedrock",
            system_prompt="You are a helpful assistant. When asked to run commands, use the execute_terminal_cmd tool.",
        )

        # Send a message that should trigger tool use
        messages = [{"role": "user", "content": "Run the command: kubectl get pods"}]

        # Run the agent
        try:
            response = await agent.arun(messages=messages)
        except Exception as e:
            pytest.skip(f"API call failed (credentials issue?): {e}")

        assert response is not None, "Response should not be None"

        # Log the response details
        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response: {response}")

        # Extract text content
        text = None
        if hasattr(response, "text"):
            text = response.text
        elif hasattr(response, "content"):
            text = response.content

        logger.info(f"Extracted text: {repr(text)}")

        # THE CRITICAL CHECK
        if text:
            assert not text.endswith("[]"), (
                f"BUG REPRODUCED: Response ends with '[]'\nText: {repr(text)}"
            )
            assert "[]" not in text, f"BUG: Response contains '[]'\nText: {repr(text)}"

    @pytest.mark.asyncio
    async def test_agno_adapter_direct_tool_call(self):
        """
        Test the Agno adapter directly to isolate where [] comes from.
        """
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(
            model_id=os.getenv("TEST_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0"),
            provider="bedrock",
            aws_region=os.getenv("AWS_REGION", "us-west-2"),
        )

        messages = [{"role": "user", "content": "Please run: ls -la"}]

        try:
            response = await adapter.invoke(
                messages=messages,
                tools=[get_test_tool()],
                system_prompt="You are a helpful assistant. Use the execute_terminal_cmd tool when asked to run commands.",
            )
        except Exception as e:
            pytest.skip(f"API call failed (credentials issue?): {e}")

        # Verify we got actual content (not just an empty/error response)
        assert response is not None, "Response should not be None"
        assert response.text is not None and len(response.text) > 0, (
            f"Response text is empty - API may have failed silently. Response: {response}"
        )

        logger.info(f"Response type: {type(response)}")
        logger.info(f"Response.text: {repr(response.text)}")
        logger.info(f"Response.data: {response.data}")

        # Check for brackets
        if response.text:
            assert not response.text.endswith("[]"), (
                f"BUG: Adapter response ends with '[]'\nText: {repr(response.text)}"
            )

    @pytest.mark.asyncio
    async def test_agno_raw_run_output(self):
        """
        Test Agno directly (bypassing DCAF) to see if [] is from Agno SDK.
        """
        import aioboto3
        from agno.agent import Agent as AgnoAgent
        from agno.models.aws import AwsBedrock
        from agno.tools import tool as agno_tool

        # Create a tool using Agno's decorator
        @agno_tool(name="run_cmd", description="Run a terminal command")
        def run_cmd(command: str) -> str:
            return f"Executed: {command}"

        # Create Agno model and agent directly
        region = os.getenv("AWS_REGION", "us-west-2")
        model_id = os.getenv("TEST_MODEL", "anthropic.claude-3-5-sonnet-20241022-v2:0")

        async_session = aioboto3.Session(region_name=region)

        model = AwsBedrock(
            id=model_id,
            aws_region=region,
            async_session=async_session,
        )

        agent = AgnoAgent(
            model=model,
            tools=[run_cmd],
            instructions="Use the run_cmd tool when asked to execute commands.",
        )

        # Run the agent
        try:
            run_output = await agent.arun("Execute: echo hello")
        except Exception as e:
            pytest.skip(f"API call failed (credentials issue?): {e}")

        # Verify we got a response
        assert run_output is not None, "run_output should not be None"

        # Log everything about the run_output
        logger.info("=== RAW AGNO RUN_OUTPUT ===")
        logger.info(f"run_output type: {type(run_output)}")
        logger.info(f"run_output.content type: {type(run_output.content)}")
        logger.info(f"run_output.content repr: {repr(run_output.content)}")
        logger.info(f"run_output.content_type: {run_output.content_type}")
        logger.info(f"run_output.tools: {run_output.tools}")
        logger.info(f"run_output.images: {run_output.images}")
        logger.info(f"run_output.videos: {run_output.videos}")
        logger.info(f"run_output.audio: {run_output.audio}")
        logger.info(f"run_output.files: {run_output.files}")
        logger.info(f"run_output.status: {run_output.status}")

        # Check messages for raw content
        if run_output.messages:
            logger.info(f"=== MESSAGES ({len(run_output.messages)}) ===")
            for i, msg in enumerate(run_output.messages):
                logger.info(
                    f"  Message {i}: role={msg.role}, content={repr(str(msg.content)[:200]) if msg.content else None}"
                )

        # Check get_content_as_string
        if hasattr(run_output, "get_content_as_string"):
            content_str = run_output.get_content_as_string()
            logger.info(f"get_content_as_string(): {repr(content_str)}")

        # Check for brackets in raw content
        content = run_output.content
        if content:
            content_repr = repr(content)
            logger.info(f"Content ends with '[]': {str(content).endswith('[]')}")

            if str(content).endswith("[]"):
                logger.error("!!! BUG FOUND IN AGNO SDK - content ends with []")

            assert not str(content).endswith("[]"), (
                f"AGNO SDK BUG: run_output.content ends with '[]'\n"
                f"Type: {type(content)}\n"
                f"Repr: {content_repr}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
