"""
Vertex AI LLM implementation using the Google GenAI SDK.
https://googleapis.github.io/python-genai/

Provides a sync interface for calling Gemini models on Vertex AI,
mirroring the BedrockLLM class for AWS Bedrock.
"""

import logging
import os
import time
from typing import Any

from google import genai
from google.genai import types

from dcaf.llm.base import LLM

logger = logging.getLogger(__name__)


class VertexLLM(LLM):
    """
    A class for interacting with Vertex AI models using the Google GenAI SDK.
    Provides a consistent interface mirroring BedrockLLM.
    """

    def __init__(
        self,
        project_id: str | None = None,
        location: str | None = None,
    ):
        """
        Initialize the VertexLLM client.

        Args:
            project_id: GCP project ID. Falls back to GOOGLE_CLOUD_PROJECT env var,
                        then auto-detection via ADC / metadata service.
            location: GCP region for Vertex AI. Falls back to DCAF_GOOGLE_MODEL_LOCATION
                      env var, then defaults to 'us-central1'.
        """
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = (
            location
            or os.getenv("DCAF_GOOGLE_MODEL_LOCATION")
            or "us-central1"
        )

        logger.info(
            f"Initializing Vertex AI client (project={self.project_id}, location={self.location})"
        )

        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location,
        )

    def invoke(
        self,
        messages: list[dict[str, Any]],
        model_id: str,
        max_tokens: int = 1000,
        temperature: float = 0.0,
        system_prompt: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs,  # noqa: ARG002
    ) -> dict[str, Any]:
        """
        Invoke a Vertex AI model using the Google GenAI SDK.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model_id: Vertex AI model ID (e.g., 'gemini-2.0-flash').
            max_tokens: Maximum number of tokens to generate.
            temperature: Controls randomness (0-1).
            system_prompt: Optional system prompt.
            tools: Optional list of tool specs (same schema as BedrockLLM).
            tool_choice: Tool choice strategy. Supports:
                         - 'auto': Model decides whether to call a tool
                         - 'any': Model must call a tool
                         - {'type': 'tool', 'name': 'X'}: Model must call tool X
                         - {'name': 'X'}: Shorthand, model must call tool X
            **kwargs: Additional parameters for compatibility.

        Returns:
            Dict with normalized response matching the structure expected by callers:
            {
                "output": {
                    "message": {
                        "content": [
                            {"text": "..."} or {"toolUse": {"name": ..., "input": ...}}
                        ]
                    }
                },
                "stopReason": "end_turn" | "tool_use",
                "usage": {...}
            }
        """
        logger.info(f"Invoking Vertex AI model {model_id}")
        logger.debug(f"Messages: {messages}")

        # Build contents
        contents = self._format_messages(messages)

        # Build config
        config_kwargs: dict[str, Any] = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt

        # Add tools
        if tools:
            config_kwargs["tools"] = [self._format_tools(tools)]
            config_kwargs["tool_config"] = self._format_tool_choice(tool_choice)
            # Disable auto-execution so we get raw function calls back
            config_kwargs["automatic_function_calling"] = (
                types.AutomaticFunctionCallingConfig(disable=True)
            )

        config = types.GenerateContentConfig(**config_kwargs)

        start_time = time.perf_counter()

        response = self.client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )

        elapsed = time.perf_counter() - start_time
        logger.info(f"Vertex AI model {model_id} call completed in {elapsed:.2f} seconds")
        logger.debug(f"Response: {response}")

        return self._normalize_response(response)

    def _format_messages(self, messages: list[dict[str, Any]]) -> list[types.Content]:
        """Convert message dicts to google-genai Content objects."""
        contents = []
        for msg in messages:
            role = msg["role"]
            # Vertex AI uses "user" and "model" (not "assistant")
            if role == "assistant":
                role = "model"
            content = msg.get("content", "")
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=content)],
                )
            )
        return contents

    def _format_tools(self, tools: list[dict[str, Any]]) -> types.Tool:
        """Convert tool specs (BedrockLLM schema format) to google-genai Tool."""
        declarations = []
        for tool in tools:
            schema = tool.get("input_schema", tool.get("parameters", {}))
            declarations.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    parameters_json_schema=schema,
                )
            )
        return types.Tool(function_declarations=declarations)

    def _format_tool_choice(
        self, tool_choice: str | dict[str, Any] | None
    ) -> types.ToolConfig:
        """Convert tool_choice to google-genai ToolConfig."""
        if tool_choice is None or tool_choice == "auto":
            return types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        if tool_choice == "any":
            return types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="ANY")
            )

        # Specific tool: {'name': 'X'} or {'type': 'tool', 'name': 'X'}
        if isinstance(tool_choice, dict) and "name" in tool_choice:
            return types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[tool_choice["name"]],
                )
            )

        # Fallback
        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO")
        )

    def _normalize_response(self, response: Any) -> dict[str, Any]:
        """
        Normalize Vertex AI response to match the structure callers expect.

        Returns a dict matching Bedrock Converse API shape so callers
        (like SlackResponseRouter) can use the same parsing logic.
        """
        content_blocks = []
        has_tool_use = False

        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call:
                    has_tool_use = True
                    content_blocks.append({
                        "toolUse": {
                            "name": part.function_call.name,
                            "input": dict(part.function_call.args) if part.function_call.args else {},
                        }
                    })
                elif part.text:
                    content_blocks.append({"text": part.text})

        usage = {}
        if response.usage_metadata:
            usage = {
                "inputTokens": response.usage_metadata.prompt_token_count or 0,
                "outputTokens": response.usage_metadata.candidates_token_count or 0,
                "totalTokens": response.usage_metadata.total_token_count or 0,
            }

        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": content_blocks,
                }
            },
            "stopReason": "tool_use" if has_tool_use else "end_turn",
            "usage": usage,
        }
