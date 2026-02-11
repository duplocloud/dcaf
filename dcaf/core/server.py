"""
Server utilities for running DCAF Core agents.

This module provides simple functions to start an agent as a REST server.

Supports both:
- Agent class (simple use case)
- Callable functions (custom agent logic)

Example - Agent class:
    from dcaf.core import Agent, serve

    agent = Agent(tools=[my_tool])
    serve(agent, port=8000)

Example - Custom function:
    from dcaf.core import serve, Session
    from dcaf.core.primitives import AgentResult

    def my_agent(messages: list, context: dict, session: Session) -> AgentResult:
        # Access and modify session
        count = session.get("call_count", 0)
        session.set("call_count", count + 1)

        return AgentResult(
            text=f"Call #{count + 1}",
            session=session.to_dict(),  # Return updated session
        )

    serve(my_agent, port=8000)

Example - With custom routes:
    from dcaf.core import Agent, serve
    from fastapi import APIRouter

    agent = Agent(tools=[my_tool])

    custom_router = APIRouter()

    @custom_router.get("/api/custom/schema")
    async def get_schema():
        return {"schema": "..."}

    serve(agent, additional_routers=[custom_router])
"""

import inspect
import logging
from collections.abc import Callable, Iterator, Sequence
from typing import TYPE_CHECKING, Any, Union

from .agent import Agent

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI
    from starlette.websockets import WebSocket

    from ..channel_routing import ChannelResponseRouter
    from .a2a.models import AgentCard
    from .primitives import AgentResult
    from .schemas.messages import AgentMessage
    from .session import Session

logger = logging.getLogger(__name__)

# Type for agent handlers (can be 2-arg or 3-arg with session)
AgentHandler = Callable[..., "AgentResult"]

# Server defaults
DEFAULT_PORT = 8000
DEFAULT_HOST = "0.0.0.0"
DEFAULT_WORKERS = 1
DEFAULT_TIMEOUT_KEEP_ALIVE = 5
DEFAULT_MCP_PORT = 8001
DEFAULT_MCP_TRANSPORT = "sse"
DEFAULT_A2A_ADAPTER = "agno"
DEFAULT_WS_PING_INTERVAL: float = 20.0
DEFAULT_WS_PING_TIMEOUT: float = 20.0


def serve(
    agent: Union["Agent", AgentHandler],
    port: int = DEFAULT_PORT,
    host: str = DEFAULT_HOST,
    reload: bool = False,
    log_level: str = "info",
    workers: int = DEFAULT_WORKERS,
    timeout_keep_alive: int = DEFAULT_TIMEOUT_KEEP_ALIVE,
    additional_routers: Sequence["APIRouter"] | None = None,
    channel_router: "ChannelResponseRouter | None" = None,
    a2a: bool = False,
    a2a_adapter: str = DEFAULT_A2A_ADAPTER,
    a2a_agent_card: "AgentCard | dict | None" = None,
    mcp: bool = False,
    mcp_port: int = DEFAULT_MCP_PORT,
    mcp_transport: str = DEFAULT_MCP_TRANSPORT,
    ws_ping_interval: float | None = DEFAULT_WS_PING_INTERVAL,
    ws_ping_timeout: float | None = DEFAULT_WS_PING_TIMEOUT,
) -> None:
    """
    Start a REST server for the agent.

    This is the simplest way to expose an agent via HTTP. It creates
    a FastAPI application with the standard endpoints and runs it.

    Args:
        agent: Either an Agent instance OR a callable function.
               If callable, signature must be: (messages: list, context: dict) -> AgentResult
        port: Port to listen on (default: 8000)
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
        reload: Enable auto-reload on code changes (default: False)
        log_level: Logging level (default: "info")
        workers: Number of worker processes (default: 1). For production,
                 a common formula is (2 * cpu_cores) + 1. Cannot be used
                 with reload=True.
        timeout_keep_alive: Keep-alive timeout in seconds (default: 5).
                           Set this to match or exceed your load balancer's
                           idle timeout (e.g., AWS ALB defaults to 60s).
        additional_routers: Optional list of FastAPI APIRouter instances to include.
                           Use this to add custom endpoints beyond /api/chat.
        channel_router: Optional channel response router for multi-agent environments.
                       When provided and the request includes ``source: "slack"``,
                       the router decides whether the agent should respond.
                       Use ``SlackResponseRouter`` for Slack integration.
        a2a: Enable A2A (Agent-to-Agent) protocol support (default: False).
            When enabled, adds A2A endpoints for agent discovery and task handling.
        a2a_adapter: A2A adapter to use (default: "agno").
                    Currently only "agno" is supported.
        a2a_agent_card: Optional custom agent card for A2A discovery. Can be an
                       AgentCard instance or a dict with arbitrary A2A spec fields.
                       If not provided, the card is auto-generated from the agent.
        mcp: Enable MCP (Model Context Protocol) server (default: False).
            When enabled, starts an MCP server alongside the HTTP server.
            This allows AI assistants like Claude to discover and use the
            agent's tools via the MCP protocol.
        mcp_port: Port for the MCP server when mcp=True (default: 8001).
        mcp_transport: Transport for MCP server - "sse" (default) or "stdio".
                      SSE runs an HTTP server, stdio uses standard I/O.
        ws_ping_interval: Interval in seconds between WebSocket ping frames
                         (default: 20.0). Set to ``None`` to disable pings.
                         Uvicorn sends these automatically to detect dead connections.
        ws_ping_timeout: Seconds to wait for a pong reply before closing
                        the connection (default: 20.0). Set to ``None`` to wait
                        indefinitely.

    Endpoints:
        GET  /health           - Health check
        POST /api/chat         - Synchronous chat (async, non-blocking)
        POST /api/chat-stream  - Streaming chat (NDJSON, async)

    A2A Endpoints (when a2a=True):
        GET  /.well-known/agent.json  - Agent card (A2A discovery)
        POST /a2a/tasks/send          - Receive A2A tasks
        GET  /a2a/tasks/{id}          - A2A task status

    MCP Server (when mcp=True):
        Runs on mcp_port (default: 8001). Exposes agent tools via MCP protocol
        for AI assistants like Claude Desktop to discover and call.

    Example - Using Agent class:
        from dcaf.core import Agent, serve
        from dcaf.tools import tool

        @tool(description="List pods")
        def list_pods(namespace: str = "default") -> str:
            return kubectl(f"get pods -n {namespace}")

        agent = Agent(tools=[list_pods])
        serve(agent)  # Runs at http://0.0.0.0:8000

    Example - Using custom function:
        from dcaf.core import serve
        from dcaf.core.primitives import llm, AgentResult

        def my_agent(messages: list, context: dict) -> AgentResult:
            # Your custom logic - any structure
            intent = llm.call(messages, system="Classify intent")

            if "delete" in intent.text:
                # Multiple LLM calls, branching, etc.
                ...

            return AgentResult(text="Done!")

        serve(my_agent, port=8000)

    Example - With custom routes:
        from dcaf.core import Agent, serve
        from fastapi import APIRouter

        agent = Agent(tools=[my_tool])
        custom_router = APIRouter()

        @custom_router.get("/api/custom/status")
        async def get_status():
            return {"status": "ok"}

        @custom_router.get("/api/custom/schema")
        async def get_schema():
            return {"schema": "..."}

        serve(agent, additional_routers=[custom_router])

    Example - Custom port:
        serve(agent, port=8080)

    Example - Development mode:
        serve(agent, port=8000, reload=True)

    Example - Production mode:
        serve(
            agent,
            port=8000,
            workers=4,
            timeout_keep_alive=30,
            log_level="warning",
        )

    Example - With MCP enabled (HTTP + MCP servers):
        serve(agent, mcp=True)
        # HTTP at http://localhost:8000
        # MCP at http://localhost:8001 (SSE transport)

    Example - MCP only (use serve_mcp from dcaf.mcp):
        from dcaf.mcp import serve_mcp
        serve_mcp(agent, name="my-agent")

    Note:
        This function blocks until the server is stopped (Ctrl+C).
        For programmatic control, use create_app() instead.

    Raises:
        ValueError: If reload=True and workers > 1 (mutually exclusive in uvicorn).
    """
    import uvicorn

    # Validate reload and workers are not used together
    if reload and workers > 1:
        raise ValueError(
            "Cannot use reload=True with workers > 1. "
            "These options are mutually exclusive in uvicorn. "
            "Use workers=1 for development with hot reload."
        )

    # Create the FastAPI app
    app = create_app(
        agent,
        additional_routers=additional_routers,
        channel_router=channel_router,
        a2a=a2a,
        a2a_adapter=a2a_adapter,
        a2a_agent_card=a2a_agent_card,
    )

    logger.info(f"Starting DCAF server at http://{host}:{port}")
    logger.info("Endpoints:")
    logger.info(f"  GET  http://{host}:{port}/health")
    logger.info(f"  POST http://{host}:{port}/api/chat")
    logger.info(f"  POST http://{host}:{port}/api/chat-stream")
    logger.info(f"  WS   ws://{host}:{port}/api/chat-ws")
    if a2a:
        logger.info("A2A Endpoints:")
        logger.info(f"  GET  http://{host}:{port}/.well-known/agent.json")
        logger.info(f"  POST http://{host}:{port}/a2a/tasks/send")
        logger.info(f"  GET  http://{host}:{port}/a2a/tasks/{{id}}")
    if additional_routers:
        logger.info(f"  + {len(additional_routers)} custom router(s)")
    if workers > 1:
        logger.info(f"Configuration: {workers} workers, {timeout_keep_alive}s keep-alive")

    # Start MCP server in background if enabled
    mcp_process = None
    if mcp:
        mcp_process = _start_mcp_server(agent, host, mcp_port, mcp_transport)

    try:
        # Run the HTTP server (blocking)
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
            workers=workers,
            timeout_keep_alive=timeout_keep_alive,
            ws_ping_interval=ws_ping_interval,
            ws_ping_timeout=ws_ping_timeout,
        )
    finally:
        # Clean up MCP server if it was started
        if mcp_process:
            logger.info("Stopping MCP server...")
            mcp_process.terminate()
            mcp_process.join(timeout=5)


def create_app(
    agent: Union["Agent", AgentHandler],
    additional_routers: Sequence["APIRouter"] | None = None,
    channel_router: "ChannelResponseRouter | None" = None,
    a2a: bool = False,
    a2a_adapter: str = "agno",  # noqa: ARG001 - Reserved for future A2A adapter selection
    a2a_agent_card: "AgentCard | dict | None" = None,
) -> "FastAPI":
    """
    Create a FastAPI application for the agent without starting the server.

    This creates a server with the following endpoints:

    Endpoints:
        GET  /health           - Health check
        POST /api/chat         - Synchronous chat
        POST /api/chat-stream  - Streaming chat (NDJSON)
        WS   /api/chat-ws      - WebSocket bidirectional streaming

    Legacy Aliases (Deprecated):
        POST /api/sendMessage       - Alias for /api/chat
        POST /api/sendMessageStream - Alias for /api/chat-stream

    Args:
        agent: Either an Agent instance OR a callable function.
               If callable, signature must be: (messages: list, context: dict) -> AgentResult
        additional_routers: Optional list of FastAPI APIRouter instances to include.
                           Use this to add custom endpoints beyond /api/chat.
        channel_router: Optional channel response router for multi-agent environments.
                       When provided and the request includes ``source: "slack"``,
                       the router decides whether the agent should respond.
                       Use ``SlackResponseRouter`` for Slack integration.
        a2a: Enable A2A (Agent-to-Agent) protocol support (default: False).
        a2a_adapter: A2A adapter to use (default: "agno").
        a2a_agent_card: Optional custom agent card for A2A discovery. Can be an
                       AgentCard instance or a dict with arbitrary A2A spec fields.
                       If not provided, the card is auto-generated from the agent.

    Returns:
        FastAPI application instance

    Example - Add custom endpoints directly:
        from dcaf.core import Agent, create_app

        agent = Agent(tools=[...])
        app = create_app(agent)

        @app.get("/custom")
        def custom_endpoint():
            return {"message": "Hello!"}

        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8000)

    Example - Add custom endpoints via router:
        from dcaf.core import Agent, create_app
        from fastapi import APIRouter

        agent = Agent(tools=[...])

        custom_router = APIRouter(prefix="/api/custom")

        @custom_router.get("/schema")
        async def get_schema():
            return {"schema": "..."}

        @custom_router.get("/status")
        async def get_status():
            return {"status": "ok"}

        app = create_app(agent, additional_routers=[custom_router])

    Example - Custom function with custom endpoints:
        from dcaf.core import create_app
        from dcaf.core.primitives import AgentResult

        def my_agent(messages, context) -> AgentResult:
            return AgentResult(text="Hello!")

        app = create_app(my_agent)

        @app.get("/status")
        def status():
            return {"agents_running": 1}
    """
    from fastapi import Body, FastAPI, HTTPException
    from fastapi.responses import StreamingResponse

    # Create the appropriate adapter based on agent type
    adapter = _create_adapter(agent)

    # Create FastAPI app
    app = FastAPI(title="DCAF Core Chat Service", version="2.0.0")

    # Health endpoint
    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # -------------------------------------------------------------------------
    # V2 Handler logic
    # -------------------------------------------------------------------------

    async def _handle_chat_v2(raw_body: dict[str, Any]) -> dict[str, Any]:
        """V2 handler for synchronous chat endpoints."""
        # Validate messages field
        if "messages" not in raw_body:
            raise HTTPException(
                status_code=400, detail="'messages' field missing from request body"
            )

        # Extract _request_fields (all top-level fields except 'messages')
        request_fields = {k: v for k, v in raw_body.items() if k != "messages"}

        # Check channel router for Slack
        source = raw_body.get("source")
        if source == "slack" and channel_router:
            should_respond = channel_router.should_agent_respond(raw_body["messages"])
            if not should_respond.get("should_respond", True):
                return {"role": "assistant", "content": ""}

        # Build the input dict for the agent
        agent_input: dict[str, Any] = {"messages": raw_body["messages"]}
        if request_fields:
            agent_input["_request_fields"] = request_fields

        # Call the agent
        try:
            result = await _invoke_agent(adapter, agent_input)

            # Build response
            response: dict[str, Any] = {
                "role": result.role if hasattr(result, "role") else "assistant",
                "content": result.content if hasattr(result, "content") else str(result),
            }

            # Echo request_fields in meta_data.request_context if present
            if request_fields:
                response["meta_data"] = {"request_context": request_fields}

            return response

        except Exception as e:
            logger.exception(f"V2 Chat endpoint error: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from e

    async def _handle_chat_stream_v2(raw_body: dict[str, Any]) -> StreamingResponse:
        """V2 handler for streaming chat endpoints."""
        from .schemas.events import DoneEvent, ErrorEvent

        # Validate messages field
        if "messages" not in raw_body:
            raise HTTPException(
                status_code=400, detail="'messages' field missing from request body"
            )

        # Extract _request_fields (all top-level fields except 'messages')
        request_fields = {k: v for k, v in raw_body.items() if k != "messages"}

        # Check channel router for Slack
        source = raw_body.get("source")
        if source == "slack" and channel_router:
            should_respond = channel_router.should_agent_respond(raw_body["messages"])
            if not should_respond.get("should_respond", True):

                def done_generator() -> Iterator[str]:
                    yield DoneEvent().model_dump_json() + "\n"

                return StreamingResponse(done_generator(), media_type="application/x-ndjson")

        # Build the input dict for the agent
        agent_input: dict[str, Any] = {"messages": raw_body["messages"]}
        if request_fields:
            agent_input["_request_fields"] = request_fields

        async def event_generator() -> Any:
            try:
                async for event in _stream_agent(adapter, agent_input):
                    if hasattr(event, "model_dump_json"):
                        yield event.model_dump_json() + "\n"
                    else:
                        import json

                        yield json.dumps(event) + "\n"
            except Exception as e:
                logger.exception(f"V2 Stream error: {e}")
                yield ErrorEvent(error=str(e)).model_dump_json() + "\n"

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    # -------------------------------------------------------------------------
    # V2 Endpoints (Preferred) - Uses V2 code path
    # -------------------------------------------------------------------------

    @app.post("/api/chat", tags=["chat"])
    async def chat(raw_body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Synchronous chat endpoint (V2 code path)."""
        return await _handle_chat_v2(raw_body)

    @app.post("/api/chat-stream", tags=["chat"])
    async def chat_stream(raw_body: dict[str, Any] = Body(...)) -> StreamingResponse:
        """Streaming chat endpoint (V2 code path, NDJSON)."""
        return await _handle_chat_stream_v2(raw_body)

    # -------------------------------------------------------------------------
    # Legacy Endpoint Aliases (Deprecated) - Aliases to V2 endpoints
    # -------------------------------------------------------------------------

    @app.post("/api/sendMessage", tags=["legacy"], deprecated=True)
    async def send_message(raw_body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """
        Synchronous chat endpoint (alias for /api/chat).

        Deprecated: Use POST /api/chat instead.
        """
        return await _handle_chat_v2(raw_body)

    @app.post("/api/sendMessageStream", tags=["legacy"], deprecated=True)
    async def send_message_stream(raw_body: dict[str, Any] = Body(...)) -> StreamingResponse:
        """
        Streaming chat endpoint (alias for /api/chat-stream).

        Deprecated: Use POST /api/chat-stream instead.
        """
        return await _handle_chat_stream_v2(raw_body)

    # -------------------------------------------------------------------------
    # WebSocket endpoint (V2 only)
    # -------------------------------------------------------------------------

    _add_websocket_endpoint(app, adapter, channel_router)

    # -------------------------------------------------------------------------
    # A2A routes (optional)
    # -------------------------------------------------------------------------

    if a2a:
        try:
            from .a2a import create_a2a_routes

            # A2A only works with Agent instances, not callables
            if not isinstance(agent, Agent):
                logger.warning(
                    "A2A protocol requires an Agent instance, not a callable. A2A disabled."
                )
            else:
                a2a_routers = create_a2a_routes(agent, agent_card=a2a_agent_card)
                for router in a2a_routers:
                    app.include_router(router)
                logger.info("A2A protocol enabled")
        except ImportError as e:
            logger.error(f"Failed to enable A2A: {e}")
            raise RuntimeError(
                "A2A support requires additional dependencies. Install with: pip install httpx"
            ) from e

    # Add any additional routers
    if additional_routers:
        for router in additional_routers:
            app.include_router(router)

    return app


def _create_adapter(agent: Union["Agent", AgentHandler]) -> Any:
    """Create the appropriate adapter for the agent type."""
    from .agent import Agent

    # Check if it's an Agent instance
    if isinstance(agent, Agent):
        from .adapters.inbound import ServerAdapter

        return ServerAdapter(agent)

    # Check if it's an object with invoke method (AgentProtocol-like)
    if hasattr(agent, "invoke") and callable(agent.invoke):
        # Return as-is, it can be used directly by the server
        return agent

    # Check if it's a callable (function)
    if callable(agent):
        return CallableAdapter(agent)

    raise TypeError(f"agent must be an Agent instance or a callable function, got {type(agent)}")


async def _invoke_agent(adapter: Any, agent_input: dict[str, Any]) -> "AgentMessage":
    """Invoke the agent, handling both sync and async adapters."""
    import inspect

    from .schemas.messages import AgentMessage

    if hasattr(adapter, "invoke"):
        result = adapter.invoke(agent_input)
        # Handle coroutine result (async def invoke)
        if inspect.iscoroutine(result):
            result = await result
        # Ensure we return an AgentMessage
        if isinstance(result, AgentMessage):
            return result
        if hasattr(result, "content"):
            return AgentMessage(role="assistant", content=result.content)
        return AgentMessage(role="assistant", content=str(result))
    raise TypeError("Adapter does not have invoke method")


async def _stream_agent(adapter: Any, agent_input: dict[str, Any]) -> Any:
    """Stream from the agent, handling both sync and async generators."""
    import inspect

    from .schemas.events import DoneEvent, TextDeltaEvent

    if hasattr(adapter, "invoke_stream"):
        result = adapter.invoke_stream(agent_input)

        # Check for generators BEFORE coroutines to avoid Python 3.11
        # asyncio.iscoroutine misidentifying generators.
        if hasattr(result, "__anext__"):
            # Async generator (async def + yield)
            async for event in result:
                yield event
        elif hasattr(result, "__next__"):
            # Sync generator (def + yield)
            for event in result:
                yield event
        elif inspect.iscoroutine(result):
            # Coroutine (async def that returns a value)
            result = await result
            if hasattr(result, "content") and result.content:
                yield TextDeltaEvent(text=result.content)
            yield DoneEvent()
        else:
            # Single result - wrap in text_delta + done
            if hasattr(result, "content") and result.content:
                yield TextDeltaEvent(text=result.content)
            yield DoneEvent()
    else:
        # Fallback to invoke
        result = await _invoke_agent(adapter, agent_input)
        if result.content:
            yield TextDeltaEvent(text=result.content)
        yield DoneEvent()


def _add_websocket_endpoint(
    app: "FastAPI",
    adapter: Any,
    channel_router: "ChannelResponseRouter | None" = None,
) -> None:
    """
    Add WebSocket endpoint /api/chat-ws to the FastAPI app.

    The WebSocket endpoint provides bidirectional streaming chat over a
    persistent connection. A single connection stays open for multiple
    conversation turns.

    Protocol:
        - Client sends JSON: {"messages": [{"role": "user", "content": "..."}]}
        - Server responds with streaming events as JSON:
          - {"type": "text_delta", "text": "..."}
          - {"type": "tool_calls", "tool_calls": [...]}
          - {"type": "done"}
          - {"type": "error", "error": "..."}
    """
    import inspect
    import json

    from fastapi import WebSocket, WebSocketDisconnect

    @app.websocket("/api/chat-ws")
    async def websocket_chat(websocket: WebSocket) -> None:
        await websocket.accept()

        try:
            while True:
                # Receive message from client
                raw_message = await websocket.receive_text()

                # Parse JSON
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "error": "Invalid JSON"})
                    continue

                # Validate messages field
                if "messages" not in data:
                    await websocket.send_json(
                        {"type": "error", "error": "Missing 'messages' field"}
                    )
                    continue

                # Check channel router for Slack
                source = data.get("source")
                if source == "slack" and channel_router:
                    should_respond = channel_router.should_agent_respond(data["messages"])
                    if not should_respond.get("should_respond", True):
                        await websocket.send_json({"type": "done"})
                        continue

                # Extract _request_fields (all top-level fields except 'messages')
                request_fields = {k: v for k, v in data.items() if k != "messages"}

                # Build the input dict for the agent
                agent_input: dict[str, Any] = {"messages": data["messages"]}
                if request_fields:
                    agent_input["_request_fields"] = request_fields

                # Process the message through the agent
                try:
                    # Check if adapter has invoke_stream
                    if hasattr(adapter, "invoke_stream"):
                        result = adapter.invoke_stream(agent_input)

                        # Check generators BEFORE coroutines (Python 3.11 compat)
                        if hasattr(result, "__anext__"):
                            # Async generator
                            async for event in result:
                                await _send_event(websocket, event)
                        elif hasattr(result, "__next__"):
                            # Sync generator
                            for event in result:
                                await _send_event(websocket, event)
                        elif inspect.iscoroutine(result):
                            # Coroutine - await then send
                            result = await result
                            await _send_event(websocket, result)
                        else:
                            # Not a generator, treat as single result
                            await _send_event(websocket, result)
                    else:
                        # Fallback to invoke if no streaming
                        result = adapter.invoke(agent_input)
                        if hasattr(result, "content") and result.content:
                            await websocket.send_json(
                                {"type": "text_delta", "text": result.content}
                            )
                        await websocket.send_json({"type": "done"})

                except Exception as e:  # Intentional catch-all: agent code can raise anything
                    logger.exception(f"WebSocket agent error: {e}")
                    await websocket.send_json({"type": "error", "error": str(e)})
                    # Don't close connection - allow recovery

        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")


async def _send_event(websocket: "WebSocket", event: Any) -> None:
    """Send a streaming event over the WebSocket connection."""
    # Convert event to JSON-serializable dict
    if hasattr(event, "model_dump"):
        # Pydantic model
        event_dict = event.model_dump()
    elif hasattr(event, "__dict__"):
        # Dataclass or regular object
        event_dict = {k: v for k, v in event.__dict__.items() if not k.startswith("_")}
    elif isinstance(event, dict):
        event_dict = event
    else:
        event_dict = {"data": str(event)}

    # Ensure type field is present
    if "type" not in event_dict:
        # Infer type from class name
        type_name = type(event).__name__
        # Convert CamelCase to snake_case (e.g., TextDeltaEvent -> text_delta)
        event_type = ""
        for i, char in enumerate(type_name):
            if char.isupper() and i > 0:
                event_type += "_"
            event_type += char.lower()
        # Remove _event suffix if present
        if event_type.endswith("_event"):
            event_type = event_type[:-6]
        event_dict["type"] = event_type

    await websocket.send_json(event_dict)


def _start_mcp_server(agent: Any, host: str, port: int, transport: str) -> Any:
    """
    Start an MCP server in a background process.

    Args:
        agent: The DCAF Agent to expose via MCP
        host: Host to bind to
        port: Port for SSE transport
        transport: "sse" or "stdio"

    Returns:
        Process object for the MCP server
    """
    import multiprocessing

    def run_mcp() -> None:
        try:
            from ..mcp import create_mcp_server

            server_name = getattr(agent, "name", None) or "dcaf-agent"
            mcp = create_mcp_server(agent, name=server_name)

            logger.info(f"Starting MCP server '{server_name}' on port {port}")

            if transport == "sse":
                mcp.run(transport="sse", host=host, port=port)
            else:
                mcp.run()
        except ImportError as e:
            logger.error(f"MCP server failed to start: {e}. Install with: pip install dcaf[mcp]")
        except Exception as e:  # Intentional catch-all: MCP subprocess boundary
            logger.exception(f"MCP server error: {e}")

    logger.info(f"MCP Server: http://{host}:{port} ({transport} transport)")

    process = multiprocessing.Process(target=run_mcp, daemon=True)
    process.start()

    return process


class CallableAdapter:
    """
    Adapts a callable function to work with the FastAPI server.

    This allows users to write custom agent functions without
    using the Agent class.

    Supports both old-style (2 args) and new-style (3 args with session) handlers:
        # Old style (still supported)
        def my_agent(messages: list, context: dict) -> AgentResult:
            ...

        # New style with session
        def my_agent(messages: list, context: dict, session: Session) -> AgentResult:
            ...
    """

    def __init__(self, handler: AgentHandler):
        self.handler = handler
        # Check if handler accepts session parameter
        self._accepts_session = self._check_accepts_session(handler)

    def _check_accepts_session(self, handler: AgentHandler) -> bool:
        """Check if the handler function accepts a session parameter."""
        try:
            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())
            # Check for 3+ parameters or a parameter named 'session'
            return len(params) >= 3 or "session" in params
        except (ValueError, TypeError):
            return False

    def invoke(self, messages: dict) -> "AgentMessage":
        """
        Handle a synchronous chat request.

        Calls the user's handler function and converts the result
        to the HelpDesk protocol format.
        """
        from .primitives import AgentResult
        from .schemas.messages import AgentMessage

        # Extract messages and context
        messages_list = messages.get("messages", [])
        context = self._extract_context(messages_list)

        # Extract session from request
        session = self._extract_session(messages_list)

        # Add approved tool calls to context if present
        approved = self._extract_approved_tools(messages_list)
        if approved:
            context["approved_tool_calls"] = approved

        # Convert to simple format for user's handler
        simple_messages = self._simplify_messages(messages_list)

        # Call user's handler (with or without session based on signature)
        try:
            if self._accepts_session:
                result = self.handler(simple_messages, context, session)
            else:
                result = self.handler(simple_messages, context)

            # Handle different return types
            if isinstance(result, AgentResult):
                # If handler didn't include session but modified it, include it
                if not result.session and session.is_modified:
                    result.session = session.to_dict()
                # Use native to_message() conversion
                return result.to_message()
            elif isinstance(result, dict):
                # Allow returning dict directly
                return AgentMessage(
                    content=result.get("text", result.get("content", "")),
                )
            elif isinstance(result, str):
                # Allow returning string directly
                return AgentMessage(content=result)
            else:
                return AgentMessage(content=str(result))

        except Exception as e:  # Intentional catch-all: user handler code can raise anything
            logger.exception(f"Agent handler error: {e}")
            return AgentMessage(content=f"Error: {str(e)}")

    def invoke_stream(self, messages: dict[str, Any]) -> Iterator[Any]:
        """
        Handle a streaming chat request.

        For now, wraps the sync call. Users can implement
        streaming in their handler by returning a generator.
        """
        from .schemas.events import DoneEvent, ErrorEvent, TextDeltaEvent

        try:
            result = self.invoke(messages)

            # Emit the text content
            if result.content:
                yield TextDeltaEvent(text=result.content)

            yield DoneEvent()

        except Exception as e:  # Intentional catch-all: user handler code can raise anything
            yield ErrorEvent(error=str(e))

    def _simplify_messages(self, messages_list: list) -> list[dict]:
        """Convert to simple format for user's handler."""
        simple = []
        for msg in messages_list:
            simple.append(
                {
                    "role": msg.get("role"),
                    "content": msg.get("content", ""),
                }
            )
        return simple

    def _extract_context(self, messages_list: list[Any]) -> dict[str, Any]:
        """Extract platform context from the latest user message."""
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                ctx = msg.get("platform_context", {})
                if ctx:
                    if hasattr(ctx, "model_dump"):
                        result: dict[str, Any] = ctx.model_dump()
                        return result
                    return dict(ctx)
        return {}

    def _extract_session(self, messages_list: list) -> "Session":
        """Extract session data from the latest message's data field."""
        from .session import Session

        # Look for session in the latest message's data
        for msg in reversed(messages_list):
            data = msg.get("data", {})
            if data:
                # Handle both dict and Pydantic model
                if hasattr(data, "model_dump"):
                    data = data.model_dump()
                session_data = data.get("session", {})
                if session_data:
                    return Session.from_dict(session_data)

        return Session()

    def _extract_approved_tools(self, messages_list: list) -> list[dict]:
        """Extract approved tool calls from the latest message."""
        if not messages_list:
            return []

        latest = messages_list[-1]
        data = latest.get("data", {})
        tool_calls = data.get("tool_calls", [])

        approved = []
        for tc in tool_calls:
            if tc.get("execute", False):
                approved.append(
                    {
                        "id": tc.get("id"),
                        "name": tc.get("name"),
                        "input": tc.get("input", {}),
                    }
                )

        return approved
