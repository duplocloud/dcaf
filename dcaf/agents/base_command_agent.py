"""Base class for legacy command-executing agents.

Extracts the shared orchestration flow (invoke → process → call_llm → extract)
that is duplicated across CommandAgent, AWSAgent, and K8sAgent.

Subclasses override:
    - _default_system_prompt()
    - _create_response_schema()
    - process_messages() (if the default is insufficient)
"""

import logging
import os
import subprocess
import traceback
from typing import Any

from dcaf.agent_server import AgentProtocol
from dcaf.llm import BedrockLLM
from dcaf.schemas.messages import AgentMessage, Command, Data, ExecutedCommand

logger = logging.getLogger(__name__)

LEGACY_DEFAULT_MODEL_ID = "anthropic.claude-3-5-sonnet-20240620-v1:0"
LEGACY_MAX_TOKENS = 4000


class BaseCommandAgent(AgentProtocol):
    """Shared base for legacy agents that suggest and execute shell commands."""

    def __init__(self, llm: BedrockLLM, system_prompt: str | None = None):
        self.llm = llm
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.response_schema = self._create_response_schema()

    # ------------------------------------------------------------------
    # Orchestration (shared across all agents)
    # ------------------------------------------------------------------

    def invoke(self, messages: dict[str, list[dict[str, Any]]]) -> AgentMessage:
        """Process messages, execute approved commands, call LLM, return response."""
        processed_messages, executed_commands = self.process_messages(messages)
        llm_response = self.call_llm(processed_messages)
        commands = self._extract_commands(llm_response)

        return AgentMessage(
            content=llm_response.get("content", "I'm unable to provide a response at this time."),
            data=Data(
                cmds=[Command(command=cmd["command"]) for cmd in commands],
                executed_cmds=[
                    ExecutedCommand(command=cmd["command"], output=cmd["output"])
                    for cmd in executed_commands
                ],
            ),
        )

    # ------------------------------------------------------------------
    # LLM invocation (identical across all agents)
    # ------------------------------------------------------------------

    def call_llm(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Call the LLM with processed messages and the response schema."""
        try:
            tool_choice = {"type": "tool", "name": "return_response"}
            model_id = os.getenv("BEDROCK_MODEL_ID", LEGACY_DEFAULT_MODEL_ID)

            response = self.llm.invoke(
                model_id=model_id,
                messages=self.llm.normalize_message_roles(messages),
                max_tokens=LEGACY_MAX_TOKENS,
                system_prompt=self.system_prompt,
                tools=[self.response_schema],
                tool_choice=tool_choice,
            )

            logger.info("LLM Response: %s", response)
            return dict(response) if response else {}
        except Exception as e:
            traceback_error = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error("Error while making LLM API call:\n%s", traceback_error)

            if "ExpiredTokenException" in str(e):
                solution = (
                    "If running the agent locally with Bedrock, refresh the aws creds "
                    "in the .env file (use the env_update_aws_creds.sh script if using "
                    "DuploCloud; refer README)."
                )
                raise Exception(f"Error while making LLM API call: {e}. {solution}") from e
            raise Exception(f"Error while making LLM API call: {e}") from e

    # ------------------------------------------------------------------
    # Command execution (shared by cmd_agent and aws_agent)
    # ------------------------------------------------------------------

    def execute_cmd(self, command: str) -> str:
        """Execute a shell command and return combined stdout/stderr."""
        try:
            logger.info("Executing command: %s", command)
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            output = result.stdout
            if result.stderr:
                if output:
                    output += f"\n\nErrors:\n{result.stderr}"
                else:
                    output = f"Errors:\n{result.stderr}"

            if not output:
                output = "Command executed successfully with no output."

            return output
        except Exception as e:  # Intentional catch-all: subprocess can raise many types
            logger.error("Error executing command: %s", e)
            return f"Error executing command: {e}"

    # ------------------------------------------------------------------
    # Command extraction (shared by cmd_agent and aws_agent)
    # ------------------------------------------------------------------

    def _extract_commands(self, llm_response: dict[str, Any]) -> list[dict[str, str]]:
        """Extract terminal_commands from the LLM response."""
        return llm_response.get("terminal_commands", [])

    # ------------------------------------------------------------------
    # Abstract hooks — subclasses must override
    # ------------------------------------------------------------------

    def _default_system_prompt(self) -> str:
        """Return the default system prompt. Override in subclasses."""
        raise NotImplementedError

    def _create_response_schema(self) -> dict[str, Any]:
        """Return the response tool schema. Override in subclasses."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Default process_messages (used by cmd_agent, overridden by others)
    # ------------------------------------------------------------------

    def process_messages(
        self, messages: dict[str, list[dict[str, Any]]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Process raw messages, executing approved commands from the latest message."""
        processed_messages: list[dict[str, Any]] = []
        executed_cmds: list[dict[str, str]] = []
        messages_list = messages.get("messages", [])

        for msg in messages_list:
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue

            processed_msg = {"role": role, "content": msg.get("content", "")}

            if role == "user":
                data = msg.get("data", {})

                # Execute approved commands only from the latest message
                if "cmds" in data and msg == messages_list[-1]:
                    for cmd in data["cmds"]:
                        if cmd.get("execute", False):
                            logger.info("Executing approved command: %s", cmd["command"])
                            output = self.execute_cmd(cmd["command"])
                            executed_cmds.append({"command": cmd["command"], "output": output})
                            processed_msg["content"] += (
                                f"\n\nExecuted command: {cmd['command']}\nOutput: {output}"
                            )

                # Include previously executed commands
                for cmd in data.get("executed_cmds", []):
                    executed_cmds.append(cmd)
                    processed_msg["content"] += (
                        f"\n\nPreviously executed: {cmd['command']}\nOutput: {cmd['output']}"
                    )

            processed_messages.append(processed_msg)

        return processed_messages, executed_cmds
