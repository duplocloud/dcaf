"""
Slack Response Router Module

This module determines whether a bot should respond to messages in a Slack thread
or remain silent. It uses an LLM to analyze the conversation context and make
intelligent decisions about when the bot should engage.
"""

import logging
import os
import traceback
from typing import Any

from .llm import LLM, BedrockLLM, VertexLLM

logger = logging.getLogger(__name__)

# Env var names
_ENV_PROVIDER = "DCAF_PROVIDER"
_ENV_SILENCE_MODEL = "DCAF_SILENCE_MODEL_ID"

# Provider defaults
_DEFAULT_PROVIDER = "bedrock"
_PROVIDER_MODEL_DEFAULTS = {
    "bedrock": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
    "google": "gemini-2.0-flash",
}


def _create_llm_from_env() -> tuple[LLM, str]:
    """Create an LLM client and resolve model ID from environment variables."""
    provider = os.getenv(_ENV_PROVIDER, _DEFAULT_PROVIDER).lower()
    model_id = os.getenv(_ENV_SILENCE_MODEL) or _PROVIDER_MODEL_DEFAULTS.get(provider, "")

    if provider == "google":
        return VertexLLM(), model_id
    else:
        return BedrockLLM(), model_id


class ChannelResponseRouter:
    """
    Generic class which will be inheritied by subclasses for various channel routers.
    """

    def should_agent_respond(self, *args: Any, **kwargs: Any) -> Any:
        pass


class SlackResponseRouter(ChannelResponseRouter):
    """
    A router that decides whether a bot should respond to Slack messages.

    This class uses an LLM to analyze conversation context and determine if
    the bot should engage or remain silent based on the conversation flow.
    """

    def __init__(
        self,
        llm_client: LLM | None = None,
        agent_name: str = "Assistant",
        agent_description: str = "",
        model_id: str | None = None,
    ):
        """
        Initialize the Slack Response Router.

        Args:
            llm_client: LLM instance. If None, auto-created from DCAF_PROVIDER env var.
            agent_name: The name of the agent for context in decision making
            agent_description: The description of the agent for context in decision making
            model_id: Model ID override. If None, uses DCAF_SILENCE_MODEL_ID env var
                      or provider default.
        """
        if llm_client is not None:
            self.llm_client = llm_client
            self.model_id = model_id
        else:
            self.llm_client, default_model = _create_llm_from_env()
            self.model_id = model_id or default_model
        self.agent_name = agent_name
        self.agent_description = agent_description

    def _get_system_prompt(self) -> str:
        """
        Get the system prompt for the LLM to make response decisions.

        Returns:
            A system prompt that instructs the LLM on how to decide whether to respond
        """
        return f"""You are a decision-making assistant for a Slack bot named "{self.agent_name}".

Your job is to analyze Slack thread messages and decide whether the bot should respond or remain silent.

AGENT INFO:
{self.agent_description}

DECISION CRITERIA:
1. RESPOND when:
   - The bot is directly mentioned (@{self.agent_name} or similar)
   - Asks for clarification on this agent's previous response
   - Reports an error with this agent's suggestion
   - Is a follow-up request like "also can you..." or "now do..."
   - Contains question words (what, how, why, can you, etc.) directed at this agent
   - Is a direct question immediately after this agent responded
   - Someone asks a direct question that the bot can help with

2. REMAIN SILENT when:
   - Is just acknowledgment ("thanks", "got it", "ok")
   - Shifts to a different topic outside this agent's domain
   - Tags a different agent (@other-agent)
   - Is conversation between humans (no questions for the agent)
   - Is off-topic chitchat or side discussion
   - People are having casual conversation or small talk
   - The discussion is personal or private in nature
   - The topic is outside the bot's domain of expertise

DEFAULT: When in doubt, choose to REMAIN SILENT. It's better to miss a response than to spam the thread.
Focus primarily on the LATEST message, but use thread context to understand if this agent was recently active.
"""

    def _format_slack_messages(self, slack_messages: list[dict[str, Any]]) -> str:
        """
        Convert Slack messages to LLM-compatible format.

        Args:
            slack_messages: List of Slack messages with keys like 'user', 'text', 'timestamp'

        Returns:
            Formatted string for LLM consumption
        """
        formatted_conversation = ""

        for msg in slack_messages:
            # Extract relevant information from Slack message
            if msg.get("role") == "user":
                user_info = msg.get("user", {})
                user = (
                    user_info.get("name", "Unknown User")
                    if isinstance(user_info, dict)
                    else "Unknown User"
                )
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")

                # Format as a user message for the LLM
                formatted_content = f"[{user}]: {content}"
                if timestamp:
                    formatted_content = f"[{timestamp}] {formatted_content}"

                formatted_conversation += formatted_content + "\n"

            elif msg.get("role") == "assistant":
                assistant_info = msg.get("assistant", {})
                assistant = (
                    assistant_info.get("name", "Assistant")
                    if isinstance(assistant_info, dict)
                    else "Assistant"
                )
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")

                # Format as an assistant message for the LLM
                formatted_content = f"[{assistant}]: {content}"
                if timestamp:
                    formatted_content = f"[{timestamp}] {formatted_content}"

                formatted_conversation += formatted_content + "\n"

        return formatted_conversation

    def should_agent_respond(
        self, slack_thread: str | list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Determines if a DuploCloud agent should respond to the latest message in a Slack thread.

        Args:
            slack_thread: Slack thread as a string or list of message dicts
                          with 'role' and 'content' keys.

        Returns:
            dict: {"should_respond": bool, "reasoning": str}
        """
        if isinstance(slack_thread, list):
            slack_thread = self._format_slack_messages(slack_thread)

        # Tool schema for structured response
        routing_tool = {
            "name": "slack_routing_decision",
            "description": "Make a decision about whether the agent should respond to the latest Slack message",
            "input_schema": {
                "type": "object",
                "properties": {
                    "should_respond": {
                        "type": "boolean",
                        "description": "True if the agent should respond in the thread, False if it should stay silent",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Brief 1 sentence explanation for the decision if should_respond is True. If should_respond is False, this field MUST be empty.",
                    },
                },
                "required": ["should_respond"],
            },
        }

        system_prompt = self._get_system_prompt()

        # Prepare messages for LLM
        messages = [
            {
                "role": "user",
                "content": f"Here is the complete Slack thread:\n\n{slack_thread}\n\nShould the agent respond to the latest message?",
            }
        ]

        try:
            # Call LLM with forced tool use
            response = self.llm_client.invoke(
                messages=messages,
                model_id=self.model_id,
                system_prompt=system_prompt,
                tools=[routing_tool],
                tool_choice={"type": "tool", "name": "slack_routing_decision"},
                max_tokens=200,
                temperature=0.0,
            )

            logger.info("Slack Channel Router LLM Response: %s", response)

            if isinstance(response, str):
                if response == "1":
                    return {
                        "should_respond": True,
                        "reasoning": "Agent should respond to the latest message",
                    }
                else:
                    return {
                        "should_respond": False,
                        "reasoning": "Agent should not respond to the latest message",
                    }

            else:
                # Extract tool use input from Bedrock Converse API response format
                tool_use_input = response["output"]["message"]["content"][0]["toolUse"]["input"]
                return {
                    "should_respond": tool_use_input.get("should_respond", False),
                    "reasoning": tool_use_input.get("reasoning", "No reasoning provided"),
                }

        except Exception as e:
            # Fail safe - default to not responding if router fails
            # Log the entire error stack trace
            logger.error("Stack trace: %s", traceback.format_exc())
            return {"should_respond": False, "reasoning": f"Router error: {str(e)}"}
