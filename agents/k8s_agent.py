import json
import logging
import traceback
import subprocess
import os
import base64
import tempfile
import shutil
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Command, ExecutedCommand, Data
from services.llm import BedrockAnthropicLLM
from services.prompt_manager import PromptManager

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
            system_prompt: Optional custom system prompt to override the dynamic prompts
        """
        self.llm = llm
        
        # Check if there's a local static prompt file
        local_prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'prompt.txt')
        self.using_static_prompt = False
        
        if os.path.isfile(local_prompt_path):
            # Use the static prompt file instead of dynamic prompts
            try:
                with open(local_prompt_path, 'r') as f:
                    self.system_prompt_override = f.read()
                logger.info(f"Using local static prompt from {local_prompt_path}")
                self.using_static_prompt = True
            except Exception as e:
                logger.warning(f"Failed to read local prompt file {local_prompt_path}: {str(e)}")
                self.system_prompt_override = system_prompt
        else:
            # Store the override system prompt if provided
            self.system_prompt_override = system_prompt
        
        # Only initialize dynamic prompts if not using static prompt
        if not self.using_static_prompt:
            # Initialize the prompt manager
            self.prompt_manager = PromptManager()
            
            # Start the background refresh task (which will also do the initial refresh)
            self.prompt_manager.start_background_refresh()
        else:
            self.prompt_manager = None
        
        # Schema for LLM responses
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
                cmds=[Command(command=cmd["command"], files=cmd.get("files")) for cmd in commands],
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
        # Store the latest platform context for potential duploctl env vars
        latest_platform_context = None
        
        for m in reversed(messages.get("messages", [])):
            if m.get("role") == "user":
                platform_context = m.get("platform_context")
                if platform_context:
                    latest_platform_context = platform_context
                    
                kube_b64 = (platform_context or {}).get("kubeconfig")
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

            content = "(Current Request Ephemeral Instructions: - If the user asks to convert a docker compose into a helm chart, ask for the name of the helm chart and confirm with the user.\n- Be less wordy and to the point. And for helm chart creation give the required command and the files in a single command object. Remember the files in a command object are not persisted for the next command's execution. Do not suggest any other helm commands that need to use the previous files again.)\n\n" + content


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
                    # DuploCloud plan if specified
                    duplo_plan = platform_context.get("duplo_plan")
                    if duplo_plan:
                        pc_lines.append(f"DuploCloud plan: {duplo_plan}")
                    # DuploCloud base URL if specified
                    duplo_base_url = platform_context.get("duplo_base_url")
                    if duplo_base_url:
                        pc_lines.append(f"DuploCloud base URL: {duplo_base_url}")
                    # Only indicate kubeconfig/credentials presence to avoid leaking large sensitive blobs
                    if platform_context.get("kubeconfig"):
                        pass
                        # pc_lines.append("kubeconfig provided")
                    if platform_context.get("duplo_token"):
                        pc_lines.append("DuploCloud token provided")
                    if pc_lines:
                        content = "\n\nCurrent Message Context:\n- " + "\n- ".join(pc_lines) + "\n\n" + content

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
                    # execute approved commands
                    for c in data.get("cmds", []):
                        if c.get("execute", False):
                            cmd_str = c.get("command", "")
                            logger.info("Executing approved command: %s", cmd_str)
                            files = c.get("files")
                            output = self.execute_cmd(cmd_str, kubeconfig_path, files, platform_context)
                            executed_cmds_current_turn.append({"command": cmd_str, "output": output})

                            # Add executed command and files to content
                            if files:
                                files_str = "\n".join([f"{f.get('file_path', '')}: {f.get('file_content', '')}" for f in files])
                                content += f"\n\nCreated tmp dir with tmp files for command execution:\n{files_str}\n\nExecuted command: {cmd_str}\nOutput:\n{output}\n (Note: The tmp dir with the above tmp files created have been deleted after the command execution.)"
                            else:
                                content += f"\n\nExecuted command: {cmd_str}\nOutput:\n{output}\n"

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
            
            # Extract platform context from messages if available
            platform_context = None
            for m in messages:
                if m.get("role") == "user" and m.get("platform_context"):
                    platform_context = m.get("platform_context")
                    break
            
            # Use static prompt override or get the dynamic system prompt
            system_prompt = self.system_prompt_override
            if not system_prompt and not self.using_static_prompt:
                logger.info("Using dynamic system prompt")
                # Prepare variables for prompt substitution
                variables = {
                    "agent_name": self.__class__.__name__,
                    "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                
                # Add all platform context variables if available
                if platform_context:
                    # Iterate through all keys in platform_context
                    for key, value in platform_context.items():
                        if value:  # Only add non-empty values
                            variables[key] = value
                            
                            # Also add namespace as an alias for k8s_namespace for backward compatibility
                            if key == "k8s_namespace":
                                variables["namespace"] = value
                
                system_prompt = self.prompt_manager.get_combined_prompt(variables)
            elif self.using_static_prompt:
                logger.info("Using static prompt from prompt.txt file")
            
            logger.info(f"System prompt: {system_prompt}")
            
            # Invoke the LLM with the messages, system prompt, and response schema
            model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
            # model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            # model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
            response = self.llm.invoke(
                model_id=model_id,
                messages=self.llm.normalize_message_roles(messages),
                max_tokens=4000,
                system_prompt=system_prompt,
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
    
    def execute_cmd(self, command: str, kubeconfig_path: Optional[str] = None, files: Optional[List[Dict[str, str]]] = None, platform_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Execute a terminal command and return its output.
        
        Args:
            command: The command string to execute
            kubeconfig_path: Optional path to a kubeconfig file for kubectl commands
            files: Optional list of files to create before executing the command
            platform_context: Optional platform context containing environment variables
            
        Returns:
            The command output as a string
        """
        tmp_dir = None
        output = ""
        try:
            logger.info("Executing command: %s", command)
            # --- create temp dir & files if provided ---
            if files:
                tmp_dir = tempfile.mkdtemp(prefix="cmd_files_")
                for f in files:
                    try:
                        path = os.path.join(tmp_dir, f.get("file_path", ""))
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        with open(path, "w") as fh:
                            fh.write(f.get("file_content", ""))
                    except Exception as e:
                        logger.warning("Failed writing temp file %s: %s", f, e)

            env = os.environ.copy()
            
            # Set environment variables for kubectl commands
            if kubeconfig_path and (command.startswith("kubectl") or "kubectl " in command):
                env["KUBECONFIG"] = kubeconfig_path
                
            # Set environment variables for duploctl commands
            if command.startswith("duploctl") or "duploctl " in command:
                logger.info("Executing duploctl command")
                
                # Process platform context to get duploctl environment variables if available
                if platform_context:
                    duplo_env_vars = self.process_platform_context(platform_context)
                    logger.info(f"Using DuploCloud environment variables: {duplo_env_vars}")
                    env.update(duplo_env_vars)
                                
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                env=env,
                cwd=tmp_dir if tmp_dir else None
            )
            output = result.stdout or ""
            if result.stderr:
                output += ("\n\nErrors:\n" + result.stderr)
            if not output:
                output = "Command executed successfully with no output."
            return output
        except Exception as e:
            logger.error("Error executing command: %s", e)
            return f"Error executing command: {str(e)}"
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    
    def _extract_commands(self, llm_response: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract commands from the LLM response.
        
        Args:
            llm_response: The response from the LLM
            
        Returns:
            A list of command dictionaries
        """
        cmds: List[Dict[str, Any]] = []
        raw = llm_response.get("terminal_commands", [])
        for item in raw:
            if isinstance(item, str):
                cmds.append({"command": item})
            elif isinstance(item, dict):
                cmds.append(item)
        return cmds

    def process_platform_context(self, platform_context: Dict[str, Any]) -> Dict[str, str]:
        """
        Process platform context to extract DuploCloud environment variables.
        
        Args:
            platform_context: Dictionary containing platform context information
            
        Returns:
            A dictionary of environment variables for DuploCloud
        """
        env_vars = {}
        
        # Extract DuploCloud token if available
        if platform_context.get("duplo_token"):
            env_vars["DUPLO_TOKEN"] = platform_context.get("duplo_token")
        
        # Extract DuploCloud tenant if available
        if platform_context.get("tenant_name"):
            env_vars["DUPLO_TENANT"] = platform_context.get("tenant_name")
        
        # Extract DuploCloud base URL if available
        if platform_context.get("duplo_base_url"):
            env_vars["DUPLO_HOST"] = f"https://{platform_context.get('duplo_base_url')}"
            
        # Extract DuploCloud plan if available
        if platform_context.get("duplo_plan"):
            env_vars["DUPLO_PLAN"] = platform_context.get("duplo_plan")
            
        return env_vars
    
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
                        "description": "Terminal commands (kubectl, duploctl, or Helm) that will be displayed to the user for approval before execution. The commands you execute if approved by the user will be run by the agent in a non-interactive terminal using subprocess.run. So do not suggest commands which need to be run in an interactive user attached terminal, like: kubectl edit, exec etc here. Suggest those types of commands in the regular content field displayed to the user if needed.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "The complete terminal command string to be executed. Can be kubectl, helm, or duploctl commands."
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "A brief explanation of what this command does."
                                },
                                "files": {
                                    "type": "array",
                                    "description": "Optional. All files that must be created before running this command.",
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
