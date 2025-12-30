"""
Testing Infrastructure - Test Support Utilities.

This module provides utilities for testing DCAF Core components:
    - Fakes: Fake implementations of ports for testing
    - Builders: Test data builders for creating domain objects
    - Fixtures: pytest fixtures for common test setup
"""

from .fakes import (
    FakeAgentRuntime,
    FakeConversationRepository,
    FakeApprovalCallback,
    FakeEventPublisher,
)
from .builders import (
    MessageBuilder,
    ToolCallBuilder,
    ConversationBuilder,
    ToolBuilder,
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
