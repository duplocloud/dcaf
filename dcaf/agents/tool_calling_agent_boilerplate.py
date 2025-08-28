from typing import Dict, Any, List, Optional
import sys
import os
import uuid
import functools

# Add parent directory to path to import from root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent_server import AgentProtocol
from schemas.messages import AgentMessage, ToolCall, ExecutedToolCall, Command
from llm import BedrockLLM
import os
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def requires_approval(func):
    """Decorator to mark functions as requiring user approval before execution"""
    func._requires_approval = True
    return func


class ToolCallingBoilerplateAgent(AgentProtocol):
    def __init__(self, llm: BedrockLLM):
        self.llm = llm
        # self.model_id = "us.anthropic.claude-opus-4-20250514-v1:0"
        # self.model_id = "us.anthropic.claude-3-sonnet-20240229-v1:0"
        self.model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        self.tools = self._get_tools()
        self.tool_schemas = self._get_tool_schemas()
        self.approval_required_tools = self._get_approval_required_tools()
        self.max_iterations = 5
        
    # Tool functions - these could be moved to a separate module if needed
    def get_weather(self, location: str, unit: str = "celsius") -> str:
        """Dummy weather function that returns static temperature"""
        return f"The current weather in {location} is 15 degrees {unit}"
    
    def get_stock_price(self, ticker: str) -> str:
        """Dummy stock price function that returns static price"""
        return f"The current stock price of {ticker} is $100"

    def get_current_time(self) -> str:
        """Get the current timestamp"""
        # return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return "The time is 00:00:00 and the date is 01-01-2025"
    
    @requires_approval
    def delete_tenant(self, tenant_name: str) -> str:
        """Delete a tenant from the system"""
        return f"Tenant '{tenant_name}' has been deleted successfully"
    
    @requires_approval
    def create_tenant(self, tenant_name: str) -> str:
        """Create a tenant in the system"""
        return f"Tenant '{tenant_name}' has been created successfully"
    
    def _get_tools(self) -> Dict[str, callable]:
        """Map tool names to their corresponding functions"""
        return {
            "get_weather": self.get_weather,
            "get_stock_price": self.get_stock_price,
            "get_current_time": self.get_current_time,
            "delete_tenant": self.delete_tenant,
            "create_tenant": self.create_tenant,
        }
    
    def _get_approval_required_tools(self) -> set:
        """Get set of tool names that require approval"""
        approval_tools = set()
        for tool_name, tool_func in self.tools.items():
            if hasattr(tool_func, '_requires_approval') and tool_func._requires_approval:
                approval_tools.add(tool_name)
        return approval_tools
    
    def _get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Define tool schemas for the LLM"""
        return [
            {
                "name": "get_weather",
                "description": "Get the current weather in a given location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "The city and state, e.g. San Francisco, CA"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "The unit of temperature, either 'celsius' or 'fahrenheit'"
                        }
                    },
                    "required": ["location"]
                }
            },
            {
                "name": "get_stock_price",
                "description": "Retrieves the current stock price for a given ticker symbol",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "The stock ticker symbol, e.g. AAPL for Apple Inc."
                        }
                    },
                    "required": ["ticker"]
                }
            },

            {
                "name": "get_current_time",
                "description": "Get the current date and time",
                "input_schema": {
                    "type": "object",
                    "properties": {},  # Empty - no inputs needed
                    "required": []     # No required fields
                }
            },
            {
                "name": "delete_tenant",
                "description": "Delete a tenant from the system",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tenant_name": {
                            "type": "string",
                            "description": "The case sensitive name of the tenant to delete"
                        }
                    },
                    "required": ["tenant_name"]
                }
            },
            {
                "name": "create_tenant",
                "description": "Create a tenant in the system",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "tenant_name": {
                            "type": "string",
                            "description": "The name of the tenant to create"
                        }
                    },
                    "required": ["tenant_name"]
                }
            },

            {
                "name": "return_final_response_to_user",
                "description": "Use this tool to return the final response that will be shown to the user once you are ready",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The main response text to display to the user"
                        },
                        "terminal_commands": {
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
                    },
                    "required": ["content"]
                }
            }
        ]

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool function and return the result"""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found"

        logger.info("-" * 40)
        logger.info(f"Executing tool '{tool_name}' with input: {tool_input}")
        
        try:
            tool_function = self.tools[tool_name]
            result = tool_function(**tool_input)

            tool_output = str(result)
            logger.info(f"Tool '{tool_name}' output: {tool_output}")
            logger.info("-" * 40)
            return tool_output
        except Exception as e:
            return f"Error executing tool '{tool_name}': {str(e)}"

    def create_tool_call_for_approval(self, tool_name: str, tool_input: Dict[str, Any], tool_use_id: str) -> ToolCall:
        """Create a ToolCall object for approval"""
        # Get tool schema for descriptions
        tool_schema = None
        for schema in self.tool_schemas:
            if schema["name"] == tool_name:
                tool_schema = schema
                break
        
        tool_description = tool_schema["description"] if tool_schema else f"Execute {tool_name}"
        input_description = {}
        
        if tool_schema and "input_schema" in tool_schema:
            properties = tool_schema["input_schema"].get("properties", {})
            for prop_name, prop_info in properties.items():
                input_description[prop_name] = {
                    "type": prop_info.get("type", "string"),
                    "description": prop_info.get("description", f"Parameter {prop_name}")
                }
        
        return ToolCall(
            id=tool_use_id,
            name=tool_name,
            input=tool_input,
            tool_description=tool_description,
            input_description=input_description
        )
    
    def process_approved_tool_calls(self, messages: Dict[str, List[Dict[str, Any]]]) -> List[ExecutedToolCall]:
        """Process approved tool calls from incoming messages"""
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
                    result = self.execute_tool(tool_call["name"], tool_call["input"])
                    
                    executed_tool = ExecutedToolCall(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        input=tool_call["input"],
                        output=result
                    )
                    executed_tools.append(executed_tool)
                elif tool_call.get("rejection_reason"):
                    # Handle rejected tool - add message about rejection
                    executed_tool = ExecutedToolCall(
                        id=tool_call["id"],
                        name=tool_call["name"],
                        input=tool_call["input"],
                        output=f"Tool execution rejected: {tool_call['rejection_reason']}"
                    )
                    executed_tools.append(executed_tool)
        
        return executed_tools
    
    def process_tool_calls(self, response_content: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[ToolCall]]:
        """Process tool calls from LLM response - execute non-approval tools, return approval tools"""
        executed_tool_calls = []
        approval_required_tools = []
        
        for content_block in response_content:
            if content_block.get("type") == "tool_use":
                tool_name = content_block.get("name")
                tool_input = content_block.get("input", {})
                tool_use_id = content_block.get("id")
                
                if tool_name in self.approval_required_tools:
                    # Tool requires approval - add to approval list
                    tool_call = self.create_tool_call_for_approval(tool_name, tool_input, tool_use_id)
                    approval_required_tools.append(tool_call)
                else:
                    # Tool doesn't require approval - execute immediately
                    result = self.execute_tool(tool_name, tool_input)
                    
                    # Format tool result for next LLM call
                    executed_tool_calls.append(
                        ExecutedToolCall(
                            id=tool_use_id,
                            name=tool_name,
                            input=tool_input,
                            output=result
                        )
                    )
        
        return executed_tool_calls, approval_required_tools

    def call_bedrock_anthropic_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call the LLM with tool support"""
        system_prompt = """You are a helpful assistant called Dash. Do not use tools (other than the return_final_response_to_user tool) unless necessary.
Use the return_final_response_to_user tool once you've used all the other tools you need to use to generate the final answer. 
When using the return_final_response_to_user tool, you can return a text response to the user as well as terminal commmands in the 'terminal_commands' field which will be shown to the user in an approval box below the text in the 'content' field. Once approved by the user, the terminal commands will be executed in a non interactive shell using subprocess.run and the results will be provided to you.
Be extremely critical and ask clarifying questions if needed. 
Be surgical, simple and less wordy."""
        
        return self.llm.invoke(
            model_id=self.model_id,
            messages=messages,
            max_tokens=4000,
            system_prompt=system_prompt,
            return_raw_api_response=True,
            tools=self.tool_schemas,
            tool_choice={"type": "any"}
        )

    def preprocess_messages(self, messages: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Convert input messages to LLM format"""
        preprocessed_messages = []
        messages_list = messages.get("messages", [])
        
        for message in messages_list:
            if message.get("role") == "user":
                preprocessed_messages.append({
                    "role": "user", 
                    "content": message.get("content", "")
                })
            elif message.get("role") == "assistant":
                preprocessed_messages.append({
                    "role": "assistant", 
                    "content": message.get("content", "")
                })
        
        return preprocessed_messages
        
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """Main agent invocation with tool support"""
        # First, process any approved tool calls from the incoming message
        executed_tool_calls = self.process_approved_tool_calls(messages)
        
        # Add executed tool results to conversation if any
        conversation_messages = self.preprocess_messages(messages)
        if executed_tool_calls:
            for executed_tool_call in executed_tool_calls:
                tool_execution_result_content = f"Tool result for {executed_tool_call.name} with inputs {executed_tool_call.input}: {executed_tool_call.output}"
                conversation_messages.append({
                    "role": "user",
                    "content": tool_execution_result_content
                })
        
        logger.info("Entering agent execution loop..")
        num_iterations = 0
        while True:
            num_iterations += 1
            if num_iterations > self.max_iterations:
                logger.error("Max iterations reached. Stopping execution.")
                break

            logger.info("Iteration %s", num_iterations)
            
            # Call LLM
            response = self.call_bedrock_anthropic_llm(conversation_messages)
            response_content = response.get("content", [])
            
            # Check if final response tool is called
            final_response_call = None
            other_tool_calls = []
            
            for content_block in response_content:
                if (content_block.get("type") == "tool_use" and 
                    content_block.get("name") == "return_final_response_to_user"):
                    final_response_call = content_block
                elif content_block.get("type") == "tool_use":
                    other_tool_calls.append(content_block)
            
            # If final response tool is called, return the structured response
            if final_response_call:
                final_input = final_response_call.get("input", {})
                
                # Create response with both terminal commands and tool calls if any pending
                agent_message = AgentMessage(
                    content=final_input.get("content", "")
                )
                
                # Add terminal commands to data if present
                if final_input.get("terminal_commands"):
                    for cmd in final_input.get("terminal_commands", []):
                        agent_message.data.cmds.append(Command(
                            command=cmd.get("command"),
                            execute=False
                        ))
                
                return agent_message
            
            # Process other tool calls
            if other_tool_calls:
                # Add assistant message with tool calls
                conversation_messages.append({
                    "role": "assistant",
                    "content": "Processing Tool Calls"
                })
                
                # Process tools - execute non-approval ones, collect approval-required ones
                executed_tool_calls, approval_required_tools = self.process_tool_calls(response_content)
                
                # If there are approval-required tools, return them for user approval
                if approval_required_tools:
                    agent_message = AgentMessage(
                        content="I need your approval to execute the following tools:"
                    )
                    
                    # Add tool calls to data for approval
                    for tool_call in approval_required_tools:
                        if tool_call.name == "delete_tenant":
                            tool_call.intent = "Sample Intent: Delete a tenant"
                        agent_message.data.tool_calls.append(tool_call)
                    
                    return agent_message
                
                # If only non-approval tools were called, add results and continue
                if executed_tool_calls:
                    for executed_tool_call in executed_tool_calls:
                        executed_tool_call_content = f"Tool result for {executed_tool_call.name} with input {executed_tool_call.input}: {executed_tool_call.output}"
                        conversation_messages.append({
                            "role": "user",
                            "content": executed_tool_call_content
                        })
                
                # Continue the loop to get next LLM response
                continue
            
            # Fallback - no tools or final response
            return AgentMessage(content=response)


# Usage example:
if __name__ == "__main__":
    from llm import BedrockLLM
    import dotenv
    
    dotenv.load_dotenv(override=True)
    
    llm = BedrockLLM()
    agent = ToolEnabledLLMAgent(llm)
    
    # Test with mixed tool calls (approval and non-approval)
    test_messages = {
        "messages": [
            {
                "role": "user", 
                "content": "What's the weather in San Francisco? Also delete the tenant 'test-tenant' and get the current time."
                # "content": "Update S3 bucket 'my-bucket' with a new policy and get stock price for AAPL"
                # "content": "What is the time?"
                # "content": "Run a terminal command to list directories"
            }
        ]
    }
    
    result = agent.invoke(test_messages)
    print("Result:", result.content)
    if hasattr(result, 'terminal_commands') and result.terminal_commands:
        print("Terminal commands:", result.terminal_commands)

    print()
    print("-" * 50)
    print(result)