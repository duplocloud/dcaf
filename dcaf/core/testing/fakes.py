"""Fake implementations of ports for testing."""

from typing import List, Optional, Iterator, Dict, Any, Callable
from dataclasses import dataclass, field

from ..domain.entities import Message, Conversation, ToolCall
from ..domain.value_objects import ConversationId
from ..domain.events import DomainEvent
from ..application.dto.responses import AgentResponse, ToolCallDTO, StreamEvent
from ..application.ports.approval_callback import ApprovalDecision, ApprovalAction


class FakeAgentRuntime:
    """
    Fake implementation of AgentRuntime for testing.
    
    Allows configuring canned responses and tracking invocations.
    
    Example:
        fake = FakeAgentRuntime()
        fake.will_respond_with_text("Hello, world!")
        
        response = fake.invoke(messages, tools)
        assert response.text == "Hello, world!"
        assert fake.invoke_count == 1
    """
    
    def __init__(self) -> None:
        self._responses: List[AgentResponse] = []
        self._stream_events: List[List[StreamEvent]] = []
        self._invoke_calls: List[Dict[str, Any]] = []
        self._invoke_stream_calls: List[Dict[str, Any]] = []
        self._default_conversation_id = "test-conversation-123"
    
    @property
    def invoke_count(self) -> int:
        """Get the number of times invoke was called."""
        return len(self._invoke_calls)
    
    @property
    def invoke_stream_count(self) -> int:
        """Get the number of times invoke_stream was called."""
        return len(self._invoke_stream_calls)
    
    @property
    def last_invoke_call(self) -> Optional[Dict[str, Any]]:
        """Get the last invoke call arguments."""
        return self._invoke_calls[-1] if self._invoke_calls else None
    
    @property
    def last_messages(self) -> Optional[List[Message]]:
        """Get the messages from the last invoke call."""
        if self._invoke_calls:
            return self._invoke_calls[-1].get("messages")
        return None
    
    @property
    def last_tools(self) -> Optional[List]:
        """Get the tools from the last invoke call."""
        if self._invoke_calls:
            return self._invoke_calls[-1].get("tools")
        return None
    
    def will_respond_with_text(self, text: str) -> "FakeAgentRuntime":
        """Configure the next response to return text."""
        self._responses.append(AgentResponse.text_only(
            self._default_conversation_id, 
            text,
        ))
        return self
    
    def will_respond_with_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_call_id: Optional[str] = None,
        requires_approval: bool = True,
    ) -> "FakeAgentRuntime":
        """Configure the next response to return a tool call."""
        tool_call = ToolCallDTO(
            id=tool_call_id or f"tc-{len(self._responses)}",
            name=tool_name,
            input=tool_input,
            requires_approval=requires_approval,
            status="pending" if requires_approval else "approved",
        )
        self._responses.append(AgentResponse.with_tool_calls(
            self._default_conversation_id,
            [tool_call],
        ))
        return self
    
    def will_respond_with(self, response: AgentResponse) -> "FakeAgentRuntime":
        """Configure the next response with a custom AgentResponse."""
        self._responses.append(response)
        return self
    
    def will_stream_text(self, text: str) -> "FakeAgentRuntime":
        """Configure the next stream response with text."""
        events = [
            StreamEvent.message_start(),
        ]
        for char in text:
            events.append(StreamEvent.text_delta(char))
        events.append(StreamEvent.message_end(AgentResponse.text_only(
            self._default_conversation_id,
            text,
        )))
        self._stream_events.append(events)
        return self
    
    def invoke(
        self,
        messages: List[Message],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> AgentResponse:
        """Fake invoke that returns configured responses."""
        self._invoke_calls.append({
            "messages": messages,
            "tools": tools,
            "system_prompt": system_prompt,
        })
        
        if self._responses:
            return self._responses.pop(0)
        
        # Default response
        return AgentResponse.text_only(
            self._default_conversation_id,
            "Default fake response",
        )
    
    def invoke_stream(
        self,
        messages: List[Message],
        tools: List[Any],
        system_prompt: Optional[str] = None,
    ) -> Iterator[StreamEvent]:
        """Fake invoke_stream that returns configured events."""
        self._invoke_stream_calls.append({
            "messages": messages,
            "tools": tools,
            "system_prompt": system_prompt,
        })
        
        if self._stream_events:
            yield from self._stream_events.pop(0)
        else:
            # Default stream
            yield StreamEvent.message_start()
            yield StreamEvent.text_delta("Default ")
            yield StreamEvent.text_delta("stream ")
            yield StreamEvent.text_delta("response")
            yield StreamEvent.message_end(AgentResponse.text_only(
                self._default_conversation_id,
                "Default stream response",
            ))
    
    def reset(self) -> None:
        """Reset all configured responses and recorded calls."""
        self._responses.clear()
        self._stream_events.clear()
        self._invoke_calls.clear()
        self._invoke_stream_calls.clear()


class FakeConversationRepository:
    """
    Fake implementation of ConversationRepository for testing.
    
    Example:
        fake = FakeConversationRepository()
        conversation = Conversation.create()
        fake.save(conversation)
        
        loaded = fake.get(conversation.id)
        assert loaded == conversation
    """
    
    def __init__(self) -> None:
        self._store: Dict[str, Conversation] = {}
        self._save_calls: List[Conversation] = []
        self._get_calls: List[ConversationId] = []
    
    @property
    def save_count(self) -> int:
        return len(self._save_calls)
    
    @property
    def get_count(self) -> int:
        return len(self._get_calls)
    
    @property
    def last_saved(self) -> Optional[Conversation]:
        return self._save_calls[-1] if self._save_calls else None
    
    def get(self, id: ConversationId) -> Optional[Conversation]:
        self._get_calls.append(id)
        return self._store.get(str(id))
    
    def save(self, conversation: Conversation) -> None:
        self._save_calls.append(conversation)
        self._store[str(conversation.id)] = conversation
    
    def delete(self, id: ConversationId) -> bool:
        if str(id) in self._store:
            del self._store[str(id)]
            return True
        return False
    
    def exists(self, id: ConversationId) -> bool:
        return str(id) in self._store
    
    def get_or_create(self, id: ConversationId) -> Conversation:
        existing = self._store.get(str(id))
        if existing:
            return existing
        conversation = Conversation(id=id)
        self._store[str(id)] = conversation
        return conversation
    
    def seed(self, conversation: Conversation) -> None:
        """Seed the repository with a conversation (without recording)."""
        self._store[str(conversation.id)] = conversation
    
    def reset(self) -> None:
        """Reset the repository."""
        self._store.clear()
        self._save_calls.clear()
        self._get_calls.clear()


class FakeApprovalCallback:
    """
    Fake implementation of ApprovalCallback for testing.
    
    Example:
        fake = FakeApprovalCallback()
        fake.will_approve_all()
        
        decisions = fake.request_approval(tool_calls)
        assert all(d.is_approved for d in decisions)
    """
    
    def __init__(self) -> None:
        self._decisions: List[List[ApprovalDecision]] = []
        self._request_calls: List[List[ToolCall]] = []
        self._notifications: List[Dict[str, Any]] = []
        self._auto_approve = False
        self._auto_reject = False
        self._auto_reject_reason = "Auto-rejected by fake"
    
    @property
    def request_count(self) -> int:
        return len(self._request_calls)
    
    @property
    def last_tool_calls(self) -> Optional[List[ToolCall]]:
        return self._request_calls[-1] if self._request_calls else None
    
    @property
    def notification_count(self) -> int:
        return len(self._notifications)
    
    def will_approve_all(self) -> "FakeApprovalCallback":
        """Configure to automatically approve all tool calls."""
        self._auto_approve = True
        self._auto_reject = False
        return self
    
    def will_reject_all(self, reason: str = "Rejected by test") -> "FakeApprovalCallback":
        """Configure to automatically reject all tool calls."""
        self._auto_reject = True
        self._auto_reject_reason = reason
        self._auto_approve = False
        return self
    
    def will_return_decisions(
        self, 
        decisions: List[ApprovalDecision],
    ) -> "FakeApprovalCallback":
        """Configure specific decisions to return."""
        self._decisions.append(decisions)
        return self
    
    def request_approval(
        self,
        tool_calls: List[ToolCall],
    ) -> List[ApprovalDecision]:
        self._request_calls.append(tool_calls)
        
        if self._decisions:
            return self._decisions.pop(0)
        
        if self._auto_approve:
            return [
                ApprovalDecision.approve(str(tc.id))
                for tc in tool_calls
            ]
        
        if self._auto_reject:
            return [
                ApprovalDecision.reject(str(tc.id), self._auto_reject_reason)
                for tc in tool_calls
            ]
        
        # Default: approve all
        return [
            ApprovalDecision.approve(str(tc.id))
            for tc in tool_calls
        ]
    
    def notify_execution_result(
        self,
        tool_call_id: str,
        result: str,
        success: bool,
    ) -> None:
        self._notifications.append({
            "tool_call_id": tool_call_id,
            "result": result,
            "success": success,
        })
    
    def reset(self) -> None:
        self._decisions.clear()
        self._request_calls.clear()
        self._notifications.clear()
        self._auto_approve = False
        self._auto_reject = False


class FakeEventPublisher:
    """
    Fake implementation of EventPublisher for testing.
    
    Example:
        fake = FakeEventPublisher()
        
        fake.publish(SomeEvent())
        
        assert fake.publish_count == 1
        assert fake.events[0].event_type == "SomeEvent"
    """
    
    def __init__(self) -> None:
        self._events: List[DomainEvent] = []
    
    @property
    def events(self) -> List[DomainEvent]:
        return list(self._events)
    
    @property
    def publish_count(self) -> int:
        return len(self._events)
    
    def publish(self, event: DomainEvent) -> None:
        self._events.append(event)
    
    def publish_all(self, events: List[DomainEvent]) -> None:
        self._events.extend(events)
    
    def get_events_of_type(self, event_type: type) -> List[DomainEvent]:
        """Get all events of a specific type."""
        return [e for e in self._events if isinstance(e, event_type)]
    
    def has_event_of_type(self, event_type: type) -> bool:
        """Check if an event of the given type was published."""
        return any(isinstance(e, event_type) for e in self._events)
    
    def reset(self) -> None:
        self._events.clear()
