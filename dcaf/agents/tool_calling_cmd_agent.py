from typing import Dict, Any, List, Optional
import os
import json
import logging
from datetime import datetime

from ..agent_server import AgentProtocol
from ..schemas.messages import AgentMessage, ExecutedToolCall
from ..llm import BedrockLLM

logger = logging.getLogger(__name__)


class ToolCallingCmdAgent(AgentProtocol):
    def __init__(self, llm: BedrockLLM):
        self.llm = llm
        # self.model_id = "us.anthropic.claude-opus-4-20250514-v1:0"
        self.model_id = "us.anthropic.claude-3-sonnet-20240229-v1:0"
        self.tools = self._get_tools()
        self.tool_schemas = self._get_tool_schemas()
        
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
    
    def _get_tools(self) -> Dict[str, callable]:
        """Map tool names to their corresponding functions"""
        return {
            "get_weather": self.get_weather,
            "get_stock_price": self.get_stock_price,
            "get_current_time": self.get_current_time,
        }
    
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

        logger.info("-" * 50)
        logger.info(f"Executing tool '{tool_name}' with input: {tool_input}")
        
        try:
            tool_function = self.tools[tool_name]
            result = tool_function(**tool_input)

            tool_output = str(result)
            logger.info(f"Tool '{tool_name}' output: {tool_output}")
            logger.info("-" * 50)
            return tool_output
        except Exception as e:
            return f"Error executing tool '{tool_name}': {str(e)}"

    def process_tool_calls(self, response_content: List[Dict[str, Any]]) -> List[ExecutedToolCall]:
        """Process tool calls from LLM response and return tool results"""
        executed_tool_calls = []
        
        for content_block in response_content:
            if content_block.get("type") == "tool_use":
                tool_name = content_block.get("name")
                tool_input = content_block.get("input", {})
                tool_use_id = content_block.get("id")
                
                # Execute the tool
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
        
        return executed_tool_calls

    def call_bedrock_anthropic_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Call the LLM with tool support"""
        system_prompt = """You are a helpful assistant called Dash. Do not use tools (other than the return_final_response_to_user tool) unless necessary.
Use the return_final_response_to_user tool once you've used all the other tools you need to use to generate the final answer. 
When using the return_final_response_to_user tool, you can return a text response to the user as well as terminal commmands in the 'terminal_commands' field which will be shown to the user in an approval box below the text in the 'content' field. Once approved by the user, the terminal commands will be executed in a non interactive shell using subprocess.run and the results will be provided to you.
Be extremely critical and ask clarifying questions if needed. 
Be surgical, simple and less wordy."""
        
        return self.llm.invoke(
            model_id=self.model_id,
            messages=self.llm.normalize_message_roles(messages),
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
        conversation_messages = self.preprocess_messages(messages)
        
        while True:
            # Call LLM
            response = self.call_bedrock_anthropic_llm(conversation_messages)
            response_content = response.get("content", [])
            
            # Check if response contains tool calls
            has_tool_calls = any(block.get("type") == "tool_use" for block in response_content)
            
            if not has_tool_calls:
                # No tools called, return response
                return AgentMessage(content=response)
            
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
                return AgentMessage(
                    content=final_input.get("content", ""),
                    terminal_commands=final_input.get("terminal_commands", [])
                )
            
            # Process other tool calls
            if other_tool_calls:
                # Add assistant message with tool calls
                tool_calls_message = 'Making Tool Calls.'
                conversation_messages.append({
                    "role": "assistant",
                    "content": tool_calls_message
                })
                
                # Execute tools and add results
                executed_tool_calls = self.process_tool_calls(response_content)
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
    
    # Test with weather and stock request
    test_messages = {
        "messages": [
            {
                "role": "user", 
                # "content": "Hi! What is your name? What is the weather in Hyderabad? What is the stock price of AAPL?"
                # "content": "List directories in the current directory"
                # "content": "What is the time?"
                "content": "Run a terminal command to list directories"
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