"""
Testing Infrastructure - Test Support Utilities.

This module provides utilities for testing DCAF Core components:
    - Fakes: Fake implementations of ports for testing
    - Builders: Test data builders for creating domain objects
    - Fixtures: pytest fixtures for common test setup
"""

from .builders import (
    ConversationBuilder,
    MessageBuilder,
    ToolBuilder,
    ToolCallBuilder,
)
from .fakes import (
    FakeAgentRuntime,
    FakeApprovalCallback,
    FakeConversationRepository,
    FakeEventPublisher,
)

__all__ = [
    # Fakes
    "FakeAgentRuntime",
    "FakeConversationRepository",
    "FakeApprovalCallback",
    "FakeEventPublisher",
    # Builders
    "MessageBuilder",
    "ToolCallBuilder",
    "ConversationBuilder",
    "ToolBuilder",
]
