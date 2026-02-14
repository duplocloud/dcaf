"""
Server Adapter - Bridge between Core Agent and FastAPI server.

This adapter allows a Core Agent to work with the existing
FastAPI server infrastructure, providing full compatibility
with the DuploCloud helpdesk integration.

Example:
    from dcaf.core import Agent
    from dcaf.core.adapters.inbound import ServerAdapter
    from dcaf.agent_server import create_chat_app

    agent = Agent(tools=[...])
    app = create_chat_app(ServerAdapter(agent))
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, cast

from ....schemas.events import (
    DoneEvent,
    ErrorEvent,
    ExecutedToolCallsEvent,
    StreamEvent,
)
from ....schemas.messages import AgentMessage, ExecutedToolCall
from ...agent import Agent

logger = logging.getLogger(__name__)


class ServerAdapter:
    """
    Adapts a Core Agent to work with the existing FastAPI server.

    This implements the AgentProtocol interface expected by
    `dcaf.agent_server.create_chat_app()`.

    The adapter:
    - Converts incoming message format to Core format
    - Runs the Core agent
    - Converts responses back to AgentMessage schema
    - Handles tool call approvals

    Args:
        agent: The Core Agent instance to wrap

    Example:
        from dcaf.core import Agent
        from dcaf.core.adapters.inbound import ServerAdapter
        from dcaf.agent_server import create_chat_app
        import uvicorn

        # Create your agent
        agent = Agent(
            tools=[list_pods, delete_pod],
            system_prompt="You are a Kubernetes assistant."
        )

        # Wrap it for the server
        adapter = ServerAdapter(agent)

        # Create and run the app
        app = create_chat_app(adapter)
        uvicorn.run(app, host="0.0.0.0", port=8000)
    """

    def __init__(self, agent: Agent):
        self.agent = agent

    async def invoke(self, messages: dict[str, list[dict[str, Any]]]) -> AgentMessage:
        """
        Handle a chat request.

        This is called by the /api/sendMessage endpoint.

        Args:
            messages: The message payload from the server
                     Format: {"messages": [{"role": "...", "content": "..."}, ...]}

        Returns:
            AgentMessage with the response
        """
        logger.debug(
            f"ServerAdapter.invoke called with {len(messages.get('messages', []))} messages"
        )

        # Extract messages list and platform context
        messages_list = messages.get("messages", [])
        platform_context = self._extract_platform_context(messages_list)

        # Merge top-level request fields into context (platform_context takes precedence)
        request_fields: dict[str, Any] = messages.get("_request_fields", {})  # type: ignore[assignment]
        context = {**request_fields, **platform_context} if request_fields else platform_context

        # Check for approved tool calls that need to be processed
        executed_tool_calls = self._process_approved_tool_calls(messages_list, context)

        # Convert to Core format (simple list of dicts with role/content)
        core_messages = self._convert_messages(messages_list)

        # Inject executed tool results into conversation so the LLM can see them.
        # Replace the last user message (the approval text) to maintain strict
        # user/assistant alternation required by Bedrock.
        if executed_tool_calls:
            result_parts = [
                f"Tool result for {tc.name} with inputs {tc.input}: {tc.output}"
                for tc in executed_tool_calls
            ]
            result_content = "\n\n".join(result_parts)
            if core_messages and core_messages[-1]["role"] == "user":
                core_messages[-1]["content"] = result_content
            else:
                core_messages.append({"role": "user", "content": result_content})

        if not core_messages:
            return AgentMessage(content="No messages provided.")

        # Run the core agent
        try:
            response = await self.agent.run(
                messages=cast(list[Any], core_messages),
                context=context,
            )

            # Convert to AgentMessage using native to_message()
            agent_msg = response.to_message()

            # Add any executed tool calls from this request
            if executed_tool_calls:
                agent_msg.data.executed_tool_calls.extend(executed_tool_calls)  # type: ignore[arg-type]

            # If there are pending approvals, ensure helpful content
            if response.needs_approval and not agent_msg.content:
                agent_msg.content = "I need your approval to execute the following tools:"

            return agent_msg  # type: ignore[return-value]

        except Exception as e:
            logger.exception(f"Error in agent execution: {e}")
            return AgentMessage(content=f"Error: {str(e)}")

    async def invoke_stream(
        self, messages: dict[str, list[dict[str, Any]]]
    ) -> AsyncIterator[StreamEvent]:
        """
        Handle a streaming chat request.

        This is called by the /api/chat-stream endpoint.
        Uses true token-by-token streaming from the Agent.

        Args:
            messages: The message payload from the server

        Yields:
            StreamEvent objects for NDJSON streaming
        """
        logger.debug("ServerAdapter.invoke_stream called")

        # Extract messages list and platform context
        messages_list = messages.get("messages", [])
        platform_context = self._extract_platform_context(messages_list)

        # Merge top-level request fields into context (platform_context takes precedence)
        request_fields: dict[str, Any] = messages.get("_request_fields", {})  # type: ignore[assignment]
        context = {**request_fields, **platform_context} if request_fields else platform_context

        # Execute any approved tool calls before streaming
        executed_tool_calls = self._process_approved_tool_calls(messages_list, context)
        if executed_tool_calls:
            yield ExecutedToolCallsEvent(executed_tool_calls=executed_tool_calls)

        # Convert to Core format
        core_messages = self._convert_messages(messages_list)

        # Inject executed tool results into conversation so the LLM can see them.
        # Replace the last user message (the approval text) to maintain strict
        # user/assistant alternation required by Bedrock.
        if executed_tool_calls:
            result_parts = [
                f"Tool result for {tc.name} with inputs {tc.input}: {tc.output}"
                for tc in executed_tool_calls
            ]
            result_content = "\n\n".join(result_parts)
            if core_messages and core_messages[-1]["role"] == "user":
                core_messages[-1]["content"] = result_content
            else:
                core_messages.append({"role": "user", "content": result_content})

        if not core_messages:
            yield ErrorEvent(error="No messages provided")
            return

        try:
            # Use true streaming from the Agent
            async for event in self.agent.run_stream(
                messages=cast(list[Any], core_messages),
                context=context,
            ):
                # Echo top-level request fields in DoneEvent for client correlation
                if isinstance(event, DoneEvent) and request_fields:
                    event.meta_data["request_context"] = request_fields
                yield event  # type: ignore[misc]

        except Exception as e:
            logger.exception(f"Stream error: {e}")
            yield ErrorEvent(error=str(e))

    def _convert_messages(self, messages_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert from server message format to Core format.

        Server format includes rich data (tool_calls, executed_cmds, etc.)
        Core format is simple: [{"role": "...", "content": "..."}]
        """
        core_messages = []

        for msg in messages_list:
            role = msg.get("role")
            content = msg.get("content", "")

            # Only include user and assistant messages
            if role in ["user", "assistant"]:
                core_messages.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

        return core_messages

    def _extract_platform_context(self, messages_list: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Extract platform context from the latest user message.

        The platform_context contains runtime info like tenant_name,
        k8s_namespace, AWS credentials, etc.
        """
        # Find the last user message
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                platform_context = msg.get("platform_context", {})
                if platform_context:
                    # Convert Pydantic model to dict if needed
                    if hasattr(platform_context, "model_dump"):
                        result = platform_context.model_dump()
                        return result if isinstance(result, dict) else {}
                    return platform_context if isinstance(platform_context, dict) else {}
        return {}

    def _process_approved_tool_calls(
        self,
        messages_list: list[dict[str, Any]],
        platform_context: dict[str, Any],
    ) -> list[ExecutedToolCall]:
        """
        Process any approved tool calls from incoming messages.

        When the user approves tool calls, they come back in the
        message data. We execute them here and return results.
        """
        executed_tools: list[ExecutedToolCall] = []

        if not messages_list:
            return executed_tools

        # Get the latest message's data
        latest_message = messages_list[-1]
        data = latest_message.get("data", {})
        tool_calls = data.get("tool_calls", [])

        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            tool_input = tool_call.get("input", {})
            tool_id = tool_call.get("id")

            if tool_call.get("execute", False):
                # User approved - execute the tool
                result = self._execute_tool(tool_name, tool_input, platform_context)
                executed_tools.append(
                    ExecutedToolCall(
                        id=tool_id,
                        name=tool_name,
                        input=tool_input,
                        output=result,
                    )
                )
            elif tool_call.get("rejection_reason"):
                # User rejected
                executed_tools.append(
                    ExecutedToolCall(
                        id=tool_id,
                        name=tool_name,
                        input=tool_input,
                        output=f"Tool rejected: {tool_call['rejection_reason']}",
                    )
                )

        return executed_tools

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        platform_context: dict[str, Any],
    ) -> str:
        """Execute a tool by name."""
        # Find the tool in the agent's tool list
        for tool in self.agent.tools:
            if getattr(tool, "name", None) == tool_name:
                try:
                    if hasattr(tool, "execute"):
                        result = tool.execute(tool_input, platform_context)
                        return str(result) if result is not None else ""
                    elif callable(tool):
                        result = tool(**tool_input)
                        return str(result) if result is not None else ""
                except Exception as e:
                    return f"Error executing {tool_name}: {str(e)}"

        return f"Tool '{tool_name}' not found"
