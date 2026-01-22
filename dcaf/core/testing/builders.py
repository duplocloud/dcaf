"""Test data builders for creating domain objects."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..domain.entities import (
    Conversation,
    Message,
    MessageRole,
    ToolCall,
    ToolCallStatus,
)
from ..domain.value_objects import (
    ConversationId,
    MessageContent,
    PlatformContext,
    ToolCallId,
    ToolInput,
)


class MessageBuilder:
    """
    Builder for creating Message entities in tests.

    Example:
        message = (MessageBuilder()
            .with_role(MessageRole.USER)
            .with_text("Hello, world!")
            .build())
    """

    def __init__(self) -> None:
        self._role = MessageRole.USER
        self._text: str | None = "Test message"
        self._content: MessageContent | None = None
        self._created_at: datetime | None = None

    def with_role(self, role: MessageRole) -> "MessageBuilder":
        self._role = role
        return self

    def with_text(self, text: str) -> "MessageBuilder":
        self._text = text
        return self

    def with_content(self, content: MessageContent) -> "MessageBuilder":
        self._content = content
        return self

    def with_created_at(self, created_at: datetime) -> "MessageBuilder":
        self._created_at = created_at
        return self

    def as_user(self) -> "MessageBuilder":
        self._role = MessageRole.USER
        return self

    def as_assistant(self) -> "MessageBuilder":
        self._role = MessageRole.ASSISTANT
        return self

    def as_system(self) -> "MessageBuilder":
        self._role = MessageRole.SYSTEM
        return self

    def build(self) -> Message:
        content = self._content or MessageContent.from_text(self._text or "")
        return Message(
            role=self._role,
            content=content,
            created_at=self._created_at,
        )

    @classmethod
    def user_message(cls, text: str = "User test message") -> Message:
        """Convenience method for creating a user message."""
        return cls().as_user().with_text(text).build()

    @classmethod
    def assistant_message(cls, text: str = "Assistant test message") -> Message:
        """Convenience method for creating an assistant message."""
        return cls().as_assistant().with_text(text).build()

    @classmethod
    def system_message(cls, text: str = "System test message") -> Message:
        """Convenience method for creating a system message."""
        return cls().as_system().with_text(text).build()


class ToolCallBuilder:
    """
    Builder for creating ToolCall entities in tests.

    Example:
        tool_call = (ToolCallBuilder()
            .with_name("kubectl")
            .with_input({"command": "get pods"})
            .requiring_approval()
            .build())
    """

    def __init__(self) -> None:
        self._id: ToolCallId | None = None
        self._tool_name = "test_tool"
        self._input: dict[str, Any] = {}
        self._description = "Test tool"
        self._intent: str | None = None
        self._requires_approval = True
        self._status: ToolCallStatus | None = None
        self._result: str | None = None

    def with_id(self, id: str) -> "ToolCallBuilder":
        self._id = ToolCallId(id)
        return self

    def with_name(self, name: str) -> "ToolCallBuilder":
        self._tool_name = name
        return self

    def with_input(self, input_data: dict[str, Any]) -> "ToolCallBuilder":
        self._input = input_data
        return self

    def with_description(self, description: str) -> "ToolCallBuilder":
        self._description = description
        return self

    def with_intent(self, intent: str) -> "ToolCallBuilder":
        self._intent = intent
        return self

    def requiring_approval(self) -> "ToolCallBuilder":
        self._requires_approval = True
        return self

    def not_requiring_approval(self) -> "ToolCallBuilder":
        self._requires_approval = False
        return self

    def as_approved(self) -> "ToolCallBuilder":
        self._status = ToolCallStatus.APPROVED
        return self

    def as_rejected(self) -> "ToolCallBuilder":
        self._status = ToolCallStatus.REJECTED
        return self

    def as_completed(self, result: str = "Success") -> "ToolCallBuilder":
        self._status = ToolCallStatus.COMPLETED
        self._result = result
        return self

    def build(self) -> ToolCall:
        tool_call = ToolCall(
            id=self._id or ToolCallId.generate(),
            tool_name=self._tool_name,
            input=ToolInput(self._input),
            description=self._description,
            intent=self._intent,
            requires_approval=self._requires_approval,
        )

        # Apply status transitions if needed
        if self._status == ToolCallStatus.APPROVED:
            tool_call.approve()
        elif self._status == ToolCallStatus.REJECTED:
            tool_call.reject("Test rejection")
        elif self._status == ToolCallStatus.COMPLETED:
            tool_call.approve()
            tool_call.start_execution()
            tool_call.complete(self._result or "Success")

        return tool_call

    @classmethod
    def pending_kubectl_call(cls) -> ToolCall:
        """Create a pending kubectl tool call."""
        return (
            cls()
            .with_name("kubectl")
            .with_input({"command": "get pods"})
            .with_description("Execute kubectl commands")
            .requiring_approval()
            .build()
        )


class ConversationBuilder:
    """
    Builder for creating Conversation aggregates in tests.

    Example:
        conversation = (ConversationBuilder()
            .with_system_prompt("You are a helpful assistant")
            .with_user_message("Hello")
            .with_assistant_message("Hi there!")
            .build())
    """

    def __init__(self) -> None:
        self._id: ConversationId | None = None
        self._messages: list[Message] = []
        self._context: PlatformContext | None = None
        self._pending_tool_calls: list[ToolCall] = []

    def with_id(self, id: str) -> "ConversationBuilder":
        self._id = ConversationId(id)
        return self

    def with_context(self, context: PlatformContext) -> "ConversationBuilder":
        self._context = context
        return self

    def with_tenant(self, tenant_name: str) -> "ConversationBuilder":
        self._context = PlatformContext(tenant_name=tenant_name)
        return self

    def with_message(self, message: Message) -> "ConversationBuilder":
        self._messages.append(message)
        return self

    def with_messages(self, messages: list[Message]) -> "ConversationBuilder":
        self._messages.extend(messages)
        return self

    def with_user_message(self, text: str) -> "ConversationBuilder":
        self._messages.append(MessageBuilder.user_message(text))
        return self

    def with_assistant_message(self, text: str) -> "ConversationBuilder":
        self._messages.append(MessageBuilder.assistant_message(text))
        return self

    def with_system_prompt(self, text: str) -> "ConversationBuilder":
        self._messages.insert(0, MessageBuilder.system_message(text))
        return self

    def with_pending_tool_call(self, tool_call: ToolCall) -> "ConversationBuilder":
        self._pending_tool_calls.append(tool_call)
        return self

    def build(self) -> Conversation:
        conversation = Conversation(
            id=self._id or ConversationId.generate(),
            messages=self._messages,
            context=self._context,
        )

        # Add pending tool calls
        if self._pending_tool_calls:
            conversation.request_tool_approval(self._pending_tool_calls)

        return conversation

    @classmethod
    def empty(cls) -> Conversation:
        """Create an empty conversation."""
        return cls().build()

    @classmethod
    def with_single_turn(
        cls,
        user_text: str = "Hello",
        assistant_text: str = "Hi there!",
    ) -> Conversation:
        """Create a conversation with one complete turn."""
        return cls().with_user_message(user_text).with_assistant_message(assistant_text).build()


class ToolBuilder:
    """
    Builder for creating Tool objects in tests.

    Note: This creates a mock tool-like object for testing.
    For real tools, use the dcaf.tools.Tool class.

    Example:
        tool = (ToolBuilder()
            .with_name("kubectl")
            .with_description("Execute kubectl commands")
            .requiring_approval()
            .build())
    """

    def __init__(self) -> None:
        self._name = "test_tool"
        self._description = "A test tool"
        self._schema: dict[str, Any] = {
            "name": "test_tool",
            "description": "A test tool",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        }
        self._requires_approval = False
        self._requires_platform_context = False
        self._func: Callable = lambda **_kwargs: "Tool executed"

    def with_name(self, name: str) -> "ToolBuilder":
        self._name = name
        self._schema["name"] = name
        return self

    def with_description(self, description: str) -> "ToolBuilder":
        self._description = description
        self._schema["description"] = description
        return self

    def with_schema(self, schema: dict[str, Any]) -> "ToolBuilder":
        self._schema = schema
        return self

    def with_input_schema(self, input_schema: dict[str, Any]) -> "ToolBuilder":
        self._schema["input_schema"] = input_schema
        return self

    def requiring_approval(self) -> "ToolBuilder":
        self._requires_approval = True
        return self

    def not_requiring_approval(self) -> "ToolBuilder":
        self._requires_approval = False
        return self

    def requiring_platform_context(self) -> "ToolBuilder":
        self._requires_platform_context = True
        return self

    def with_func(self, func: Callable) -> "ToolBuilder":
        self._func = func
        return self

    def build(self) -> "MockTool":
        return MockTool(
            name=self._name,
            description=self._description,
            schema=self._schema,
            requires_approval=self._requires_approval,
            requires_platform_context=self._requires_platform_context,
            func=self._func,
        )

    @classmethod
    def kubectl_tool(cls) -> "MockTool":
        """Create a kubectl tool for testing."""
        return (
            cls()
            .with_name("kubectl")
            .with_description("Execute kubectl commands")
            .with_input_schema(
                {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The kubectl command"},
                    },
                    "required": ["command"],
                }
            )
            .requiring_approval()
            .requiring_platform_context()
            .build()
        )


class MockTool:
    """Mock tool for testing purposes."""

    def __init__(
        self,
        name: str,
        description: str,
        schema: dict[str, Any],
        requires_approval: bool = False,
        requires_platform_context: bool = False,
        func: Callable | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self.requires_approval = requires_approval
        self.requires_platform_context = requires_platform_context
        self._func = func or (lambda **_kwargs: "Executed")
        self._execute_calls: list[dict[str, Any]] = []

    def get_schema(self) -> dict[str, Any]:
        return self.schema

    def execute(
        self,
        input_args: dict[str, Any],
        platform_context: dict[str, Any] | None = None,
    ) -> str:
        self._execute_calls.append(
            {
                "input_args": input_args,
                "platform_context": platform_context,
            }
        )
        if self.requires_platform_context:
            return str(self._func(**input_args, platform_context=platform_context))
        return str(self._func(**input_args))

    @property
    def execute_count(self) -> int:
        return len(self._execute_calls)

    @property
    def last_execute_call(self) -> dict[str, Any] | None:
        return self._execute_calls[-1] if self._execute_calls else None
