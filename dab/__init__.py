"""
DAB (DuploCloud Agent Builder) - A framework for building AI agents with tool calling capabilities.
"""

from .agent_server import create_chat_app, AgentProtocol
from .services.llm import BedrockAnthropicLLM
from .agents.tool_calling_cmd_agent import ToolCallingCmdAgent
from .schemas.messages import *

__version__ = "0.1.0"
__all__ = [
    "create_chat_app",
    "AgentProtocol", 
    "BedrockAnthropicLLM",
    "ToolCallingCmdAgent",
    "AgentMessage",
    "Messages",
    "ExecutedToolCall",
]
