"""Agno-specific type definitions and constants."""

from typing import TypedDict, Optional, List, Any, Dict
from enum import Enum


class AgnoRole(Enum):
    """Message roles in Agno format."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AgnoContentType(Enum):
    """Content block types in Agno format."""
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class AgnoTextBlock(TypedDict):
    """Text content block in Agno format."""
    type: str  # "text"
    text: str


class AgnoToolUseBlock(TypedDict):
    """Tool use content block in Agno format."""
    type: str  # "tool_use"
    id: str
    name: str
    input: Dict[str, Any]


class AgnoToolResultBlock(TypedDict):
    """Tool result content block in Agno format."""
    type: str  # "tool_result"
    tool_use_id: str
    content: str


# Union type for content blocks
AgnoContentBlock = AgnoTextBlock | AgnoToolUseBlock | AgnoToolResultBlock


class AgnoMessage(TypedDict):
    """Message in Agno format."""
    role: str
    content: List[AgnoContentBlock] | str


class AgnoToolDefinition(TypedDict):
    """Tool definition in Agno format."""
    name: str
    description: str
    input_schema: Dict[str, Any]


class AgnoStreamEvent(TypedDict, total=False):
    """Streaming event from Agno."""
    type: str
    index: int
    delta: Dict[str, Any]
    content_block: Dict[str, Any]


# Default configuration values
DEFAULT_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
DEFAULT_PROVIDER = "bedrock"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7

# Supported providers
SUPPORTED_PROVIDERS = ["bedrock", "anthropic", "openai"]
