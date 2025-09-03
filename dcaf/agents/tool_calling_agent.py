"""
Tool-calling agent implementation using the new tool system.
"""
from typing import Dict, Any, List, Optional, Union
import logging
import asyncio
from ..tools import Tool, tool
from ..schemas.messages import AgentMessage, ToolCall, ExecutedToolCall, Command
from ..llm import BedrockLLM

logger = logging.getLogger(__name__)


class ToolCallingAgent:
    """
    Agent that can call tools and suggest terminal commands.
    """
    
    def __init__(
        self,
        llm: BedrockLLM,
        tools: List[Tool],
        system_prompt: str = "You are a helpful assistant.",
        model_id: str = "us.anthropic.claude-3-5-sonnet-20240620-v1:0",
        max_iterations: int = 5,
        enable_terminal_cmds: bool = True
    ):
        """
        Initialize the agent.
        
        Args:
            llm: BedrockLLM instance for making LLM calls
            tools: List of Tool objects to make available to the agent
            system_prompt: System prompt for the LLM
            model_id: Model ID to use
            max_iterations: Maximum number of LLM iterations
            enable_terminal_cmds: Whether to enable terminal command suggestions
        """
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        self.system_prompt = system_prompt
        self.model_id = model_id
        self.max_iterations = max_iterations
        self.enable_terminal_cmds = enable_terminal_cmds
        
        # Build tool schemas for LLM
        self.tool_schemas = self._build_tool_schemas()
        
    def _build_tool_schemas(self) -> List[Dict[str, Any]]:
        """Build tool schemas for the LLM, including the final response tool."""
        schemas = []
        
        # Add user-defined tools
        for tool in self.tools.values():
            schemas.append(tool.get_schema())
        
        # Add the final response tool
        final_response_schema = {
            "name": "return_final_response_to_user",
            "description": "Use this tool to return the final response that will be shown to the user once you are ready",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The main response text to display to the user"
                    }
                },
                "required": ["content"]
            }
        }
        
        # Add terminal commands field if enabled
        if self.enable_terminal_cmds:
            final_response_schema["input_schema"]["properties"]["terminal_commands"] = {
                "type": "array",
                "description": "Terminal commands that will be displayed to the user for approval",
                "items": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The complete terminal command string to be executed"
                        },
                        "explanation": {
                            "type": "string",
                            "description": "A brief explanation of what this command does"
                        },
                        "files": {
                            "type": "array",
                            "description": "Optional. All files that must be created before running this command",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "file_path": {"type": "string", "description": "Path relative to CWD"},
                                    "file_content": {"type": "string", "description": "Full content of the file"}
                                },
                                "required": ["file_path", "file_content"]
                            }
                        }
                    },
                    "required": ["command"]
                }
            }
        
        schemas.append(final_response_schema)
        return schemas
    
    async def execute_tool(
        self, 
        tool_name: str, 
        tool_input: Dict[str, Any],
        platform_context: Dict[str, Any]
    ) -> str:
        """Execute a tool and return the result."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found"
        
        logger.info(f"Executing tool '{tool_name}' with input: {tool_input}")
        
        try:
            tool = self.tools[tool_name]
            result = await tool.execute(tool_input, platform_context)
            logger.info(f"Tool '{tool_name}' output: {result}")
            return result
        except Exception as e:
            error_msg = f"Error executing tool '{tool_name}': {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    def create_tool_call_for_approval(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_use_id: str
    ) -> ToolCall:
        """Create a ToolCall object for user approval."""
        tool = self.tools[tool_name]
        
        # Extract input descriptions from schema
        input_description = {}
        if "properties" in tool.schema:
            for prop_name, prop_info in tool.schema["properties"].items():
                input_description[prop_name] = {
                    "type": prop_info.get("type", "string"),
                    "description": prop_info.get("description", f"Parameter {prop_name}")
                }
        
        return ToolCall(
            id=tool_use_id,
            name=tool_name,
            input=tool_input,
            tool_description=tool.description,
            input_description=input_description
        )
    
    async def process_approved_tool_calls(
        self,
        messages: Dict[str, List[Dict[str, Any]]],
        platform_context: Dict[str, Any]
    ) -> List[ExecutedToolCall]:
        """Process approved tool calls from incoming messages."""
        executed_tools = []
        
        # Look for approved tool calls in the latest message
        messages_list = messages.get("messages", [])
        if messages_list:
            latest_message = messages_list[-1]
            data = latest_message.get("data", {})
            tool_calls = data.get("tool_calls", [])
            
            for tool_call in tool_calls:
                if tool_call.get("execute", False):
                    # Execute the approved tool
                    result = await self.execute_tool(
                        tool_call["name"],
                        tool_call["input"],
                        platform_context
                    )
                    
                    executed_tools.append(ExecutedToolCall(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        input=tool_call["input"],
                        output=result
                    ))
                elif tool_call.get("rejection_reason"):
                    # Handle rejected tool
                    executed_tools.append(ExecutedToolCall(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        input=tool_call["input"],
                        output=f"Tool execution rejected: {tool_call['rejection_reason']}"
                    ))
        
        return executed_tools
    
    async def process_tool_calls(
        self,
        response_content: List[Dict[str, Any]],
        platform_context: Dict[str, Any]
    ) -> tuple[List[ExecutedToolCall], List[ToolCall]]:
        """Process tool calls from LLM response."""
        executed_tool_calls = []
        approval_required_tools = []
        
        for content_block in response_content:
            if content_block.get("type") == "tool_use":
                tool_name = content_block.get("name")
                tool_input = content_block.get("input", {})
                tool_use_id = content_block.get("id")
                
                if tool_name in self.tools:
                    tool = self.tools[tool_name]
                    
                    if tool.requires_approval:
                        # Tool requires approval
                        tool_call = self.create_tool_call_for_approval(
                            tool_name, tool_input, tool_use_id
                        )
                        approval_required_tools.append(tool_call)
                    else:
                        # Execute immediately
                        result = await self.execute_tool(
                            tool_name, tool_input, platform_context
                        )
                        executed_tool_calls.append(ExecutedToolCall(
                            id=tool_use_id,
                            name=tool_name,
                            input=tool_input,
                            output=result
                        ))
        
        return executed_tool_calls, approval_required_tools
    
    def preprocess_messages(
        self,
        messages: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Convert input messages to LLM format."""
        preprocessed = []
        messages_list = messages.get("messages", [])
        
        for message in messages_list:
            if message.get("role") in ["user", "assistant"]:
                preprocessed.append({
                    "role": message["role"],
                    "content": message.get("content", "")
                })
        
        return preprocessed
    
    async def invoke(
        self,
        messages: Dict[str, List[Dict[str, Any]]],
        platform_context: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        """
        Main agent invocation.
        
        Args:
            messages: Conversation messages
            platform_context: Runtime context to pass to tools
            
        Returns:
            AgentMessage with response and any tool calls needing approval
        """
        if platform_context is None:
            platform_context = {}
        
        # Process any approved tool calls from incoming message
        executed_tool_calls = await self.process_approved_tool_calls(
            messages, platform_context
        )
        
        # Build conversation with executed tool results
        conversation = self.preprocess_messages(messages)
        if executed_tool_calls:
            for executed_tool in executed_tool_calls:
                result_msg = (
                    f"Tool result for {executed_tool.name} "
                    f"with inputs {executed_tool.input}: {executed_tool.output}"
                )
                conversation.append({"role": "user", "content": result_msg})
        
        # Main execution loop
        for iteration in range(self.max_iterations):
            logger.info(f"Iteration {iteration + 1}")
            
            # Call LLM
            response = self.llm.invoke(
                messages=conversation,
                model_id=self.model_id,
                max_tokens=4000,
                system_prompt=self.system_prompt,
                tools=self.tool_schemas,
                tool_choice={"type": "any"},
                return_raw_api_response=True
            )
            
            response_content = response.get("content", [])
            
            # Check for final response
            final_response_call = None
            other_tool_calls = []
            
            for content_block in response_content:
                if (content_block.get("type") == "tool_use" and
                    content_block.get("name") == "return_final_response_to_user"):
                    final_response_call = content_block
                elif content_block.get("type") == "tool_use":
                    other_tool_calls.append(content_block)
            
            # Return final response if found
            if final_response_call:
                final_input = final_response_call.get("input", {})
                agent_message = AgentMessage(
                    content=final_input.get("content", "")
                )
                
                # Add terminal commands if present and enabled
                if self.enable_terminal_cmds and final_input.get("terminal_commands"):
                    for cmd in final_input["terminal_commands"]:
                        agent_message.data.cmds.append(Command(
                            command=cmd.get("command"),
                            execute=False
                        ))
                
                return agent_message
            
            # Process other tool calls
            if other_tool_calls:
                conversation.append({
                    "role": "assistant",
                    "content": "Processing tool calls"
                })
                
                # Process tools
                executed, approval_needed = await self.process_tool_calls(
                    response_content, platform_context
                )
                
                # Return approval-needed tools
                if approval_needed:
                    agent_message = AgentMessage(
                        content="I need your approval to execute the following tools:"
                    )
                    for tool_call in approval_needed:
                        agent_message.data.tool_calls.append(tool_call)
                    return agent_message
                
                # Add executed tool results
                if executed:
                    for executed_tool in executed:
                        result_msg = (
                            f"Tool result for {executed_tool.name} "
                            f"with input {executed_tool.input}: {executed_tool.output}"
                        )
                        conversation.append({"role": "user", "content": result_msg})
        
        # Max iterations reached
        return AgentMessage(
            content="Maximum iterations reached. Please try rephrasing your request."
        )