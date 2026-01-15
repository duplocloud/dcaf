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

from typing import TYPE_CHECKING, Callable, Sequence, Union
import logging
import inspect

if TYPE_CHECKING:
    from .agent import Agent
    from fastapi import APIRouter
    from .session import Session

logger = logging.getLogger(__name__)

# Type for agent handlers (can be 2-arg or 3-arg with session)
AgentHandler = Callable[..., "AgentResult"]


def serve(
    agent: Union["Agent", AgentHandler],
    port: int = 8000,
    host: str = "0.0.0.0",
    reload: bool = False,
    log_level: str = "info",
    workers: int = 1,
    timeout_keep_alive: int = 5,
    additional_routers: Sequence["APIRouter"] | None = None,
    a2a: bool = False,
    a2a_adapter: str = "agno",
    mcp: bool = False,
    mcp_port: int = 8001,
    mcp_transport: str = "sse",
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
        a2a: Enable A2A (Agent-to-Agent) protocol support (default: False).
            When enabled, adds A2A endpoints for agent discovery and task handling.
        a2a_adapter: A2A adapter to use (default: "agno").
                    Currently only "agno" is supported.
        mcp: Enable MCP (Model Context Protocol) server (default: False).
            When enabled, starts an MCP server alongside the HTTP server.
            This allows AI assistants like Claude to discover and use the
            agent's tools via the MCP protocol.
        mcp_port: Port for the MCP server when mcp=True (default: 8001).
        mcp_transport: Transport for MCP server - "sse" (default) or "stdio".
                      SSE runs an HTTP server, stdio uses standard I/O.
        
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
    app = create_app(agent, additional_routers=additional_routers, a2a=a2a, a2a_adapter=a2a_adapter)
    
    logger.info(f"Starting DCAF server at http://{host}:{port}")
    logger.info("Endpoints:")
    logger.info(f"  GET  http://{host}:{port}/health")
    logger.info(f"  POST http://{host}:{port}/api/chat")
    logger.info(f"  POST http://{host}:{port}/api/chat-stream")
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
    a2a: bool = False,
    a2a_adapter: str = "agno",
):
    """
    Create a FastAPI application for the agent without starting the server.
    
    This is useful when you need programmatic control over the server,
    want to add custom endpoints, or need to run in a different ASGI server.
    
    Args:
        agent: Either an Agent instance OR a callable function.
               If callable, signature must be: (messages: list, context: dict) -> AgentResult
        additional_routers: Optional list of FastAPI APIRouter instances to include.
                           Use this to add custom endpoints beyond /api/chat.
        a2a: Enable A2A (Agent-to-Agent) protocol support (default: False).
        a2a_adapter: A2A adapter to use (default: "agno").
        
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
    from ..agent_server import create_chat_app
    
    # Create the appropriate adapter based on agent type
    adapter = _create_adapter(agent)
    
    # Create the base app
    app = create_chat_app(adapter)
    
    # Add A2A routes if enabled
    if a2a:
        try:
            from .a2a import create_a2a_routes
            a2a_routers = create_a2a_routes(agent)
            for router in a2a_routers:
                app.include_router(router)
            logger.info("A2A protocol enabled")
        except ImportError as e:
            logger.error(f"Failed to enable A2A: {e}")
            raise RuntimeError(
                "A2A support requires additional dependencies. "
                "Install with: pip install httpx"
            ) from e
    
    # Add any additional routers
    if additional_routers:
        for router in additional_routers:
            app.include_router(router)
    
    return app


def _create_adapter(agent: Union["Agent", AgentHandler]):
    """Create the appropriate adapter for the agent type."""
    from .agent import Agent
    
    # Check if it's an Agent instance
    if isinstance(agent, Agent):
        from .adapters.inbound import ServerAdapter
        return ServerAdapter(agent)
    
    # Check if it's a callable (function)
    if callable(agent):
        return CallableAdapter(agent)
    
    raise TypeError(
        f"agent must be an Agent instance or a callable function, got {type(agent)}"
    )


def _start_mcp_server(agent, host: str, port: int, transport: str):
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
    
    def run_mcp():
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
            logger.error(
                f"MCP server failed to start: {e}. "
                "Install with: pip install dcaf[mcp]"
            )
        except Exception as e:
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
            return len(params) >= 3 or 'session' in params
        except (ValueError, TypeError):
            return False
    
    def invoke(self, messages: dict) -> "AgentMessage":
        """
        Handle a synchronous chat request.
        
        Calls the user's handler function and converts the result
        to the HelpDesk protocol format.
        """
        from ..schemas.messages import AgentMessage, ToolCall
        from .primitives import AgentResult
        from .session import Session
        
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
                
        except Exception as e:
            logger.exception(f"Agent handler error: {e}")
            return AgentMessage(content=f"Error: {str(e)}")
    
    def invoke_stream(self, messages: dict):
        """
        Handle a streaming chat request.
        
        For now, wraps the sync call. Users can implement
        streaming in their handler by returning a generator.
        """
        from ..schemas.events import TextDeltaEvent, DoneEvent, ErrorEvent
        
        try:
            result = self.invoke(messages)
            
            # Emit the text content
            if result.content:
                yield TextDeltaEvent(text=result.content)
            
            yield DoneEvent()
            
        except Exception as e:
            yield ErrorEvent(error=str(e))
    
    def _simplify_messages(self, messages_list: list) -> list[dict]:
        """Convert to simple format for user's handler."""
        simple = []
        for msg in messages_list:
            simple.append({
                "role": msg.get("role"),
                "content": msg.get("content", ""),
            })
        return simple
    
    def _extract_context(self, messages_list: list) -> dict:
        """Extract platform context from the latest user message."""
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                ctx = msg.get("platform_context", {})
                if ctx:
                    if hasattr(ctx, "model_dump"):
                        return ctx.model_dump()
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
                approved.append({
                    "id": tc.get("id"),
                    "name": tc.get("name"),
                    "input": tc.get("input", {}),
                })
        
        return approved
