"""Message converter for Agno framework."""

from typing import Any

from ....application.dto.responses import AgentResponse, StreamEvent, StreamEventType, ToolCallDTO
from ....domain.entities import Message, MessageRole
from ....domain.value_objects import ContentBlock, ContentType, MessageContent
from .types import (
    AgnoContentBlock,
    AgnoMessage,
)


class AgnoMessageConverter:
    """
    Converts messages between dcaf and Agno formats.

    Handles bidirectional conversion:
    - to_agno: Convert dcaf Messages to Agno format for API calls
    - from_agno: Convert Agno responses back to dcaf format

    Also handles streaming event conversion.

    Example:
        converter = AgnoMessageConverter()

        # Convert to Agno format
        agno_messages = converter.to_agno(dcaf_messages)

        # Call Agno API...

        # Convert response back
        response = converter.from_agno(agno_response, conversation_id)
    """

    def to_agno(self, messages: list[Message]) -> list[AgnoMessage]:
        """
        Convert dcaf Messages to Agno format.

        Args:
            messages: List of dcaf Message objects

        Returns:
            List of AgnoMessage dictionaries
        """
        agno_messages = []

        for message in messages:
            agno_msg = self._convert_message_to_agno(message)
            if agno_msg:
                agno_messages.append(agno_msg)

        return agno_messages

    def from_agno(
        self,
        agno_response: dict[str, Any],
        conversation_id: str,
    ) -> AgentResponse:
        """
        Convert an Agno response to dcaf AgentResponse.

        Args:
            agno_response: Response from Agno API
            conversation_id: ID of the conversation

        Returns:
            AgentResponse DTO
        """
        text_parts = []
        tool_calls = []

        # Extract content from response
        content = agno_response.get("content", [])
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append(self._convert_tool_use_block(block))

        text = " ".join(text_parts) if text_parts else None

        # Build DataDTO with tool calls
        from ....application.dto.responses import DataDTO

        data = DataDTO(tool_calls=tool_calls)

        return AgentResponse(
            conversation_id=conversation_id,
            text=text,
            data=data,
            has_pending_approvals=any(tc.status == "pending" for tc in tool_calls),
            is_complete=len(tool_calls) == 0 or all(tc.status != "pending" for tc in tool_calls),
        )

    def stream_event_from_agno(
        self,
        agno_event: dict[str, Any],
    ) -> StreamEvent | None:
        """
        Convert an Agno streaming event to dcaf StreamEvent.

        Args:
            agno_event: Streaming event from Agno

        Returns:
            StreamEvent or None if event should be skipped
        """
        event_type = agno_event.get("type", "")

        if event_type == "content_block_start":
            content_block = agno_event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                return StreamEvent.tool_use_start(
                    tool_call_id=content_block.get("id", ""),
                    tool_name=content_block.get("name", ""),
                    index=agno_event.get("index", 0),
                )
            return None

        elif event_type == "content_block_delta":
            delta = agno_event.get("delta", {})
            delta_type = delta.get("type", "")
            index = agno_event.get("index", 0)

            if delta_type == "text_delta":
                return StreamEvent.text_delta(
                    text=delta.get("text", ""),
                    index=index,
                )
            elif delta_type == "input_json_delta":
                return StreamEvent.tool_use_delta(
                    tool_call_id="",  # Agno doesn't include ID in delta
                    input_delta=delta.get("partial_json", ""),
                    index=index,
                )
            return None

        elif event_type == "content_block_stop":
            return StreamEvent(
                event_type=StreamEventType.TOOL_USE_END,
                index=agno_event.get("index", 0),
            )

        elif event_type == "message_start":
            return StreamEvent.message_start()

        elif event_type == "message_stop":
            # Message end is handled separately with full response
            return None

        elif event_type == "error":
            return StreamEvent.error(
                message=agno_event.get("error", {}).get("message", "Unknown error"),
                code=agno_event.get("error", {}).get("type"),
            )

        return None

    def to_domain_message(self, agno_message: AgnoMessage) -> Message:
        """
        Convert an Agno message to a dcaf Message entity.

        Args:
            agno_message: Message in Agno format

        Returns:
            Message entity
        """
        role = self._convert_role_from_agno(agno_message["role"])
        content = self._convert_content_from_agno(agno_message["content"])

        return Message(role=role, content=content)

    # Private conversion methods

    def _convert_message_to_agno(self, message: Message) -> AgnoMessage | None:
        """Convert a single dcaf Message to Agno format."""
        role = self._convert_role_to_agno(message.role)
        content = self._convert_content_to_agno(message.content)

        return {
            "role": role,
            "content": content,
        }

    def _convert_role_to_agno(self, role: MessageRole) -> str:
        """Convert dcaf MessageRole to Agno role string."""
        mapping = {
            MessageRole.USER: "user",
            MessageRole.ASSISTANT: "assistant",
            MessageRole.SYSTEM: "system",
        }
        return mapping.get(role, "user")

    def _convert_role_from_agno(self, role: str) -> MessageRole:
        """Convert Agno role string to dcaf MessageRole."""
        mapping = {
            "user": MessageRole.USER,
            "assistant": MessageRole.ASSISTANT,
            "system": MessageRole.SYSTEM,
        }
        return mapping.get(role, MessageRole.USER)

    def _convert_content_to_agno(
        self,
        content: MessageContent,
    ) -> list[AgnoContentBlock] | str:
        """Convert dcaf MessageContent to Agno content format."""
        blocks: list[AgnoContentBlock] = []

        for block in content.blocks:
            if block.content_type == ContentType.TEXT and block.text:
                blocks.append(
                    {
                        "type": "text",
                        "text": block.text,
                    }
                )
            elif block.content_type == ContentType.TOOL_USE:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.tool_use_id or "",
                        "name": block.tool_name or "",
                        "input": block.get_tool_input_dict(),
                    }
                )
            elif block.content_type == ContentType.TOOL_RESULT:
                blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.tool_use_id or "",
                        "content": block.tool_result or "",
                    }
                )

        # If only one text block, return as string
        if len(blocks) == 1 and blocks[0].get("type") == "text":
            return str(blocks[0].get("text", ""))

        return blocks

    def _convert_content_from_agno(
        self,
        content: list[AgnoContentBlock] | str,
    ) -> MessageContent:
        """Convert Agno content to dcaf MessageContent."""
        if isinstance(content, str):
            return MessageContent.from_text(content)

        blocks = []
        for agno_block in content:
            block_type = agno_block.get("type", "")

            if block_type == "text":
                blocks.append(ContentBlock.text_block(str(agno_block.get("text", ""))))
            elif block_type == "tool_use":
                tool_input_raw = agno_block.get("input", {})
                tool_input = tool_input_raw if isinstance(tool_input_raw, dict) else {}
                blocks.append(
                    ContentBlock.tool_use_block(
                        tool_use_id=str(agno_block.get("id", "")),
                        tool_name=str(agno_block.get("name", "")),
                        tool_input=tool_input,
                    )
                )
            elif block_type == "tool_result":
                blocks.append(
                    ContentBlock.tool_result_block(
                        tool_use_id=str(agno_block.get("tool_use_id", "")),
                        result=str(agno_block.get("content", "")),
                    )
                )

        if not blocks:
            # Default to empty text
            return MessageContent.from_text("")

        return MessageContent.from_blocks(blocks)

    def _convert_tool_use_block(self, block: dict[str, Any]) -> ToolCallDTO:
        """Convert an Agno tool_use block to ToolCallDTO."""
        return ToolCallDTO(
            id=block.get("id", ""),
            name=block.get("name", ""),
            input=block.get("input", {}),
            requires_approval=True,  # Default, will be updated by use case
            status="pending",
        )
