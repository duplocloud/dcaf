import json

import logging
import traceback

import subprocess
import os
import base64
import tempfile
import shutil
from typing import List, Dict, Any, Optional

from agent_server import AgentProtocol
from schemas.messages import AgentMessage, Command, ExecutedCommand, Data
from llm import BedrockLLM

logger = logging.getLogger(__name__)

class K8sAgent(AgentProtocol):
    """
    An agent that processes user messages, executes terminal commands with user approval,
    and uses an LLM to generate responses and suggest commands.
    """
    
    def __init__(self, llm: BedrockLLM, system_prompt: Optional[str] = None):
        """
        Initialize the CommandAgent with an LLM instance and optional custom system prompt.
        
        Args:
            llm: An instance of BedrockLLM for generating responses
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
                    # execute approved commands
                    for c in data.get("cmds", []):
                        if c.get("execute", False):
                            cmd_str = c.get("command", "")
                            logger.info("Executing approved command: %s", cmd_str)
                            files = c.get("files")

                            duplo_base_url = platform_context.get("duplo_base_url", None)
                            
                            if duplo_base_url and duplo_base_url.startswith("https://") == False:
                                duplo_base_url = "https://" + duplo_base_url

                            ctl_tokens = {
                                "DUPLO_HOST": duplo_base_url,
                                "DUPLO_TOKEN": platform_context.get("duplo_token", None),
                                "DUPLO_TENANT": platform_context.get("tenant_name", None)
                                }
                            
                            output = self.execute_cmd(cmd_str, kubeconfig_path, files, ctl_tokens)
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
            
            # Invoke the LLM with the messages, system prompt, and response schema
            model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")
            # model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
            # model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
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
    
    def execute_cmd(self, command: str, kubeconfig_path: Optional[str] = None, files: Optional[List[Dict[str, str]]] = None, ctl_tokens: Optional[Dict[str, str]] = None) -> str:
        """
        Execute a terminal command and return its output.
        
        Args:
            command: The command string to execute
            
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

            if ctl_tokens:
                env["DUPLO_HOST"] = ctl_tokens.get("DUPLO_HOST", None)  
                env["DUPLO_TOKEN"] = ctl_tokens.get("DUPLO_TOKEN", None)
                env["DUPLO_TENANT"] = ctl_tokens.get("DUPLO_TENANT", None)
                # Log the DuploCloud environment variables at INFO level (token redacted for security)
                if logger.isEnabledFor(logging.INFO):
                    redacted_token = None
                    token_val = ctl_tokens.get("DUPLO_TOKEN")
                    if token_val:
                        redacted_token = token_val[:4] + "…" + token_val[-4:] if len(token_val) > 8 else "***"
                    logger.info(
                        "Set DuploCloud env vars: DUPLO_HOST=%s, DUPLO_TENANT=%s, DUPLO_TOKEN=%s",
                        env.get("DUPLO_HOST"),
                        env.get("DUPLO_TENANT"),
                        redacted_token,
                    )

            if kubeconfig_path:
                env["KUBECONFIG"] = kubeconfig_path
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
            # Log the output of the executed command at INFO level so it is visible in logs
            logger.info("Command output: %s", output)
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

    def _duplocloud_context(self) -> str:
        """
        Return the DuploCloud context for the LLM.
        
        Returns:
            The DuploCloud context string
        """

        duplocloud_concepts_context = """
# 📚 DuploCloud Concepts Cheat-Sheet

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
        return f"""You are a seasoned Kubernetes and Helm expert agent for DuploCloud. 
Your role is to help users manage, troubleshoot, and deploy applications using kubectl commands and Helm in a less wordy manner.
Be throrough and perform in-depth analysis and run all the necessary terminal commands needed to collect the necessary information when investigating an issue (by suggesting them in the 'terminal_commands' field).
Always be extremely critical and ask clarifying questions when needed.

Terminal Command Capability:
- You can suggest terminal commands to the user using the 'terminal_commands' field. 
- Always specify the namespace when running kubectl commands.
- These will be shown in an approval box to the user below the text in the 'content' field, and if approved by the user they will be executed in a non-interactive terminal using subprocess.run.
- The commands will be executed using subprocess.run exactly as suggested, so do not suggest terminal commands with palceholders in them. If you need to know the values of placeholders, ask the user to provide them first and then suggest the correct exact commands using the 'terminal_commands' field.
- If you can run a terminal command always suggest it in the 'terminal_commands' field. Suggest commands in the 'content' field only if it is a terminal command that needs to be run in a user attached interactive terminal.


DuploCloud Concepts Context: {self._duplocloud_context()}

## Expertise Areas
- Kubernetes resource management and troubleshooting
- Helm chart creation and deployment
- Docker Compose to Helm chart conversion
- DuploCloud-specific Kubernetes configurations

## Kubectl Command Guidelines
- Be specific about namespaces
- Choose efficient commands to diagnose or solve problems
- Consider cluster impact and resource constraints
- Format commands properly with appropriate flags
- The commands you suggest will be displayed to the user for approval before execution. If approved by the user, the commands will be run by the agent in a non-interactive terminal using subprocess.run. So do not suggest any commands which need to be run in a persistent, interactive user attached terminal, like: kubectl edit, exec etc in the 'terminal_commands' field. Suggest those types of commands in the regular 'content' field displayed to the user if needed and leave the 'terminal_commands' field empty.

## Helm Operation Guidelines
- If a user asks to convert a Docker Compose file to a Helm chart, ask the user for the name to use for the helm chart
- Follow Helm best practices for chart structure
- Use values.yaml for configurable elements
- Include proper labels and annotations
- Create reusable and maintainable templates

## Docker Compose Conversion Guidelines
When converting Docker Compose to Helm:
1. Map services to appropriate Kubernetes resources
2. Convert volumes to PersistentVolumeClaims
3. Handle networking through Services and Ingresses
4. Create a complete chart structure with all necessary files
5. Remember that users will approve commands before execution, and files for Helm operations will be created temporarily and removed after command execution.

## Rollback Guidelines
- If the user asks to rollback a service, ask the user for the name of the service to rollback
- If the user asks to list the services, list the services with this command: `duploctl service list | jq -r '.[].Name'`. Format the output as a markdown table with the following columns: `Service #`, `Service Name`. The service # is just the index (starting from 1) of the service in the list. The service name is the name of the service as shown in the list.
- To get a list of the previous revisions of a service, use this command: `duploctl service find <SERVICE> -q ContainerImageHistory`. Replace <SERVICE> with the name of the service provided by the user. Format the output as a markdown table with the following columns: `Revision #`, `Image Url`, `Timestamp`. Revision # is just the index (starting from 1) of the revision in the list. Don't show a list of revisions, until the system gives you the list of revisions.
- To rollback the service to a previous revision, use this command: `duploctl service rollback <SERVICE> --to-revision <REVISION>`. Replace <SERVICE> with the name of the service provided by the user and <REVISION> with the revision number provided by the user.
- More context for rollbacks, when listing the previous revisions of a service, the first one is always the currently deployed revision, when possible note this in conversation or when presenting the list of revisions.

## Conversation Approach
- Be concise and to the point
- Maintain context from previous interactions
- Reference command outputs shared by the user
- Explain the reasoning behind your suggestions
- Do not execute the same command again and again for no reason
- Ask clarifying questions when needed
"""
    
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
