"""Agno-specific type definitions and constants."""

from enum import Enum
from typing import Any, TypedDict


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
    input: dict[str, Any]


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
    content: list[AgnoContentBlock] | str


class AgnoToolDefinition(TypedDict):
    """Tool definition in Agno format."""

    name: str
    description: str
    input_schema: dict[str, Any]


class AgnoStreamEvent(TypedDict, total=False):
    """Streaming event from Agno."""

    type: str
    index: int
    delta: dict[str, Any]
    content_block: dict[str, Any]


# Default configuration values
DEFAULT_MODEL_ID = "anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_PROVIDER = "bedrock"
DEFAULT_FRAMEWORK = "agno"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOOL_CALL_LIMIT = 1
DEFAULT_AWS_REGION = "us-west-2"

# Supported providers
SUPPORTED_PROVIDERS = ["bedrock", "anthropic", "openai", "google", "azure", "ollama"]
