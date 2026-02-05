"""AWS CLI agent — suggests and executes AWS CLI commands."""

import logging
from typing import Any

from dcaf.agents.base_command_agent import BaseCommandAgent

logger = logging.getLogger(__name__)


class AWSAgent(BaseCommandAgent):
    """Agent that suggests and executes AWS CLI commands with DuploCloud context."""

    def process_messages(
        self, messages: dict[str, list[dict[str, Any]]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Process messages with full history awareness and rejection tracking."""
        processed_messages: list[dict[str, Any]] = []
        executed_cmds_current_turn: list[dict[str, str]] = []
        messages_list = messages.get("messages", [])

        for idx, msg in enumerate(messages_list):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue

            content = msg.get("content", "")
            data = msg.get("data", {}) if role == "user" else {}

            if role == "user":
                # Append context for user-executed commands
                for uc in data.get("executed_cmds", []):
                    cmd = uc.get("command", "")
                    out = uc.get("output", "")
                    content += f"\n\nI ran this command in my terminal: {cmd}\nOutput:\n{out}"

                # Append any rejections
                for c in data.get("cmds", []):
                    reason = c.get("rejection_reason")
                    if reason:
                        content += f"\n\nI rejected the suggested command: {c.get('command', '')}\nReason: {reason}"

                # Execute approved commands only in the latest user message
                is_latest_user_msg = idx == len(messages_list) - 1
                if is_latest_user_msg:
                    for c in data.get("cmds", []):
                        if c.get("execute", False):
                            cmd_str = c.get("command", "")
                            logger.info("Executing approved command: %s", cmd_str)
                            output = self.execute_cmd(cmd_str)
                            executed_cmds_current_turn.append({"command": cmd_str, "output": output})
                            content += f"\n\nExecuted command: {cmd_str}\nOutput:\n{output}"

            processed_messages.append({"role": role, "content": content})

        return processed_messages, executed_cmds_current_turn

    def _duplocloud_context(self) -> str:
        return """
# DuploCloud AWS Concepts Cheat-Sheet

## AWS Resources in DuploCloud
- **DuploCloud Infrastructure** = AWS account with VPC, subnets, security groups, etc. managed by DuploCloud.
- **DuploCloud Tenant** = Logical isolation within an Infrastructure, maps to isolated AWS resources.

## Common AWS Resource Types
- **EC2 Instances** = Virtual machines running in AWS.
- **S3 Buckets** = Object storage for files and data.
- **RDS Databases** = Managed relational databases.
- **Lambda Functions** = Serverless compute functions.
- **IAM Roles/Policies** = Access management for AWS resources.
- **CloudWatch** = Monitoring and logging service.

### Key takeaway
When users ask about AWS resources in DuploCloud, they're typically referring to resources provisioned through the DuploCloud platform, which abstracts some of the underlying AWS complexity.
"""

    def _default_system_prompt(self) -> str:
        return (
            "You are a seasoned AWS CLI expert agent for DuploCloud. "
            "Help users troubleshoot and operate AWS resources concisely.\n\n"
            "DuploCloud AWS Concepts Context:\n"
            + self._duplocloud_context()
            + "\n\n"
            "Guidelines:\n"
            "1. Suggest precise, safe AWS CLI commands. \n"
            "2. Keep answers short and actionable.\n"
            "3. Always use the structured `return_response` tool.\n"
            "4. Respect any commands the user already ran or rejected.\n"
        )

    def _create_response_schema(self) -> dict[str, Any]:
        return {
            "name": "return_response",
            "description": "Generate a structured response with explanatory text and AWS CLI commands",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The main response text to display to the user. Should provide a clear explanation.",
                    },
                    "terminal_commands": {
                        "type": "array",
                        "description": (
                            "AWS CLI commands that will be displayed to the user for approval "
                            "before execution. The commands you execute if approved by the user "
                            "will be run by the agent in a non-interactive terminal using "
                            "subprocess.run. So do not suggest commands which need to be run in "
                            "an interactive user attached terminal. Focus on AWS CLI commands "
                            "like 'aws ec2 describe-instances', 'aws s3 ls', etc."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "The complete AWS CLI command string to be executed.",
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "A brief explanation of what this AWS CLI command does.",
                                },
                            },
                            "required": ["command"],
                        },
                    },
                },
                "required": ["content"],
            },
        }
