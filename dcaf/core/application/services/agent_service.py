"""AgentService - main agent execution orchestration."""

import logging
from collections.abc import AsyncIterator, Iterator
from typing import Any

from ...domain.entities import Conversation, Message, MessageRole, ToolCall
from ...domain.services import ApprovalPolicy
from ...domain.value_objects import (
    ConversationId,
    MessageContent,
    PlatformContext,
    ToolCallId,
    ToolInput,
)
from ..dto.requests import AgentRequest
from ..dto.responses import AgentResponse, DataDTO, StreamEvent, ToolCallDTO
from ..ports.agent_runtime import AgentRuntime
from ..ports.conversation_repository import ConversationRepository
from ..ports.event_publisher import EventPublisher
from ..ports.mcp_protocol import MCPToolLike

logger = logging.getLogger(__name__)


class AgentService:
    """
    Application service that orchestrates agent execution.

    This service coordinates:
    1. Loading/creating the conversation
    2. Adding the user message
    3. Invoking the agent runtime
    4. Handling tool calls and approvals
    5. Persisting the conversation
    6. Publishing domain events

    Example:
        runtime = AgnoAdapter(model="claude-3-sonnet")
        conversations = InMemoryConversationRepository()
        events = LoggingEventPublisher()

        agent_service = AgentService(
            runtime=runtime,
            conversations=conversations,
            events=events,
        )

        response = agent_service.execute(AgentRequest(
            content="What pods are running?",
            tools=[kubectl_tool],
        ))
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        conversations: ConversationRepository,
        events: EventPublisher | None = None,
        approval_policy: ApprovalPolicy | None = None,
    ) -> None:
        """
        Initialize the service.

        Args:
            runtime: The agent runtime adapter
            conversations: Repository for conversation persistence
            events: Optional event publisher
            approval_policy: Optional custom approval policy
        """
        self._runtime = runtime
        self._conversations = conversations
        self._events = events
        self._policy = approval_policy or ApprovalPolicy()

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute an agent turn.

        This is the main entry point for agent execution.
        It handles the full lifecycle of a turn:
        1. Get or create conversation
        2. Add user message
        3. Invoke agent
        4. Process tool calls
        5. Return response

        Args:
            request: The agent request

        Returns:
            AgentResponse with the agent's response
        """
        # 1. Get or create conversation
        conversation = self._get_or_create_conversation(request)
        context = request.get_platform_context()
        conversation.update_context(context)

        # 2. Add user message
        conversation.add_user_message(request.content)

        # 3. Invoke the agent runtime (async)
        runtime_response = await self._runtime.invoke(
            messages=conversation.messages,
            tools=request.tools,
            system_prompt=request.system_prompt,
            static_system=request.static_system,
            dynamic_system=request.dynamic_system,
            platform_context=context.to_dict() if context else None,
        )

        # 4. Process the response
        response = self._process_response(
            conversation=conversation,
            runtime_response=runtime_response,
            tools=request.tools,
            context=context,
        )

        # 5. Save conversation
        self._conversations.save(conversation)

        # 6. Publish domain events
        self._publish_events(conversation)

        return response

    async def execute_stream(self, request: AgentRequest) -> AsyncIterator[StreamEvent]:
        """
        Execute an agent turn with streaming response.

        Yields StreamEvent objects as the response is generated.
        The final event will be MESSAGE_END with the complete response.

        Args:
            request: The agent request

        Yields:
            StreamEvent objects
        """
        # 1. Get or create conversation
        conversation = self._get_or_create_conversation(request)
        context = request.get_platform_context()
        conversation.update_context(context)

        # 2. Add user message
        conversation.add_user_message(request.content)

        # 3. Yield message start
        yield StreamEvent.message_start()

        # 4. Stream from runtime (async)
        collected_text: list[str] = []
        collected_tool_calls: list[ToolCallDTO] = []

        async for event in self._runtime.invoke_stream(
            messages=conversation.messages,
            tools=request.tools,
            system_prompt=request.system_prompt,
            static_system=request.static_system,
            dynamic_system=request.dynamic_system,
            platform_context=context.to_dict() if context else None,
        ):
            # Track text for final response
            if event.event_type.value == "text_delta":
                collected_text.append(event.data.get("text", ""))

            yield event

        # 5. Build final response
        final_text = "".join(collected_text) if collected_text else None

        response = AgentResponse(
            conversation_id=str(conversation.id),
            text=final_text,
            data=DataDTO(tool_calls=collected_tool_calls),
            is_complete=True,
        )

        # 6. Add assistant message to conversation
        if final_text:
            conversation.add_assistant_message(final_text)

        # 7. Save conversation
        self._conversations.save(conversation)

        # 8. Publish events
        self._publish_events(conversation)

        # 9. Yield final event
        yield StreamEvent.message_end(response)

    def resume(
        self,
        conversation_id: str,
        tools: list,
    ) -> AgentResponse:
        """
        Resume execution after tool calls have been approved/rejected.

        This is called after the user has approved or rejected pending tool calls.
        It executes the approved tools and continues the conversation.

        Args:
            conversation_id: ID of the conversation
            tools: Available tools

        Returns:
            AgentResponse with results
        """
        # 1. Load conversation
        conv_id = ConversationId(conversation_id)
        conversation = self._conversations.get(conv_id)
        if not conversation:
            raise ValueError(f"Conversation not found: {conversation_id}")

        # 2. Execute approved tool calls
        context = conversation.context
        executed_results = []

        for tool_call in conversation.all_tool_calls:
            if tool_call.is_approved:
                # Find the tool
                tool = self._find_tool(tool_call.tool_name, tools)
                if tool:
                    try:
                        result = tool.execute(
                            tool_call.input.parameters,
                            context.to_dict() if tool.requires_platform_context else None,
                        )
                        conversation.complete_tool_call(str(tool_call.id), result)
                        executed_results.append((tool_call, result))
                    except Exception as e:
                        conversation.fail_tool_call(str(tool_call.id), str(e))
                        executed_results.append((tool_call, str(e)))

        # 3. Add tool results to conversation and invoke again
        # (This would add tool result messages and re-invoke the LLM)

        # 4. Save and return
        self._conversations.save(conversation)
        self._publish_events(conversation)

        return AgentResponse(
            conversation_id=str(conversation.id),
            data=DataDTO(
                tool_calls=[ToolCallDTO.from_tool_call(tc) for tc in conversation.all_tool_calls]
            ),
            is_complete=not conversation.has_pending_approvals,
        )

    # Private methods

    def _get_or_create_conversation(self, request: AgentRequest) -> Conversation:
        """
        Get existing conversation or create a new one.

        If request.messages is provided (external message history),
        creates a new conversation and populates it with that history.
        """
        context = request.get_platform_context()

        # If external message history is provided, use that
        if request.messages:
            return self._create_from_message_history(
                messages=request.messages,
                system_prompt=request.system_prompt,
                context=context,
            )

        # Try to load existing conversation by ID
        conv_id = request.get_conversation_id()
        if conv_id:
            conversation = self._conversations.get(conv_id)
            if conversation:
                return conversation

        # Create new empty conversation
        if request.system_prompt:
            conversation = Conversation.with_system_prompt(
                request.system_prompt,
                context=context,
            )
        else:
            conversation = Conversation.create(context=context)

        return conversation

    def _create_from_message_history(
        self,
        messages: list[dict],
        system_prompt: str | None,
        context: PlatformContext,
    ) -> Conversation:
        """
        Create a conversation from external message history.

        This is used when the conversation history comes from an external
        source (e.g., DuploCloud helpdesk framework) rather than being
        stored internally.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            system_prompt: Optional system prompt to prepend
            context: Platform context

        Returns:
            A new Conversation populated with the message history
        """
        # Create the conversation
        if system_prompt:
            conversation = Conversation.with_system_prompt(system_prompt, context=context)
        else:
            conversation = Conversation.create(context=context)

        # Add each message from history
        for msg in messages:
            role = msg.get("role", "").lower()
            content = msg.get("content", "")

            if not content:
                continue

            if role == "user":
                # Note: This won't raise ConversationBlocked because we're
                # replaying history, not adding new messages to a blocked conversation
                conversation._messages.append(
                    Message(role=MessageRole.USER, content=MessageContent.from_text(content))
                )
            elif role == "assistant":
                conversation._messages.append(
                    Message(role=MessageRole.ASSISTANT, content=MessageContent.from_text(content))
                )
            elif role == "system":
                conversation._messages.append(
                    Message(role=MessageRole.SYSTEM, content=MessageContent.from_text(content))
                )
            # Ignore unknown roles

        return conversation

    def _process_response(
        self,
        conversation: Conversation,
        runtime_response: AgentResponse,
        tools: list,
        context: PlatformContext,
    ) -> AgentResponse:
        """Process the runtime response and handle tool calls."""
        # Add assistant message
        if runtime_response.text:
            conversation.add_assistant_message(runtime_response.text)

        # Process tool calls
        processed_tool_calls = []
        for tc_dto in runtime_response.tool_calls:
            # Find the tool to check approval requirements
            tool = self._find_tool(tc_dto.name, tools)
            requires_approval = tool.requires_approval if tool else tc_dto.requires_approval

            # Create domain entity
            tool_call = ToolCall(
                id=ToolCallId(tc_dto.id),
                tool_name=tc_dto.name,
                input=ToolInput(tc_dto.input),
                description=tc_dto.description,
                intent=tc_dto.intent,
                requires_approval=requires_approval,
            )

            if requires_approval:
                # Add to pending approvals
                conversation.request_tool_approval([tool_call])
                processed_tool_calls.append(ToolCallDTO.from_tool_call(tool_call))
            else:
                # Execute immediately
                tool_call.auto_approve()
                if tool:
                    try:
                        result = tool.execute(
                            tc_dto.input,
                            context.to_dict() if tool.requires_platform_context else None,
                        )
                        tool_call.start_execution()
                        tool_call.complete(result)
                    except Exception as e:
                        tool_call.start_execution()
                        tool_call.fail(str(e))

                processed_tool_calls.append(ToolCallDTO.from_tool_call(tool_call))

        return AgentResponse(
            conversation_id=str(conversation.id),
            text=runtime_response.text,
            data=DataDTO(tool_calls=processed_tool_calls),
            has_pending_approvals=conversation.has_pending_approvals,
            is_complete=not conversation.has_pending_approvals,
        )

    def _find_tool(self, name: str, tools: list) -> Any:
        """Find a tool by name."""
        for tool in tools:
            # Skip MCPToolLike instances - they're toolkit containers, not individual tools.
            # MCP tools are handled directly by the runtime adapter (e.g., Agno).
            if isinstance(tool, MCPToolLike):
                continue
            if tool.name == name:
                return tool
        return None

    def _publish_events(self, conversation: Conversation) -> None:
        """Publish domain events from the conversation."""
        if self._events:
            events = conversation.clear_events()
            self._events.publish_all(events)
