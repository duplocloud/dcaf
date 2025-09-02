"""
DAB (DuploCloud Agent Builder) - A framework for building AI agents with tool calling capabilities.
"""

from .agent_server import create_chat_app, AgentProtocol
from .llm import BedrockLLM
from .agents.tool_calling_cmd_agent import ToolCallingCmdAgent
from .schemas.messages import *
from .channel_routing import SlackResponseRouter

__version__ = "0.0.1"
__all__ = [
    "create_chat_app",
    "AgentProtocol", 
    "BedrockLLM",
    "ToolCallingCmdAgent",
    "AgentMessage",
    "Messages",
    "ExecutedToolCall",
    "SlackResponseRouter"
]
