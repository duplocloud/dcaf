"""
DAB (DuploCloud Agent Builder) - A framework for building AI agents with tool calling capabilities.
"""

from importlib.metadata import version

from .agent_server import AgentProtocol, create_chat_app
from .agents.tool_calling_cmd_agent import ToolCallingCmdAgent
from .channel_routing import SlackResponseRouter
from .llm import BedrockLLM
from .schemas.messages import AgentMessage, ExecutedToolCall, Messages

__version__ = version("dcaf")
__all__ = [
    "create_chat_app",
    "AgentProtocol",
    "BedrockLLM",
    "ToolCallingCmdAgent",
    "AgentMessage",
    "Messages",
    "ExecutedToolCall",
    "SlackResponseRouter",
]
