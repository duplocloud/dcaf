"""Terminal command agent — suggests and executes shell commands."""

from typing import Any

from dcaf.agents.base_command_agent import BaseCommandAgent


class CommandAgent(BaseCommandAgent):
    """Agent that suggests and executes general terminal commands."""

    def _default_system_prompt(self) -> str:
        return """
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
        """

    def _create_response_schema(self) -> dict[str, Any]:
        return {
            "name": "return_response",
            "description": "Generate a structured response with explanatory text and terminal commands",
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The main response text to display to the user. Should provide a clear explanation.",
                    },
                    "terminal_commands": {
                        "type": "array",
                        "description": "Terminal commands that will be displayed to the user for approval before execution.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "command": {
                                    "type": "string",
                                    "description": "The complete terminal command string to be executed.",
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "A brief explanation of what this command does.",
                                },
                            },
                            "required": ["command"],
                        },
                    },
                },
                "required": ["content"],
            },
        }
