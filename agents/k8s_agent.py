import json

import logging
import traceback

import subprocess
import os
import base64
import tempfile
from typing import List, Dict, Any, Optional

from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Command, ExecutedCommand, Data
from services.llm import BedrockAnthropicLLM

logger = logging.getLogger(__name__)

class K8sAgent(AgentProtocol):
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
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """
        Process user messages, execute commands if approved, and generate a response.
        
        Args:
            messages: A dictionary containing message history in the format {"messages": [...]}
            
        Returns:
            An AgentMessage containing the response, suggested commands, and executed commands
        """
        # Process messages to handle command execution and prepare for LLM
        processed_messages, executed_commands = self.process_messages(messages)
        
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
        processed_messages: List[Dict[str, Any]] = []
        executed_cmds_current_turn: List[Dict[str, str]] = []

        # --- extract kubeconfig (latest in history) and write to temp file --- TODO Just make it last messsage?
        kubeconfig_path: Optional[str] = None
        for m in reversed(messages.get("messages", [])):
            if m.get("role") == "user":
                kube_b64 = (m.get("platform_context") or {}).get("kubeconfig")
                if kube_b64:
                    try:
                        tmp = tempfile.NamedTemporaryFile(delete=False)
                        tmp.write(base64.b64decode(kube_b64))
                        tmp.flush()
                        os.chmod(tmp.name, 0o600)
                        kubeconfig_path = tmp.name
                    except Exception as e:
                        logger.warning("Failed to set up kubeconfig: %s", e)
                    break

        # Extract the messages list
        messages_list = messages.get("messages", [])

        # Iterate through the conversation history
        for idx, msg in enumerate(messages_list):
            role = msg.get("role")
            if role not in {"user", "assistant"}:
                continue

            # Base message content #TODO update it to handle the case where assistant message as the last message
            content = msg.get("content", "")

            data = msg.get("data", {}) if role == "user" else {}

            if role == "user":

                # Append platform context if provided in the user message
                platform_context = msg.get("platform_context")
                if platform_context:
                    pc_lines = []
                    ns = platform_context.get("k8s_namespace")
                    if ns:
                        pc_lines.append(f"Kubernetes namespace: {ns}")
                    tenant = platform_context.get("tenant_name")
                    if tenant:
                        pc_lines.append(f"DuploCloud tenant: {tenant}")
                    # Only indicate kubeconfig/credentials presence to avoid leaking large sensitive blobs
                    if platform_context.get("kubeconfig"):
                        pass
                        # pc_lines.append("kubeconfig provided")
                    if pc_lines:
                        content = "\n\Current Message Context:\n- " + "\n- ".join(pc_lines) + "\n\n" + content

                # 1. Append context for user-executed commands
                for uc in data.get("executed_cmds", []):
                    cmd = uc.get("command", "")
                    out = uc.get("output", "")
                    content += f"\n\nI ran this command in my terminal: {cmd}\nOutput:\n{out}"

                # 2. Append any rejections
                for c in data.get("cmds", []):
                    reason = c.get("rejection_reason")
                    if reason:
                        content += f"\n\nI rejected the suggested command: {c.get('command', '')}\nReason: {reason}"

                # 3. Execute approved commands only in the latest user message
                is_latest_user_msg = (idx == len(messages_list) - 1)
                if is_latest_user_msg:
                    for c in data.get("cmds", []):
                        if c.get("execute", False):
                            cmd_str = c.get("command", "")
                            logger.info("Executing approved command: %s", cmd_str)
                            output = self.execute_cmd(cmd_str, kubeconfig_path)
                            executed_cmds_current_turn.append({"command": cmd_str, "output": output})
                            content += f"\n\nExecuted command: {cmd_str}\nOutput:\n{output}"

            processed_messages.append({"role": role, "content": content})

        # clean up temp kubeconfig
        if kubeconfig_path and os.path.exists(kubeconfig_path):
            try:
                os.remove(kubeconfig_path)
            except OSError:
                pass

        return processed_messages, executed_cmds_current_turn
    
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
            traceback_error = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error("Error while making LLM API call:\n%s", traceback_error)

            if "An error occurred (ExpiredTokenException) when calling the InvokeModel operation: The security token included in the request is expired" in str(e):
                solution = "If running the agent locally with Bedrock, refresh the aws creds in the .env file (use the env_update_aws_creds.sh script if using DuploCloud; refer README)."
                raise Exception(f"Error while making LLM API call: {str(e)}. {solution}")
            else:
                raise Exception(f"Error while making LLM API call: {str(e)}")
    
    def execute_cmd(self, command: str, kubeconfig_path: Optional[str] = None) -> str:
        """
        Execute a terminal command and return its output.
        
        Args:
            command: The command string to execute
            
        Returns:
            The command output as a string
        """
        try:
            logger.info(f"Executing command: {command}")
            env = os.environ.copy()
            if kubeconfig_path:
                env["KUBECONFIG"] = kubeconfig_path
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                env=env
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

    def _duplocloud_context(self) -> str:
        """
        Return the DuploCloud context for the LLM.
        
        Returns:
            The DuploCloud context string
        """

        duplocloud_concepts_context = """
# 📚 DuploCloud Concepts Cheat-Sheet  (inject into every agent)

## What “service” means here
• **DuploCloud Service** = one micro-service you declared in the DuploCloud UI.  
  ↳ DuploCloud materialises it as **one Kubernetes Deployment (or StatefulSet)** plus its Pods, HPA, ConfigMaps, etc.  
  ↳ The Deployment/Pods carry the label **app=<service-name>**.

• **It is *not* a Kubernetes `Service` object.**  
  – A K8s `Service` is just the ClusterIP/LoadBalancer front-end DuploCloud creates for traffic.  
  – When a user says “cart service”, they almost always mean the *workload* (Deployment & Pods) called **cart**, not that K8s `Service` resource.

### Key takeaway
Whenever a user mentions “<name> service” inside DuploCloud, interpret it as **the Deployment/StatefulSet and its Pods labeled `app=<name>`**, *not* the Kubernetes `Service` resource.
"""

        return duplocloud_concepts_context
    
    def _default_system_prompt(self) -> str:
        """
        Return the default system prompt for the LLM.
        
        Returns:
            The system prompt string
        """
        # Primary prompt plus DuploCloud context in a dedicated helper for easy maintenance
        return (
            "You are a seasoned Kubernetes and Helm expert agent for DuploCloud. "
            "Help users troubleshoot and operate clusters concisely.\n\n" +
            "DuploCloud Concepts Context:\n" + self._duplocloud_context() + "\n\n" +
            "Guidelines:\n"
            "1. Suggest precise, safe kubectl or Helm commands. \n"
            "2. Keep answers short and actionable.\n"
            "3. Always use the structured `return_response` tool.\n"
            "4. Respect any commands the user already ran or rejected.\n"
        )
    
    def _create_response_schema(self) -> Dict[str, Any]:
        """
        Create the JSON schema for structured LLM responses.
        
        Returns:
            The response schema as a dictionary
        """
        return {
            "name": "return_response",
            "description": "Generate a structured response with explanatory text and terminal commands",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The main response text to display to the user. Should provide a clear explanation."
                    },
                    "terminal_commands": {
                        "type": "array",
                        "description": "Terminal commands that will be displayed to the user for approval before execution. The commands you execute if approved by the user will be run by the agent in a non-interactive terminal using subprocess.run. So do not suggest commands which need to be run in an interactive user attached terminal, like: kubectl edit, exec etc here. Suggest thos types of commands in the regular content field displayed to the user if needed.",
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
