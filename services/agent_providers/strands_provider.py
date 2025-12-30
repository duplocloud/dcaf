"""
Strands Agent Provider Implementation

Implements the AgentProvider interface using AWS Strands Agents framework.
This is a backup provider in case Agno has issues with Bedrock tool handling.

Key advantages of Strands:
- AWS-native, built for Bedrock
- SequentialToolExecutor to avoid parallel tool issues
- Simpler tool definition with @tool decorator
"""

import asyncio
import inspect
import logging
import os
from typing import Any, Callable, cast

from .base import AgentProvider, AgentResponse, ToolDefinition

logger = logging.getLogger(__name__)


class StrandsProvider(AgentProvider):
    """
    Strands Agents framework implementation of the AgentProvider interface.

    Uses AWS Strands Agents with Bedrock as the backend.
    """

    def __init__(self):
        """Initialize the Strands provider."""
        self._agent = None
        self._model_id = None

    def get_provider_name(self) -> str:
        """Return the provider name."""
        return "strands"

    def get_provider_version(self) -> str:
        """Return the Strands framework version."""
        try:
            import strands
            return getattr(strands, "__version__", "unknown")
        except ImportError:
            return "not-installed"
        except Exception:
            return "unknown"

    def supports_streaming(self) -> bool:
        """Strands supports streaming."""
        return True

    def supports_reasoning(self) -> bool:
        """Strands supports reasoning with extended thinking models."""
        return True

    def _get_model_id(self) -> str:
        """
        Get the Bedrock model ID from environment.

        Returns:
            str: Model ID for Bedrock
        """
        if self._model_id is None:
            self._model_id = os.getenv(
                "BEDROCK_MODEL_ID",
                "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
            )
        return self._model_id

    def _convert_tool_to_strands(self, tool_def: ToolDefinition) -> Callable:
        """
        Convert a ToolDefinition to Strands' @tool format.

        Args:
            tool_def: Framework-agnostic tool definition

        Returns:
            Strands-decorated tool function
        """
        from strands import tool

        original_func = tool_def.function
        is_async = asyncio.iscoroutinefunction(original_func)

        if is_async:
            # For async functions, create an async wrapper
            @tool(name=tool_def.name, description=tool_def.description)
            async def async_wrapped_tool(**kwargs):
                return await original_func(**kwargs)

            async_wrapped_tool.__name__ = tool_def.name
            async_wrapped_tool.__doc__ = tool_def.description

            # Copy signature from original function for parameter detection
            async_wrapped_tool.__signature__ = inspect.signature(original_func)

            return cast(Callable[..., Any], async_wrapped_tool)
        else:
            # For sync functions, wrap directly
            strands_tool = tool(
                name=tool_def.name,
                description=tool_def.description
            )(original_func)

            return cast(Callable[..., Any], strands_tool)

    async def initialize_agent(
        self,
        system_prompt: str,
        tools: list[ToolDefinition],
        message_history: list[dict],
        **kwargs
    ) -> Any:
        """
        Initialize a Strands agent with conversation history.

        Args:
            system_prompt: Instructions for the agent
            tools: List of tool definitions
            message_history: Previous messages for conversation context
            **kwargs: Strands-specific options

        Returns:
            dict: Agent instance with attached history
        """
        from strands import Agent
        from strands.tools.executors import SequentialToolExecutor

        model_id = self._get_model_id()

        # Convert tools to Strands format
        strands_tools = [self._convert_tool_to_strands(t) for t in tools]

        # Use SequentialToolExecutor to avoid parallel tool issues
        # This is the key advantage over Agno for Bedrock compatibility
        use_sequential = os.getenv("STRANDS_SEQUENTIAL_TOOLS", "true").lower() == "true"

        logger.info(
            f"Strands: Creating agent with {len(strands_tools)} tools "
            f"(model={model_id}, sequential_tools={use_sequential}, "
            f"history_messages={len(message_history)})"
        )

        agent_kwargs = {
            "model": model_id,
            "system_prompt": system_prompt,
            "tools": strands_tools,
        }

        # Use sequential executor to avoid the parallel tool bug
        if use_sequential:
            agent_kwargs["tool_executor"] = SequentialToolExecutor()

        agent = Agent(**agent_kwargs)

        # Wrap agent with history for use in run_agent
        return {
            "agent": agent,
            "message_history": message_history,
            "system_prompt": system_prompt,
        }

    async def run_agent(
        self,
        agent: Any,
        user_message: str,
        **kwargs
    ) -> AgentResponse:
        """
        Execute the Strands agent with a user message.

        Args:
            agent: Agent wrapper dict with 'agent' and 'message_history' keys
            user_message: User's input message
            **kwargs: Additional run options

        Returns:
            AgentResponse: Normalized response
        """
        import asyncio

        # Extract agent and history from wrapper
        if isinstance(agent, dict):
            actual_agent = agent["agent"]
            message_history = agent.get("message_history", [])
        else:
            actual_agent = agent
            message_history = []

        # Filter history messages (same logic as Agno provider)
        filtered_history = []
        skipped_count = 0

        for msg in message_history or []:
            if not isinstance(msg, dict):
                continue

            content = msg.get("content")

            # Skip tool-related messages
            if content is None:
                skipped_count += 1
                continue
            if isinstance(content, str) and not content.strip():
                skipped_count += 1
                continue
            if isinstance(content, list):
                skipped_count += 1
                continue

            filtered_history.append(msg)

        if skipped_count > 0:
            logger.info(f"Strands: Filtered out {skipped_count} tool-related messages from history")

        # Build conversation for Strands
        # Note: Strands handles history differently - we may need to use its native session management
        messages_to_send = []
        for msg in filtered_history:
            messages_to_send.append(msg)

        # Add current user message
        messages_to_send.append({
            "role": "user",
            "content": user_message
        })

        logger.info(f"Strands: Running agent with {len(messages_to_send)} messages")

        # Strands agent invocation
        # Note: Strands uses synchronous API by default, run in thread
        try:
            # Run the synchronous Strands agent in a thread pool
            result = await asyncio.to_thread(
                actual_agent,  # Strands agents are callable
                user_message   # Pass just the current message (history handled by agent state)
            )
        except Exception as e:
            logger.error(f"Strands agent error: {e}")
            return AgentResponse(
                content=f"Error: {str(e)}",
                metadata={"framework": "strands", "error": str(e)},
                tool_calls=[],
                metrics={},
            )

        # Extract content from Strands response
        content = ""
        if hasattr(result, 'message'):
            content = result.message or ""
        elif isinstance(result, str):
            content = result
        elif hasattr(result, 'content'):
            content = result.content or ""
        else:
            content = str(result)

        # Extract metrics if available
        metrics = {}
        if hasattr(result, 'metrics'):
            metrics = {
                'input_tokens': getattr(result.metrics, 'input_tokens', 0),
                'output_tokens': getattr(result.metrics, 'output_tokens', 0),
                'total_tokens': getattr(result.metrics, 'total_tokens', 0),
            }

        # Extract tool calls if available
        tool_calls = []
        if hasattr(result, 'tool_calls') and result.tool_calls:
            for tc in result.tool_calls:
                tool_calls.append({
                    'name': getattr(tc, 'name', ''),
                    'args': getattr(tc, 'arguments', {}),
                    'result': getattr(tc, 'result', None),
                })

        # Build metadata
        metadata = {
            'framework': 'strands',
            'model': self._get_model_id(),
        }

        logger.info(
            f"📊 Strands Metrics: "
            f"tokens={metrics.get('total_tokens', 0)} "
            f"(in={metrics.get('input_tokens', 0)}, out={metrics.get('output_tokens', 0)})"
        )

        return AgentResponse(
            content=content,
            metadata=metadata,
            tool_calls=tool_calls,
            metrics=metrics,
        )

    async def cleanup(self):
        """Clean up resources."""
        self._agent = None
        self._model_id = None
        logger.info("Strands: Cleaned up resources")
