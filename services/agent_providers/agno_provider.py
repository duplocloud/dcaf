"""
Agno Agent Provider Implementation

Implements the AgentProvider interface using the Agno framework.
"""

import logging
import os
from typing import Any, Callable, cast

import aioboto3
from agno.agent import Agent
from agno.models.aws import AwsBedrock
from agno.tools import tool

from .base import AgentProvider, AgentResponse, ToolDefinition

logger = logging.getLogger(__name__)


class AgnoProvider(AgentProvider):
    """
    Agno framework implementation of the AgentProvider interface.

    Wraps Agno's Agent and tool system to provide a standardized interface.
    """

    def __init__(self):
        """Initialize the Agno provider."""
        self._cached_session: Any = None
        self._cached_model: Any = None

    def get_provider_name(self) -> str:
        """Return the provider name."""
        return "agno"

    def get_provider_version(self) -> str:
        """Return the Agno framework version."""
        try:
            import agno
            return getattr(agno, "__version__", "unknown")
        except Exception:
            return "unknown"

    def supports_streaming(self) -> bool:
        """Agno supports streaming."""
        return True

    def supports_reasoning(self) -> bool:
        """Agno supports explicit reasoning mode."""
        return True

    def _get_bedrock_model(self) -> AwsBedrock:
        """
        Get or create a cached AWS Bedrock model.

        Uses session caching for performance optimization.
        """
        if self._cached_model is not None:
            return self._cached_model

        fallback_region = os.getenv("AWS_REGION", "us-west-2")
        model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")

        # Infer region from ARN
        region = self._infer_region_from_model_id(model_id, fallback_region)

        # Use correct AWS profile for local development
        env_value = os.getenv("ENVIRONMENT", "").lower()
        if env_value == "local" or env_value == "test":
            logger.info(f"Agno: Using AWS profile 'test10' for local development (region: {region})")
            async_session = aioboto3.Session(region_name=region, profile_name="test10")
        else:
            logger.info(f"Agno: Using default AWS credentials (region: {region})")
            async_session = aioboto3.Session(region_name=region)

        # Cache the session
        self._cached_session = async_session

        # Create and cache the model
        # Temperature: 0.0-1.0 (lower = more deterministic/factual)
        temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))

        # Max tokens: Controls response length (higher = more detailed responses)
        # Claude's max: 4096 tokens (~3000 words)
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))

        self._cached_model = AwsBedrock(
            id=model_id,
            aws_region=region,
            async_session=async_session,
            temperature=temperature,
            max_tokens=max_tokens,  # Allow longer, more detailed responses
        )

        logger.info(
            f"Agno: Initialized Bedrock model {model_id} "
            f"(temperature={temperature}, max_tokens={max_tokens})"
        )
        return self._cached_model

    @staticmethod
    def _infer_region_from_model_id(model_id: str, fallback_region: str) -> str:
        """
        Extract AWS region from Bedrock model ARN.

        Args:
            model_id: Model ID or ARN
            fallback_region: Region to use if extraction fails

        Returns:
            str: AWS region
        """
        try:
            if model_id.startswith("arn:aws:bedrock:"):
                parts = model_id.split(":")
                if len(parts) > 3 and parts[3]:
                    return parts[3]
        except Exception:
            pass
        return fallback_region

    def _convert_tool_to_agno(self, tool_def: ToolDefinition) -> Callable:
        """
        Convert a ToolDefinition to Agno's @tool format.

        Args:
            tool_def: Framework-agnostic tool definition

        Returns:
            Agno-decorated tool function
        """
        # Wrap the function with Agno's @tool decorator
        agno_tool = tool(
            name=tool_def.name,
            description=tool_def.description
        )(tool_def.function)

        return cast(Callable[..., Any], agno_tool)

    async def initialize_agent(
        self,
        system_prompt: str,
        tools: list[ToolDefinition],
        message_history: list[dict],
        **kwargs
    ) -> Any:
        """
        Initialize an Agno agent with conversation history.

        Args:
            system_prompt: Instructions for the agent
            tools: List of tool definitions
            message_history: Previous messages for conversation context
            **kwargs: Agno-specific options (reasoning, streaming, etc.)

        Returns:
            dict: Agent instance with attached history
        """
        model = self._get_bedrock_model()

        # Convert tools to Agno format
        agno_tools = [self._convert_tool_to_agno(t) for t in tools]

        # Extract Agno-specific options from kwargs
        reasoning = kwargs.get("reasoning", False)
        telemetry = kwargs.get("telemetry", True)
        stream = kwargs.get("stream", False)

        logger.info(
            f"Agno: Creating agent with {len(agno_tools)} tools "
            f"(reasoning={reasoning}, stream={stream}, history_messages={len(message_history)})"
        )

        # WORKAROUND: Limit tool calls to prevent Agno/Bedrock bug with parallel tool execution
        # The bug causes "Expected toolResult blocks" errors when Bedrock requests multiple tools
        # See: ValidationException when Bedrock returns multiple toolUse blocks
        tool_limit = int(os.getenv("AGNO_TOOL_CALL_LIMIT", "1"))
        
        # WORKAROUND: Prepend instruction to prevent model from requesting parallel tools
        # This is necessary because Agno has a bug handling multiple toolUse blocks from Bedrock
        single_tool_instruction = (
            "IMPORTANT: You must call tools ONE AT A TIME. Never request multiple tool calls "
            "in a single response. Wait for each tool result before calling the next tool.\n\n"
        )
        modified_prompt = single_tool_instruction + system_prompt

        agent = Agent(
            model=model,
            instructions=modified_prompt,
            tools=agno_tools,
            reasoning=reasoning,
            telemetry=telemetry,
            stream=stream,
            tool_call_limit=tool_limit,  # Limit concurrent tool calls to avoid Bedrock bug
            # Note: add_history_to_context, show_tool_calls, markdown not supported in this Agno version
            # Verbosity is controlled via system prompt instructions instead
        )

        # Wrap agent with history for use in run_agent
        # This preserves the conversation context across turns
        return {
            "agent": agent,
            "message_history": message_history
        }

    async def run_agent(
        self,
        agent: Any,
        user_message: str,
        **kwargs
    ) -> AgentResponse:
        """
        Execute the Agno agent with a user message and conversation history.

        Args:
            agent: Agent wrapper dict with 'agent' and 'message_history' keys
            user_message: User's input message
            **kwargs: Additional run options

        Returns:
            AgentResponse: Normalized response
        """
        # Extract agent and history from wrapper
        if isinstance(agent, dict):
            actual_agent = agent["agent"]
            message_history = agent.get("message_history", [])
        else:
            # Fallback for backward compatibility
            actual_agent = agent
            message_history = []

        # Build message list for Agno
        # Agno's arun() accepts List[Message] as input, which allows us to pass
        # conversation history + current message together
        messages_to_send = []
        skipped_count = 0
        
        # WORKAROUND: Option to disable history to debug Bedrock tool issues
        # When disabled, each turn is independent (model will re-query if needed)
        disable_history = os.getenv("AGNO_DISABLE_HISTORY", "false").lower() == "true"
        
        # TEST FLAG: Disable filtering to reproduce original bug
        disable_filtering = os.getenv("DISABLE_TOOL_FILTERING", "false").lower() == "true"
        
        if disable_history:
            logger.info("Agno: History disabled via AGNO_DISABLE_HISTORY=true")
            message_history = []
        
        if disable_filtering:
            logger.warning("⚠️ Agno: Tool filtering DISABLED (bug reproduction mode)")
        
        # Add history messages
        # IMPORTANT: Filter out tool-related messages to prevent Bedrock
        # ValidationException: "Expected toolResult blocks..."
        # Agno handles tool calls internally within a single arun() call.
        for msg in message_history or []:
            if not isinstance(msg, dict):
                continue
            
            role = msg.get("role")
            content = msg.get("content")
            
            # If filtering is disabled (for bug reproduction), skip all filtering
            if not disable_filtering:
                # Skip messages with no content (tool-only messages)
                if content is None:
                    skipped_count += 1
                    continue
                
                # Skip empty string content
                if isinstance(content, str) and not content.strip():
                    skipped_count += 1
                    continue
                
                # Skip messages where content is a list (Bedrock tool blocks)
                # These are toolUse (assistant) or toolResult (user) messages
                if isinstance(content, list):
                    skipped_count += 1
                    logger.debug(f"Agno: Skipping tool-related message (role={role})")
                    continue
            
            cleaned = {"role": role, "content": content}
            if "name" in msg:
                cleaned["name"] = msg["name"]
            messages_to_send.append(cleaned)
        
        if skipped_count > 0:
            logger.info(f"Agno: Filtered out {skipped_count} tool-related messages from history")

        # Validate message structure for Bedrock compatibility:
        # 1. First message must be from 'user'
        # 2. Messages must alternate between user/assistant
        # Skip validation if filtering is disabled (for bug reproduction)
        if not disable_filtering:
            # Remove leading assistant messages (Bedrock requires user first)
            while messages_to_send and messages_to_send[0].get("role") != "user":
                removed = messages_to_send.pop(0)
                logger.warning(f"Agno: Removed leading {removed.get('role')} message (Bedrock requires user first)")
            
            # Validate alternation: Bedrock requires strict user/assistant alternation
            # If filtering broke the alternation, we need to fix it
            validated_messages = []
            last_role = None
            for msg in messages_to_send:
                role = msg.get("role")
                if role == last_role:
                    # Consecutive same-role messages - skip to maintain alternation
                    logger.warning(f"Agno: Skipping consecutive {role} message to maintain alternation")
                    continue
                validated_messages.append(msg)
                last_role = role
            
            if len(validated_messages) != len(messages_to_send):
                logger.info(
                    f"Agno: Fixed alternation - {len(messages_to_send)} -> {len(validated_messages)} messages"
                )
            messages_to_send = validated_messages

            # Add current user message
            # If the last message in history is already 'user', we have a problem
            if messages_to_send and messages_to_send[-1].get("role") == "user":
                logger.warning("Agno: Last history message is 'user' - removing to allow current message")
                messages_to_send.pop()
        
        messages_to_send.append({
            "role": "user",
            "content": user_message
        })

        if len(messages_to_send) > 1:
            logger.info(
                "Agno: Running agent with %s history messages + current message = %s total messages",
                len(messages_to_send) - 1,
                len(messages_to_send),
            )
            # Debug: Log each message's role and content length
            for i, msg in enumerate(messages_to_send):
                content = msg.get("content", "")
                content_preview = content[:100] if isinstance(content, str) else str(type(content))
                logger.debug(
                    f"  messages[{i}]: role={msg.get('role')}, "
                    f"content_type={type(content).__name__}, "
                    f"content_len={len(content) if isinstance(content, str) else 'N/A'}, "
                    f"preview={content_preview!r}"
                )
        else:
            logger.info("Agno: Running agent with 1 message (no history)")

        # Pass all messages to Agno's arun()
        # According to Agno docs, arun() accepts List[Dict] with role/content
        logger.info(f"Agno: Sending {len(messages_to_send)} messages to arun()")
        run_output = await actual_agent.arun(messages_to_send)

        # Extract content
        content = ""
        if hasattr(run_output, 'content'):
            content = run_output.content or ""
        elif isinstance(run_output, dict):
            content = run_output.get("content", "")
        else:
            content = str(run_output)

        # Extract metrics
        metrics = {}
        if hasattr(run_output, 'metrics') and run_output.metrics:
            metrics = {
                'input_tokens': getattr(run_output.metrics, 'input_tokens', 0),
                'output_tokens': getattr(run_output.metrics, 'output_tokens', 0),
                'total_tokens': getattr(run_output.metrics, 'total_tokens', 0),
                'duration': getattr(run_output.metrics, 'duration', 0),
                'time_to_first_token': getattr(run_output.metrics, 'time_to_first_token', None),
                'response_timer': getattr(run_output.metrics, 'response_timer', None),
            }

            # Log metrics for monitoring
            logger.info(
                f"📊 Agno Metrics: "
                f"tokens={metrics['total_tokens']} "
                f"(in={metrics['input_tokens']}, out={metrics['output_tokens']}), "
                f"duration={metrics['duration']:.3f}s"
            )

        # Extract tool calls
        tool_calls = []
        if hasattr(run_output, 'tools') and run_output.tools:
            for tool_exec in run_output.tools:
                tool_calls.append({
                    'name': getattr(tool_exec, 'tool_name', ''),
                    'args': getattr(tool_exec, 'tool_args', {}),
                    'result': getattr(tool_exec, 'result', None),
                })

            # Log tool execution for monitoring
            logger.info(f"🔧 Agno Tools: Executed {len(tool_calls)} tool call(s)")
            for i, tool_call in enumerate(tool_calls, 1):
                logger.debug(f"  Tool {i}: {tool_call['name']}")

        # Build metadata
        metadata = {
            'framework': 'agno',
            'model': getattr(actual_agent.model, 'id', 'unknown') if hasattr(actual_agent, 'model') else 'unknown',
            'run_id': getattr(run_output, 'run_id', None) if hasattr(run_output, 'run_id') else None,
            'session_id': getattr(run_output, 'session_id', None) if hasattr(run_output, 'session_id') else None,
        }

        # Log telemetry summary
        if metadata.get('run_id') or metadata.get('session_id'):
            logger.info(
                f"🔍 Agno Telemetry: "
                f"session_id={metadata.get('session_id', 'N/A')}, "
                f"run_id={metadata.get('run_id', 'N/A')}, "
                f"model={metadata['model']}"
            )

        return AgentResponse(
            content=content,
            metadata=metadata,
            tool_calls=tool_calls,
            metrics=metrics,
        )

    async def cleanup(self):
        """Clean up cached resources."""
        self._cached_session = None
        self._cached_model = None
        logger.info("Agno: Cleaned up cached resources")

