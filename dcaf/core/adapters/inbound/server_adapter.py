"""
Server Adapter - Bridge between Core Agent and FastAPI server.

This adapter allows a Core Agent to work with the existing
FastAPI server infrastructure, providing full compatibility
with the DuploCloud helpdesk integration.

Example:
    from dcaf.core import Agent
    from dcaf.core.adapters.inbound import ServerAdapter
    from dcaf.agent_server import create_chat_app

    agent = Agent(tools=[...])
    app = create_chat_app(ServerAdapter(agent))
"""

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from ....schemas.events import (
    ApprovalsEvent,
    CommandsEvent,
    DoneEvent,
    ErrorEvent,
    ExecutedApprovalsEvent,
    ExecutedCommandsEvent,
    ExecutedToolCallsEvent,
    StreamEvent,
    ToolCallsEvent,
)
from ....schemas.messages import (
    AgentMessage,
    Approval,
    Command,
    ExecutedApproval,
    ExecutedCommand,
    ExecutedToolCall,
    FileObject,
)
from ...agent import Agent

logger = logging.getLogger(__name__)

ExecutorFn = Callable[[str, list[dict[str, Any]] | None, dict[str, Any] | None], str]


class ServerAdapter:
    """
    Adapts a Core Agent to work with the existing FastAPI server.

    This implements the AgentProtocol interface expected by
    `dcaf.agent_server.create_chat_app()`.

    The adapter:
    - Converts incoming message format to Core format
    - Runs the Core agent
    - Converts responses back to AgentMessage schema
    - Handles tool call approvals

    Args:
        agent: The Core Agent instance to wrap
        execute_cmd: Optional custom command executor. When provided, replaces the
            built-in subprocess implementation for all command execution paths.
            Signature: ``(command: str, files: list[dict] | None, context: dict | None) -> str``

            Use this for domain-specific execution: kubeconfig injection, sandboxing,
            timeouts, environment setup. ``context`` carries the full platform_context
            including ``thread_id`` if sent by the client.

    Example:
        from dcaf.core import Agent
        from dcaf.core.adapters.inbound import ServerAdapter
        from dcaf.agent_server import create_chat_app
        import uvicorn

        # Create your agent
        agent = Agent(
            tools=[list_pods, delete_pod],
            system_prompt="You are a Kubernetes assistant."
        )

        # Wrap it for the server
        adapter = ServerAdapter(agent)

        # Create and run the app
        app = create_chat_app(adapter)
        uvicorn.run(app, host="0.0.0.0", port=8000)

        # Custom executor with kubeconfig injection
        import os, subprocess

        def k8s_executor(command, files, context):
            env = os.environ.copy()
            env["KUBECONFIG"] = (context or {}).get("kubeconfig_path", "")
            result = subprocess.run(command, shell=True, env=env, capture_output=True, text=True)
            return result.stdout

        adapter = ServerAdapter(agent, execute_cmd=k8s_executor)
    """

    def __init__(
        self,
        agent: Agent,
        execute_cmd: ExecutorFn | None = None,
    ) -> None:
        self.agent = agent
        self._cmd_executor = execute_cmd

    async def invoke(self, messages: dict[str, list[dict[str, Any]]]) -> AgentMessage:
        """
        Handle a chat request.

        This is called by the /api/sendMessage endpoint.

        Args:
            messages: The message payload from the server
                     Format: {"messages": [{"role": "...", "content": "..."}, ...]}

        Returns:
            AgentMessage with the response
        """
        logger.debug(
            f"ServerAdapter.invoke called with {len(messages.get('messages', []))} messages"
        )

        # Extract messages list and platform context
        messages_list = messages.get("messages", [])
        platform_context = self._extract_platform_context(messages_list)

        # Merge top-level request fields into context (platform_context takes precedence)
        request_fields: dict[str, Any] = messages.get("_request_fields", {})  # type: ignore[assignment]
        context = {**request_fields, **platform_context} if request_fields else platform_context

        # Unified approval processing — normalize all sources, execute once
        all_approvals = self._normalize_approvals(messages_list)
        executed_approvals = self._process_approvals(all_approvals, context)
        executed_commands, executed_tool_calls = self._fan_out_executed(executed_approvals)

        # Convert to Core format and inject execution results
        core_messages = self._convert_messages(messages_list)
        self._inject_execution_results(core_messages, executed_approvals)

        if not core_messages:
            return AgentMessage(content="No messages provided.")

        # Run the core agent
        try:
            response = await self.agent.run(
                messages=cast(list[Any], core_messages),
                context=context,
            )

            # Convert to AgentMessage using native to_message()
            agent_msg = response.to_message()

            # Add any executed results from this request
            if executed_tool_calls:
                agent_msg.data.executed_tool_calls.extend(executed_tool_calls)
            if executed_commands:
                agent_msg.data.executed_cmds.extend(executed_commands)
            if executed_approvals:
                agent_msg.data.executed_approvals.extend(executed_approvals)

            # If there are pending approvals, ensure helpful content
            if response.needs_approval and not agent_msg.content:
                agent_msg.content = "I need your approval to execute the following tools:"

            return agent_msg  # type: ignore[return-value]

        except Exception as e:
            logger.exception(f"Error in agent execution: {e}")
            return AgentMessage(content=f"Error: {str(e)}")

    def _translate_tool_calls_event(self, event: "ToolCallsEvent") -> list[StreamEvent]:
        """Translate a ToolCallsEvent into a unified ApprovalsEvent + split legacy events.

        Returns a list of events to emit in place of the raw ToolCallsEvent:
        - ApprovalsEvent (all items, each with correct type from approval_type)
        - ToolCallsEvent (only non-command items, for legacy tool_call clients)
        - CommandsEvent (only command items, for legacy command clients)
        """
        # 1. Unified event — all approvals with correct types (future clients)
        approvals = [
            Approval(
                id=tc.id,
                type=tc.approval_type,
                name=tc.name,
                input=tc.input,
                description=tc.tool_description,
                intent=tc.intent,
            )
            for tc in event.tool_calls
        ]
        results: list[StreamEvent] = [ApprovalsEvent(approvals=approvals)]

        # 2. Legacy: ToolCallsEvent only for tool_call items
        tool_call_items = [tc for tc in event.tool_calls if tc.approval_type != "command"]
        if tool_call_items:
            results.append(ToolCallsEvent(tool_calls=tool_call_items))

        # 3. Legacy: CommandsEvent only for command items
        command_items = [tc for tc in event.tool_calls if tc.approval_type == "command"]
        if command_items:
            commands = []
            for tc in command_items:
                raw_files = tc.input.get("files") or None
                files: list[FileObject] | None = None
                if raw_files:
                    files = [FileObject(**f) for f in raw_files]
                commands.append(
                    Command(
                        command=tc.input.get("command", tc.name),
                        files=files,
                    )
                )
            results.append(CommandsEvent(commands=commands))

        return results

    def _translate_commands_event(self, event: "CommandsEvent") -> ApprovalsEvent:
        """Translate a CommandsEvent into an ApprovalsEvent for unified approval clients."""
        approvals = [
            Approval(
                id=uuid.uuid4().hex[:12],
                type="command",
                name=cmd.command,
                input={
                    "command": cmd.command,
                    "files": [f.model_dump() for f in cmd.files] if cmd.files else [],
                },
                description=cmd.command,
            )
            for cmd in event.commands
        ]
        return ApprovalsEvent(approvals=approvals)

    def _translate_stream_event(
        self, event: StreamEvent, request_fields: dict[str, Any]
    ) -> list[StreamEvent]:
        """Translate a single stream event, applying Gap 1 and Gap 2 transformations.

        Returns the list of events to yield for this input event.
        Gap 1: ToolCallsEvent is replaced by ApprovalsEvent + split legacy events.
        Gap 2: CommandsEvent is preceded by an ApprovalsEvent.
        """
        if isinstance(event, DoneEvent) and request_fields:
            event.meta_data["request_context"] = request_fields

        if isinstance(event, ToolCallsEvent) and event.tool_calls:
            # Gap 1: replaced entirely — do not fall through to raw yield
            return self._translate_tool_calls_event(event)

        if isinstance(event, CommandsEvent) and event.commands:
            # Gap 2: prepend ApprovalsEvent, then emit original CommandsEvent
            return [self._translate_commands_event(event), event]

        return [event]

    async def invoke_stream(
        self, messages: dict[str, list[dict[str, Any]]]
    ) -> AsyncIterator[StreamEvent]:
        """
        Handle a streaming chat request.

        This is called by the /api/chat-stream endpoint.
        Uses true token-by-token streaming from the Agent.

        Args:
            messages: The message payload from the server

        Yields:
            StreamEvent objects for NDJSON streaming
        """
        logger.debug("ServerAdapter.invoke_stream called")

        # Extract messages list and platform context
        messages_list = messages.get("messages", [])
        platform_context = self._extract_platform_context(messages_list)

        # Merge top-level request fields into context (platform_context takes precedence)
        request_fields: dict[str, Any] = messages.get("_request_fields", {})  # type: ignore[assignment]
        context = {**request_fields, **platform_context} if request_fields else platform_context

        # Unified approval processing — normalize all sources, execute once
        all_approvals = self._normalize_approvals(messages_list)
        executed_approvals = self._process_approvals(all_approvals, context)
        executed_commands, executed_tool_calls = self._fan_out_executed(executed_approvals)

        # Emit execution events — unified first, then legacy
        if executed_approvals:
            yield ExecutedApprovalsEvent(executed_approvals=executed_approvals)
        if executed_commands:
            yield ExecutedCommandsEvent(executed_cmds=executed_commands)
        if executed_tool_calls:
            yield ExecutedToolCallsEvent(executed_tool_calls=executed_tool_calls)

        # Convert to Core format and inject execution results
        core_messages = self._convert_messages(messages_list)
        self._inject_execution_results(core_messages, executed_approvals)

        if not core_messages:
            yield ErrorEvent(error="No messages provided")
            return

        try:
            # Use true streaming from the Agent
            async for event in self.agent.run_stream(
                messages=cast(list[Any], core_messages),
                context=context,
            ):
                for translated in self._translate_stream_event(event, request_fields):
                    yield translated

        except Exception as e:
            logger.exception(f"Stream error: {e}")
            yield ErrorEvent(error=str(e))

    def _inject_execution_results(
        self,
        core_messages: list[dict[str, Any]],
        executed_approvals: list[ExecutedApproval],
    ) -> None:
        """Inject execution results into the conversation as a user message.

        Branches on approval type for the context string format:
        - command: "Executed command: <cmd>\nOutput: <out>"
        - tool_call: "Tool result for <name> with inputs <input>: <out>"
        """
        parts: list[str] = []
        for ea in executed_approvals:
            if ea.type == "command":
                parts.append(
                    f"Executed command: {ea.input.get('command', ea.name)}\nOutput: {ea.output}"
                )
            else:
                parts.append(f"Tool result for {ea.name} with inputs {ea.input}: {ea.output}")
        if not parts:
            return
        result_content = "\n\n".join(parts)
        if core_messages and core_messages[-1]["role"] == "user":
            core_messages[-1]["content"] += "\n\n" + result_content
        else:
            core_messages.append({"role": "user", "content": result_content})

    def _convert_messages(self, messages_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert from server message format to Core format.

        Server format includes rich data (tool_calls, executed_cmds, etc.)
        Core format is simple: [{"role": "...", "content": "..."}]
        """
        core_messages = []

        for msg in messages_list:
            role = msg.get("role")
            content = msg.get("content", "")

            # Only include user and assistant messages
            if role in ["user", "assistant"]:
                # Re-inject prior execution history so the LLM has context across
                # turns. Clients send back executed_cmds / executed_tool_calls /
                # executed_approvals from previous turns in every request.
                if role == "user":
                    data = msg.get("data", {})
                    for ec in data.get("executed_cmds", []):
                        content += f"\n\nPreviously executed: {ec.get('command', '')}\nOutput: {ec.get('output', '')}"
                    for tc in data.get("executed_tool_calls", []):
                        content += f"\n\nPreviously executed tool: {tc.get('name', '')} with inputs {tc.get('input', {})}\nOutput: {tc.get('output', '')}"
                    for ea in data.get("executed_approvals", []):
                        content += f"\n\nPreviously executed: {ea.get('name', '')} with inputs {ea.get('input', {})}\nOutput: {ea.get('output', '')}"
                core_messages.append({"role": role, "content": content})

        return core_messages

    def _extract_platform_context(self, messages_list: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Extract platform context from the latest user message.

        The platform_context contains runtime info like tenant_name,
        k8s_namespace, AWS credentials, etc.
        """
        # Find the last user message
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                platform_context = msg.get("platform_context", {})
                if platform_context:
                    # Convert Pydantic model to dict if needed
                    if hasattr(platform_context, "model_dump"):
                        result = platform_context.model_dump()
                        return result if isinstance(result, dict) else {}
                    return platform_context if isinstance(platform_context, dict) else {}
        return {}

    def _normalize_approvals(
        self,
        messages_list: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize all approval sources from the latest message into a single list.

        Reads data.approvals[], data.cmds[], and data.tool_calls[] and converts
        all entries to the unified Approval dict format.  data.approvals[] entries
        take precedence — legacy entries whose id already appears in approvals are
        skipped to avoid double-execution.
        """
        if not messages_list:
            return []

        data = messages_list[-1].get("data", {})
        seen_ids: set[str] = set()
        result: list[dict[str, Any]] = []

        # 1. Unified approvals — source of truth
        for a in data.get("approvals", []):
            aid = a.get("id", "")
            if aid:
                seen_ids.add(aid)
            result.append(a)

        # 2. Legacy data.cmds[] — normalize to command-type Approval
        for cmd in data.get("cmds", []):
            command_str = cmd.get("command", "")
            result.append(
                {
                    "id": uuid.uuid4().hex,
                    "type": "command",
                    "name": command_str,
                    "input": {"command": command_str, "files": cmd.get("files")},
                    "execute": cmd.get("execute", False),
                    "rejection_reason": cmd.get("rejection_reason"),
                }
            )

        # 3. Legacy data.tool_calls[] — normalize to tool_call-type Approval
        for tc in data.get("tool_calls", []):
            tc_id = tc.get("id") or uuid.uuid4().hex
            if tc_id in seen_ids:
                continue  # already covered by data.approvals[]
            result.append(
                {
                    "id": tc_id,
                    "type": "tool_call",
                    "name": tc.get("name", ""),
                    "input": tc.get("input", {}),
                    "execute": tc.get("execute", False),
                    "rejection_reason": tc.get("rejection_reason"),
                }
            )

        return result

    def _fan_out_executed(
        self,
        executed_approvals: list[ExecutedApproval],
    ) -> tuple[list[ExecutedCommand], list[ExecutedToolCall]]:
        """Convert ExecutedApproval list to legacy ExecutedCommand / ExecutedToolCall lists.

        These are used to populate the legacy fields in the response (data.executed_cmds,
        data.executed_tool_calls) and the legacy stream events (ExecutedCommandsEvent,
        ExecutedToolCallsEvent) for backward-compatible clients.
        """
        cmds: list[ExecutedCommand] = []
        tool_calls: list[ExecutedToolCall] = []
        for ea in executed_approvals:
            if ea.type == "command":
                cmds.append(
                    ExecutedCommand(
                        command=ea.input.get("command", ea.name),
                        output=ea.output,
                    )
                )
            else:
                tool_calls.append(
                    ExecutedToolCall(
                        id=ea.id,
                        name=ea.name,
                        input=ea.input,
                        output=ea.output,
                    )
                )
        return cmds, tool_calls

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        platform_context: dict[str, Any],
    ) -> str:
        """Execute a tool by name."""
        # Find the tool in the agent's tool list
        for tool in self.agent.tools:
            if getattr(tool, "name", None) == tool_name:
                try:
                    if hasattr(tool, "execute"):
                        result = tool.execute(tool_input, platform_context)
                        return str(result) if result is not None else ""
                    elif callable(tool):
                        result = tool(**tool_input)
                        return str(result) if result is not None else ""
                except Exception as e:
                    return f"Error executing {tool_name}: {str(e)}"

        return f"Tool '{tool_name}' not found"

    def _execute_cmd(
        self,
        command: str,
        files: list[dict[str, Any]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Execute a shell command. If a custom executor was provided at construction,
        it is called instead of the built-in subprocess implementation.

        If files are provided (in the default path), they are written to a temporary
        directory which is used as the working directory for the command. The directory
        is always cleaned up after execution, even on error.
        """
        if self._cmd_executor is not None:
            return self._cmd_executor(command, files, context)

        work_dir: str | None = None
        try:
            if files:
                work_dir = tempfile.mkdtemp()
                written_names: set[str] = set()
                for f in files:
                    # Use basename only — never allow path traversal.
                    # The `or "file"` guard handles the empty-string case
                    # (f.get default only fires when the key is absent).
                    safe_name = os.path.basename(f.get("file_path", "") or "file")
                    if safe_name in written_names:
                        logger.warning(
                            "Duplicate filename '%s' in files list; overwriting previous content",
                            safe_name,
                        )
                    written_names.add(safe_name)
                    with open(os.path.join(work_dir, safe_name), "w") as fh:
                        fh.write(f.get("file_content", ""))

            result = subprocess.run(  # noqa: S602
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=work_dir,
            )
            output = result.stdout
            if result.stderr:
                output = (
                    (output + f"\n\nErrors:\n{result.stderr}")
                    if output
                    else f"Errors:\n{result.stderr}"
                )
            return output or "Command executed successfully with no output."
        except Exception as e:
            logger.error("Error executing command: %s", e)
            return f"Error executing command: {e}"
        finally:
            if work_dir:
                shutil.rmtree(work_dir, ignore_errors=True)

    def _process_approvals(
        self,
        approvals: list[dict[str, Any]],
        platform_context: dict[str, Any],
    ) -> list[ExecutedApproval]:
        """Execute a pre-normalized list of approval dicts.

        For each entry:
        - type="command" + execute=True  → _execute_cmd()
        - type="tool_call" + execute=True → _execute_tool()
        - rejection_reason set            → record rejection (no execution)
        """
        executed: list[ExecutedApproval] = []

        for approval in approvals:
            approval_id = approval.get("id", "")
            approval_type = approval.get("type", "")
            name = approval.get("name", "")
            tool_input = approval.get("input", {})

            if approval.get("execute", False):
                if approval_type == "command":
                    files = tool_input.get("files") or None
                    result = self._execute_cmd(
                        tool_input.get("command", name), files=files, context=platform_context
                    )
                else:
                    result = self._execute_tool(name, tool_input, platform_context)
                executed.append(
                    ExecutedApproval(
                        id=approval_id,
                        type=approval_type,
                        name=name,
                        input=tool_input,
                        output=result,
                    )
                )
            elif approval.get("rejection_reason"):
                executed.append(
                    ExecutedApproval(
                        id=approval_id,
                        type=approval_type,
                        name=name,
                        input=tool_input,
                        output=f"Rejected: {approval['rejection_reason']}",
                    )
                )

        return executed
