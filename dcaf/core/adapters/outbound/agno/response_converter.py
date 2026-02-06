"""
Response converter for Agno SDK outputs.

This module handles conversion from Agno's RunOutput and streaming events
to DCAF's AgentResponse and StreamEvent formats.

Responsibilities:
- Extract text content from Agno's various content formats
- Extract tool calls from Agno's tool execution results
- Handle metrics extraction
- Convert streaming events to DCAF format
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from agno.run.agent import RunStatus

from ....application.dto.responses import (
    AgentResponse,
    DataDTO,
    StreamEvent,
    StreamEventType,
    ToolCallDTO,
)

logger = logging.getLogger(__name__)


@dataclass
class AgnoMetrics:
    """Metrics from an Agno run."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration: float = 0.0
    time_to_first_token: float | None = None
    response_timer: float | None = None


class AgnoResponseConverter:
    """
    Converts Agno SDK outputs to DCAF response formats.

    This class handles all the complexity of extracting content from Agno's
    various response formats, including:
    - Text content (plain strings or structured content blocks)
    - Tool calls with approval status
    - Streaming events
    - Metrics
    """

    def extract_metrics(self, run_output: Any) -> AgnoMetrics | None:
        """
        Extract metrics from Agno's RunOutput.

        Args:
            run_output: The RunOutput from Agno

        Returns:
            AgnoMetrics or None if no metrics available
        """
        if not hasattr(run_output, "metrics") or not run_output.metrics:
            return None

        m = run_output.metrics
        return AgnoMetrics(
            input_tokens=getattr(m, "input_tokens", 0) or 0,
            output_tokens=getattr(m, "output_tokens", 0) or 0,
            total_tokens=getattr(m, "total_tokens", 0) or 0,
            duration=getattr(m, "duration", 0.0) or 0.0,
            time_to_first_token=getattr(m, "time_to_first_token", None),
            response_timer=getattr(m, "response_timer", None),
        )

    def convert_run_output(
        self,
        run_output: Any,
        conversation_id: str,
        metrics: AgnoMetrics | None = None,  # noqa: ARG002
        tracing_context: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """
        Convert Agno's RunOutput to our AgentResponse.

        Args:
            run_output: The RunOutput from Agno
            conversation_id: ID for this conversation
            metrics: Optional extracted metrics (currently unused but kept for API compatibility)
            tracing_context: Optional tracing context to include in response metadata

        Returns:
            AgentResponse with appropriate fields set
        """
        text = self._extract_text_content(run_output)
        tool_calls, has_pending = self._extract_tool_calls(run_output)

        # Check if run is paused
        is_paused = getattr(run_output, "status", None) == RunStatus.paused
        if is_paused:
            has_pending = True

        # Determine completeness
        is_complete = getattr(run_output, "status", None) == RunStatus.completed and not has_pending

        # Wrap tool calls in DataDTO (AgentResponse expects data, not tool_calls)
        data = DataDTO(tool_calls=tool_calls)

        # Build metadata with tracing context
        response_metadata = self._build_response_metadata(tracing_context)

        return AgentResponse(
            conversation_id=conversation_id,
            text=text,
            data=data,
            has_pending_approvals=has_pending,
            is_complete=is_complete,
            metadata=response_metadata,
        )

    def convert_stream_event(self, agno_event: Any) -> StreamEvent | None:
        """
        Convert an Agno streaming event to our StreamEvent format.

        Args:
            agno_event: An event from Agno's streaming run

        Returns:
            StreamEvent or None if event should be skipped
        """
        event_type = type(agno_event).__name__

        if event_type in ("RunContentEvent", "RunContent"):
            content = getattr(agno_event, "content", "")
            if content:
                return StreamEvent.text_delta(str(content))
            return None

        elif event_type in ("RunStartedEvent", "RunStarted"):
            return None  # Already sent message_start

        elif event_type in ("RunCompletedEvent", "RunCompleted"):
            return None  # Handled via run_output

        elif event_type in ("RunErrorEvent", "RunError"):
            error_msg = getattr(agno_event, "error", "Unknown error")
            return StreamEvent.error(str(error_msg))

        elif event_type in ("ToolCallStartedEvent", "ToolCallStarted"):
            tool_name = getattr(agno_event, "tool_name", "")
            tool_id = getattr(agno_event, "tool_call_id", "")
            return StreamEvent.tool_use_start(
                tool_call_id=tool_id,
                tool_name=tool_name,
            )

        elif event_type in ("ToolCallCompletedEvent", "ToolCallCompleted"):
            return StreamEvent(
                event_type=StreamEventType.TOOL_USE_END,
                index=0,
            )

        elif event_type in ("ReasoningStartedEvent", "ReasoningStarted"):
            return StreamEvent(
                event_type=StreamEventType.REASONING_STARTED,
                data={},
            )

        elif event_type in ("ReasoningStepEvent", "ReasoningStep"):
            content = getattr(agno_event, "content", "")
            return StreamEvent(
                event_type=StreamEventType.REASONING_STEP,
                data={"content": content},
            )

        elif event_type in ("ReasoningCompletedEvent", "ReasoningCompleted"):
            return StreamEvent(
                event_type=StreamEventType.REASONING_COMPLETED,
                data={},
            )

        return None

    def _extract_text_content(self, run_output: Any) -> str | None:
        """
        Extract text content from Agno's RunOutput.

        Prefers extracting from the last assistant message in run_output.messages
        to avoid concatenated intermediate content (e.g., thinking tags from
        multi-turn tool-calling workflows).

        Handles various content formats:
        - Last assistant message from messages list (preferred)
        - Plain strings
        - JSON-serialized content blocks
        - Structured content objects

        Args:
            run_output: The RunOutput from Agno

        Returns:
            Extracted text or None
        """
        text = None

        # PREFERRED: Extract from the last assistant message to avoid
        # concatenated intermediate content (like <search_quality_reflection> tags)
        text = self._extract_from_last_assistant_message(run_output)

        # Fallback: Try Agno's built-in method
        if text is None and hasattr(run_output, "get_content_as_string"):
            text = self._extract_via_get_content_as_string(run_output)

        # Fallback: direct content access
        if text is None and hasattr(run_output, "content") and run_output.content:
            text = self._extract_via_direct_content(run_output)

        # Debug logging for content inspection
        self._log_content_debug(run_output)

        # WORKAROUND: Strip trailing [] if present (temporary fix for Agno bug)
        text = self._strip_trailing_brackets(text)

        return text


    def _extract_from_last_assistant_message(self, run_output: Any) -> str | None:
        """
        Extract text from the last assistant message in run_output.messages.

        This is the preferred extraction method because run_output.content may contain
        concatenated content from all assistant turns in a multi-turn tool-calling
        workflow, including intermediate "thinking" content like:
        - <search_quality_reflection>...</search_quality_reflection>
        - <search_quality_score>...</search_quality_score>
        - <thinking>...</thinking>

        By extracting from the last assistant message, we get only the final clean
        response without intermediate reasoning artifacts.

        Args:
            run_output: The RunOutput from Agno

        Returns:
            Text content from the last assistant message, or None if not available
        """
        if not hasattr(run_output, "messages") or not run_output.messages:
            return None

        # Find the last assistant message
        last_assistant_msg = None
        for msg in reversed(run_output.messages):
            role = getattr(msg, "role", None)
            # Handle both string roles and enum roles
            role_str = role.value if hasattr(role, "value") else str(role) if role else ""
            if role_str.lower() == "assistant":
                last_assistant_msg = msg
                break

        if not last_assistant_msg:
            logger.debug("No assistant message found in run_output.messages")
            return None

        # Extract content from the message
        content = getattr(last_assistant_msg, "content", None)
        if content is None:
            return None

        # Handle different content types
        if isinstance(content, str):
            logger.debug(f"Extracted text from last assistant message: {repr(content)[:200]}")
            return content
        elif isinstance(content, list):
            # Content blocks format
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" or "text" in block:
                        text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
                elif hasattr(block, "text"):
                    text_parts.append(str(block.text))
            if text_parts:
                result = " ".join(text_parts)
                logger.debug(f"Extracted text from last assistant message blocks: {repr(result)[:200]}")
                return result
        elif hasattr(content, "text"):
            return str(content.text)

        return None

    def _extract_via_get_content_as_string(self, run_output: Any) -> str | None:
        """Extract text using Agno's get_content_as_string method."""
        try:
            raw_content = run_output.get_content_as_string()
            logger.debug(f"Agno get_content_as_string() returned: {repr(raw_content)[:200]}")

            if not raw_content:
                return None

            # If it starts with [ or {, it's JSON-serialized structured content
            if raw_content.startswith("[") or raw_content.startswith("{"):
                return self._parse_json_content(raw_content)
            else:
                # Plain text content
                return str(raw_content)

        except Exception as e:
            logger.warning(f"Agno get_content_as_string() failed: {e}")
            return None

    def _parse_json_content(self, raw_content: str) -> str | None:
        """Parse JSON-formatted content and extract text."""
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, list):
                # Extract text from content blocks
                text_parts = []
                for block in parsed:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                return " ".join(text_parts) if text_parts else None
            elif isinstance(parsed, dict) and "text" in parsed:
                return str(parsed["text"])
            else:
                # Not a recognized format
                return None
        except json.JSONDecodeError:
            # Not valid JSON, use as-is
            return raw_content

    def _extract_via_direct_content(self, run_output: Any) -> str | None:
        """Extract text by directly accessing the content attribute."""
        logger.debug("Agno: Falling back to direct content access")

        content = run_output.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            return self._extract_from_content_list(content)
        elif hasattr(content, "text"):
            return str(content.text)

        return None

    def _extract_from_content_list(self, content: list) -> str | None:
        """Extract text from a list of content blocks."""
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" or "text" in block:
                    text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
            elif hasattr(block, "text"):
                text_parts.append(str(block.text))
        return " ".join(text_parts) if text_parts else None

    def _strip_trailing_brackets(self, text: str | None) -> str | None:
        """Strip trailing [] from text (workaround for Agno bug)."""
        if not text:
            return text

        if text.endswith("[]"):
            logger.warning("Stripping trailing '[]' from content")
            text = text[:-2]

        # Also handle cases where [] appears with whitespace before it
        if text and text.rstrip().endswith("[]"):
            text = text.rstrip()[:-2].rstrip()

        return text

    def _log_content_debug(self, run_output: Any) -> None:
        """Log detailed debug information about run_output content."""
        raw_content = getattr(run_output, "content", None)
        logger.info(f"run_output.content TYPE: {type(raw_content)}")
        logger.info(f"run_output.content REPR: {repr(raw_content)[:500]}")

        if raw_content is not None:
            logger.info(f"run_output.content ID: {id(raw_content)}")
            if hasattr(raw_content, "__class__"):
                logger.info(
                    f"run_output.content CLASS: {raw_content.__class__.__module__}.{raw_content.__class__.__name__}"
                )
            if hasattr(raw_content, "__dict__"):
                logger.info(f"run_output.content __dict__: {raw_content.__dict__}")
            # Check if it's a string that was built from concatenation
            if isinstance(raw_content, str) and "[]" in raw_content:
                logger.warning("CONTENT IS STRING WITH []: checking if it ends with []")
                logger.warning(f"Last 10 chars: {repr(raw_content[-10:])}")
                logger.warning(f"Content endswith '[]': {raw_content.endswith('[]')}")

        # Also log other potentially relevant attributes
        for attr in ("images", "videos", "audio", "files"):
            if hasattr(run_output, attr):
                logger.info(f"run_output.{attr}: {getattr(run_output, attr)}")

    def _extract_tool_calls(self, run_output: Any) -> tuple[list[ToolCallDTO], bool]:
        """
        Extract tool calls from Agno's RunOutput.

        Args:
            run_output: The RunOutput from Agno

        Returns:
            Tuple of (tool_calls list, has_pending_approvals flag)
        """
        tool_calls: list[ToolCallDTO] = []
        has_pending = False

        if not hasattr(run_output, "tools") or not run_output.tools:
            return tool_calls, has_pending

        for tool_exec in run_output.tools:
            needs_confirmation = getattr(tool_exec, "requires_confirmation", False) and not getattr(
                tool_exec, "confirmed", False
            )

            tool_call_dto = ToolCallDTO(
                id=getattr(tool_exec, "tool_call_id", "") or "",
                name=getattr(tool_exec, "tool_name", "") or "",
                input=getattr(tool_exec, "tool_args", {}) or {},
                requires_approval=needs_confirmation,
                status="pending" if needs_confirmation else "executed",
            )
            tool_calls.append(tool_call_dto)

            if needs_confirmation:
                has_pending = True

        # Log tool execution
        logger.info(f"Agno Tools: Executed {len(tool_calls)} tool call(s)")
        for i, tc in enumerate(tool_calls, 1):
            logger.debug(f"  Tool {i}: {tc.name}")

        return tool_calls, has_pending

    def _build_response_metadata(self, tracing_context: dict[str, Any] | None) -> dict[str, Any]:
        """Build response metadata from tracing context."""
        response_metadata: dict[str, Any] = {}

        if not tracing_context:
            return response_metadata

        # Include tracing IDs in response metadata for correlation
        for key in ("run_id", "session_id", "user_id"):
            if tracing_context.get(key):
                response_metadata[key] = tracing_context[key]

        # Include any metadata that was passed to Agno
        if tracing_context.get("metadata"):
            response_metadata.update(tracing_context["metadata"])

        return response_metadata
