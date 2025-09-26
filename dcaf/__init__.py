"""
DAB (DuploCloud Agent Builder) - A framework for building AI agents with tool calling capabilities.
"""

from dcaf.agent_server import create_chat_app, AgentProtocol
from dcaf.llm import BedrockLLM
from dcaf.agents.tool_calling_cmd_agent import ToolCallingCmdAgent
from dcaf.schemas.messages import *
from dcaf.channel_routing import SlackResponseRouter

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
