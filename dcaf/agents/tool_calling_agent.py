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
        max_iterations: int = 10,
        enable_terminal_cmds: bool = False
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
        logger.info(f"Loading Agent Tools: {list(self.tools.keys())}")

        self.system_prompt = system_prompt
        self.model_id = model_id
        self.max_iterations = max_iterations
        self.enable_terminal_cmds = enable_terminal_cmds
        
        # Build tool schemas for LLM
        self.tool_schemas = self._build_tool_schemas()
        logger.info(f"Tool schemas: {"\n\n\n".join(str(schema) for schema in self.tool_schemas)}")
        
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
        
        # schemas.append(final_response_schema)
        return schemas
    
    def execute_tool(
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
            result = tool.execute(tool_input, platform_context)
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
    
    def process_approved_tool_calls(
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
                    result = self.execute_tool(
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
                        output=f"Tool execution rejected; Rejection Reason: {tool_call['rejection_reason']}"
                    ))
        
        return executed_tools
    
    def process_tool_calls(
        self,
        response_content: List[Dict[str, Any]],
        platform_context: Dict[str, Any]
    ) -> tuple[List[ExecutedToolCall], List[ToolCall]]:
        """Process tool calls from LLM response."""
        executed_tool_calls = []
        approval_required_tools = []
        
        logger.info(f"Processing {len(response_content)} content blocks")
        
        for tool_use_block in response_content:
            # Handle the actual format returned by Bedrock: {'toolUse': {...}}
            tool_name = tool_use_block.get("name")
            tool_input = tool_use_block.get("input", {})
            tool_use_id = tool_use_block.get("toolUseId")
            
            logger.info(f"Found tool call: {tool_name} with ID: {tool_use_id}")
                
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
                    result = self.execute_tool(
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
    
    def invoke(
        self,
        messages: Dict[str, List[Dict[str, Any]]],
    ) -> AgentMessage:
        """
        Main agent invocation.
        
        Args:
            messages: Conversation messages
            platform_context: Runtime context to pass to tools
            
        Returns:
            AgentMessage with response and any tool calls needing approval
        """

        #Fetch the platform context for the current turn from the last user message object
        platform_context = {}
        #Iterate through the messages in reverse order to find the last user message
        for message in reversed(messages.get("messages", [])):
            if message.get("role") == "user":
                platform_context = message.get("platform_context", {})
                break
        
        # Process any approved tool calls from incoming message
        executed_tool_calls = self.process_approved_tool_calls(
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
        
        #store and return the executed calls in the agent message response object so that they are stored in the persistent thread
        current_turn_executed_tool_calls = []
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
                # tool_choice="any",
                # tool_choice="required",
                return_raw_api_response=True
            )
            
            response_content = response['output']['message'].get('content', [])
            
            # Check for final response
            final_response_call = None
            other_tool_calls = []
            
            for content_block in response_content:
                if 'toolUse' in content_block:
                    tool_use = content_block['toolUse']
                    other_tool_calls.append(tool_use)    

                elif "text" in content_block:
                    final_response_call = content_block

            logger.info(f"Tool calls found: {other_tool_calls}")

            # Return final response if found
            if final_response_call:
                final_response = final_response_call.get('text', "")
                agent_message = AgentMessage(
                    content=final_response
                )
                
                #return executed_tool_calls in the agent message response object so that they are stored in the persistent thread
                if current_turn_executed_tool_calls:
                    agent_message.data.executed_tool_calls = current_turn_executed_tool_calls

                # Add terminal commands if present
                if self.enable_terminal_cmds and final_input.get("terminal_commands"):
                    for cmd in final_input["terminal_commands"]:
                        agent_message.data.cmds.append(Command(
                            command=cmd.get("command"),
                            execute=False
                        ))
                
                return agent_message
            
            # Process other tool calls
            elif other_tool_calls:
                conversation.append({
                    "role": "assistant",
                    "content": "Processing tool calls"
                })
                
                # Update process_tool_calls to expect toolUse format
                executed, approval_needed = self.process_tool_calls(
                    other_tool_calls, platform_context
                )
                
                # Add executed tool results. This needs to be dealt with properly TODO:
                if executed:
                    for executed_tool in executed:
                        result_msg = (
                            f"Tool result for {executed_tool.name} "
                            f"with input {executed_tool.input}: {executed_tool.output}"
                        )
                        conversation.append({"role": "user", "content": result_msg})

                        current_turn_executed_tool_calls.append(executed_tool)

                # Return approval-needed tools
                if approval_needed:
                    agent_message = AgentMessage(
                        content="I need your approval to execute the following tools:"
                    )
                    for tool_call in approval_needed:
                        agent_message.data.tool_calls.append(tool_call)

                    #return executed_tool_calls in the agent message response object so that they are stored in the persistent thread
                    agent_message.data.executed_tool_calls = current_turn_executed_tool_calls

                    return agent_message

            #Edge case when no tool calls are found and no final message is found
                
        # Max iterations reached
        #TODO explore implementing soft limit for max iterations by telling the LLM to return the final response.
        return AgentMessage(
            content=f"Maximum iterations ({self.max_iterations}) reached. Please try a different request or increase the maximum iterations limit."
        )