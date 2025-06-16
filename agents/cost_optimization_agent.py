import json
import logging
import subprocess
import os
from typing import List, Dict, Any, Optional
from services.aws_service import AWSService
from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Command, ExecutedCommand, Data
from services.llm import BedrockAnthropicLLM

logger = logging.getLogger(__name__)

class CostOptimizationCommandAgent(AgentProtocol):
    """
    An agent that processes user messages, executes terminal commands with user approval,
    and uses an LLM to generate responses and suggest commands.
    """
    
    def __init__(self, llm: BedrockAnthropicLLM, system_prompt: Optional[str] = None):
        """
        Initialize the CommandAgent with an LLM instance and optional custom system prompt.
        
        Args:
            llm: An instance of BedrockAnthropicLLM for generating responses
            system_prompt: Optional custom system prompt to override the default
        """
        self.llm = llm
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.response_schema = self._create_response_schema()
        self.aws = AWSService()

    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """
        Process user messages, execute commands if approved, and generate a response.
        
        Args:
            messages: A dictionary containing message history in the format {"messages": [...]}
            
        Returns:
            An AgentMessage containing the response, suggested commands, and executed commands
        """
        # Extract platform context from the first user message
        platform_context = None
        if messages and "messages" in messages and messages["messages"]:
            for message in messages["messages"]:
                if message.get("role") == "user" and message.get("platform_context"):
                    platform_context = message.get("platform_context")
                    break

        # Extract tenant name from platform context
        tenant_name = self.extract_tenant_name(platform_context)
        print(f"[DEBUG] Extracted tenant name: {tenant_name}")
        # Process messages to handle command execution and prepare for LLM
        processed_messages, executed_commands = self.process_messages(messages)
        resource_type = self.detect_resource_types(processed_messages)
        print(f"[DEBUG] Detected resource: {resource_type}")
        # prompt = f"User request: {user_input}\n\n"
        prompt = ''
        if 'ec2' == resource_type:
                print(f"[DEBUG] Inside Detected resource: {resource_type}")
                ec2_stats = self.aws.get_ec2_instance_stats(tenant_name)
                prompt += "**EC2 Instances:**\n"
                for i in ec2_stats:
                    prompt += f"- {i['id']} | Type: {i['type']} | CPU: {i['cpu']}% | Mem: {i['memory']}% | State: {i['state']}\n"
                    prompt += "\nPlease suggest optimizations if you see any scope. Also, include the mobthly savings in dollars. Keep it crisp , clean & concise"
        if 'rds' == resource_type:
                print(f"[DEBUG] Inside Detected resource: {resource_type}")
                rds_stats = self.aws.get_rds_instance_stats(tenant_name)
                prompt += "\n**RDS Instances:**\n"
                for db in rds_stats:
                    prompt += f"- {db['id']} | Class: {db['class']} | CPU: {db['cpu']}% | Mem: {db['memory']}% | State: {db['state']}\n"
                    prompt += "\nPlease suggest optimizations if you see any scope. Also, include the mobthly savings in dollars. Keep it crisp , clean & concise"

        if prompt != '':
            new_user_message = { 'role':'user','content':prompt, 'meta': {'resource_stats': resource_type}}
            processed_messages.append(new_user_message)
        # Generate response from LLM
        llm_response = self.call_llm(processed_messages)
        
        # Extract commands from LLM response
        commands = self._extract_commands(llm_response)
        
        # Create and return the agent message with both suggested and executed commands
        return AgentMessage(
            content=llm_response.get("content", "I'm unable to provide a response at this time."),
            data=Data(
                cmds=[Command(command=cmd["command"]) for cmd in commands],
                executed_cmds=[ExecutedCommand(command=cmd["command"], output=cmd["output"]) 
                              for cmd in executed_commands]
            )
        )

    def extract_tenant_name(self, platform_context: Optional[Dict[str, Any]]) -> str:
        """
        Initialize Tenant name with platform context.
        
        Args:
            platform_context: Dictionary containing tenant_name.
        
        Returns:
            Tenant name as a string or an empty string if validation fails
        """
        if not platform_context:
            logger.warning("No platform context provided for Tenant initialization")
            return "default"
            
        try:
            tenant_name = platform_context.get("tenant_name", "default")
            if not tenant_name:
                logger.error("Tenant name not found in platform context")
            logger.info(f"Tenant name {tenant_name} found in platform context")
            return tenant_name
                
        except Exception as e:
            logger.error(f"Error initializing Tenant: {str(e)}")
            return "default"

    def process_messages(self, messages: Dict[str, List[Dict[str, Any]]]) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """
        Process the raw messages to handle command execution and prepare for LLM.
        
        Args:
            messages: A dictionary containing message history in the format {"messages": [...]}
            
        Returns:
            A tuple containing:
            - A list of processed messages ready for the LLM
            - A list of executed commands with their outputs
        """
        processed_messages = []
        executed_cmds = []
        
        # Extract the messages list from the dictionary
        messages_list = messages.get("messages", [])
        
        for msg in messages_list:
            # Ensure we're only processing messages with valid roles (user or assistant)
            print(f"[DEBUG] Message content: {msg.get('content')}")
            role = msg.get("role")
            if role not in ["user", "assistant"]:
                continue
                
            # Create a basic message with role and content
            processed_msg = {"role": role, "content": msg.get("content", "")}
            
            # Process user messages with approved commands
            if role == "user":
                data = msg.get("data", {})
                
                # Check for commands to execute - only in the current message
                if "cmds" in data and msg == messages_list[-1]:  # Only check the most recent message
                    logger.info(f"data print: {data}")
                    logger.info(f"Processing commands in most recent user message: {data['cmds']}")
                    for cmd in data["cmds"]:
                        if cmd.get("execute", False):
                            logger.info(f"Executing approved command: {cmd['command']}")
                            # Execute the approved command
                            output = self.execute_cmd(cmd["command"])
                            
                            # Track executed commands
                            executed_cmds.append({
                                "command": cmd["command"],
                                "output": output
                            })
                            
                            # Append command output to the message content
                            cmd_info = f"\n\nExecuted command: {cmd['command']}\nOutput: {output}"
                            processed_msg["content"] += cmd_info
                        else:
                            logger.info(f"Skipping command without execute flag: {cmd['command']}")
                
                # Include previously executed commands
                if "executed_cmds" in data and data["executed_cmds"]:
                    for cmd in data["executed_cmds"]:
                        executed_cmds.append(cmd)
                        cmd_info = f"\n\nPreviously executed: {cmd['command']}\nOutput: {cmd['output']}"
                        processed_msg["content"] += cmd_info
            
            # Add the processed message to the list
            processed_messages.append(processed_msg)
        
        return processed_messages, executed_cmds
    
    def call_llm(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Make an API call to the LLM with the processed messages.
        
        Args:
            messages: A list of processed message dictionaries
            
        Returns:
            The LLM response as a dictionary
        """
        try:
            # Use the schema as a tool to structure the response
            tool_choice = {
                "type": "tool",
                "name": "return_response"
            }
            
            # Invoke the LLM with the messages, system prompt, and response schema
            model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
            response = self.llm.invoke(
                model_id=model_id,
                messages=self.llm.normalize_message_roles(messages),
                max_tokens=4000,
                system_prompt=self.system_prompt,
                tools=[self.response_schema],
                tool_choice=tool_choice
            )
            
            logger.info(f"LLM Response: {response}")
            return response
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return {"content": f"I encountered an error when generating a response: {str(e)}"}
    
    def execute_cmd(self, command: str) -> str:
        """
        Execute a terminal command and return its output.
        
        Args:
            command: The command string to execute
            
        Returns:
            The command output as a string
        """
        try:
            logger.info(f"Executing command: {command}")
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True
            )
            
            # Combine stdout and stderr for the output
            output = result.stdout
            if result.stderr:
                if output:
                    output += f"\n\nErrors:\n{result.stderr}"
                else:
                    output = f"Errors:\n{result.stderr}"
                    
            if not output:
                output = "Command executed successfully with no output."
                
            return output
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return f"Error executing command: {str(e)}"


    def detect_resource_types(self, messages: List[Dict[str, Any]]) -> str:
        print("[DEBUG] Starting detect_resource_types")

        try:
            system_prompt = (
                "You are a resource classifier for AWS cost optimization.\n\n"
                "Given the full conversation history, determine which AWS resource the user is currently requesting analysis for: either 'ec2' or 'rds'.\n\n"
                "If the resource has already been analyzed in a previous assistant response (e.g., the assistant already discussed utilization or optimization suggestions for that resource), then respond with 'null'.\n\n"
                "Output ONLY one of the following strings (in lowercase, without quotes): ec2, rds, null.\n"
                "Do not explain your answer. Do not output anything else."
            )


            normalized_messages = self.llm.normalize_message_roles(messages)
            print(f"[DEBUG] Normalized messages: {normalized_messages}")

            response = self.llm.invoke(
                model_id=os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"),
                messages=normalized_messages,
                max_tokens=10,
                system_prompt=system_prompt,
            )

            # Safely extract string response
            resource = response.strip().lower() if isinstance(response, str) else response.get("content", "").strip().lower()
            print(f"[DEBUG] Parsed resource: {resource}")

            if resource in {"ec2", "rds"}:
                return resource
            return "null"

        except Exception as e:
            print(f"[DEBUG] Error in detect_resource_types: {e}")
            return "null"

        
    
    def _extract_commands(self, llm_response: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract commands from the LLM response.
        
        Args:
            llm_response: The response from the LLM
            
        Returns:
            A list of command dictionaries
        """
        commands = []
        
        # Extract commands if they exist in the response
        if "terminal_commands" in llm_response:
            commands = llm_response["terminal_commands"]
        
        return commands
    
    def _default_system_prompt(self) -> str:
        """
        Return the default system prompt for the LLM.
        
        Returns:
            The system prompt string
        """
        return """
        General Instructions:        
        You are a helpful terminal command assistant. Your role is to assist users by suggesting 
        appropriate terminal commands to accomplish their tasks and explain the commands clearly.
        
        Guidelines:
        1. Suggest precise, safe terminal commands that directly address the user's request
        2. Explain what each command does and why you're suggesting it
        3. If multiple commands are needed, list them in the correct sequence
        4. Be mindful of different operating systems - ask for clarification if needed
        5. Provide clear, concise explanations in plain language
        6. If a task cannot be accomplished with terminal commands, explain why and suggest alternatives
        7. Always prioritize safe commands that won't damage the user's system
        
        Always use the structured response format to organize your suggestions.

        # Duplo Dash - AWS Cost Optimization Assistant

        ## Role
        You are Duplo Dash, an AWS cost optimization specialist focused on analyzing resource utilization and recommending cost-saving actions.

        ## Core Responsibilities
        - Analyze AWS resource usage metrics (CPU, memory, network)
        - Recommend specific optimization actions: stop, resize, right-size, or schedule instances
        - Generate precise AWS CLI commands for recommended actions
        - Process one resource at a time for clarity

        ## Communication Style
        - **Concise**: Provide direct, actionable responses without unnecessary explanation
        - **Critical**: Ask targeted questions to gather essential information before making recommendations
        - **Structured**: Present recommendations with clear formatting and reasoning

        ## Required Information Gathering
        Before making recommendations, collect:
        - Resource type and current specifications
        - Usage patterns and metrics (CPU/memory utilization over time)
        - Business requirements and constraints
        - Peak usage periods and criticality

        ## Output Format
        For each resource:
        1. **Analysis Summary**: Brief utilization assessment
        2. **Recommendation**: Specific action with cost impact estimate, 
        3. **AWS CLI Command**: Ready-to-execute command
        4. **Confirmation Request**: Explicit permission before execution

        ## Safety Protocol
        - Always request user confirmation before providing destructive commands
        - Highlight potential downtime or service impact
        - Recommend testing in non-production environments first

        Focus on one resource type per response to maintain clarity and prevent errors.
        You can ask user to specify resource type if its not clear in his request.
        Support only EC2 & RDS, always ask user for their choice if its not clear in user request. Dont assume any default resource type.
        Its ok if it takes multiple request to give final required output. 
        Provide single commands per request to avoid confusion if response needs to have some command.
        You dont need to look for command approvals on resource utilization requests.
        You can need to take approvals on action commands basically which will include some sort of action for cost optimization.
        You dont need to ask user for permission on executing commands which will help you get utilization data. We already have functions 
        Keep response concise & not too lenghty.
        If user requests some data which is not sensitive & is readonly then you can assume default grant & run the commands if they are readonly.
        If user request did not mention resource type specifically, then you need to ask to mention it clearly to the user, Should not assume any default resource.
        dont share Recommendation in the same response as Analysis Summary, instead ask user for any preference & then share Recommendation in next response
        Share Recommendation for resource at a time, instead of sharing it for multiple resources, as it would create confusion & complexity will be increased. Try to share single aws command for recommended action which will be easy for user to understand. 
        """
    
    def _create_response_schema(self) -> Dict[str, Any]:
        """
        Create the JSON schema for structured LLM responses.
        
        Returns:
            The response schema as a dictionary
        """
        return {
            "name": "return_response",
            "description": "Generate a structured response with explanatory text and aws terminal commands",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The main response text to display to the user. Should provide a clear explanation."
                    },
                    "terminal_commands": {
                        "type": "array",
                        "description": "Terminal commands that will be displayed to the user for approval before execution.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "The complete terminal command string to be executed."
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "A brief explanation of what this command does."
                                }
                            },
                            "required": ["command"]
                        }
                    }
                },
                "required": ["content"]
            }
        }

        



