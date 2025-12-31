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
    from dcaf.core import serve
    from dcaf.core.primitives import llm, AgentResult
    
    def my_agent(messages: list, context: dict) -> AgentResult:
        response = llm.call(messages)
        return AgentResult(text=response.text)
    
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

if TYPE_CHECKING:
    from .agent import Agent
    from fastapi import APIRouter

logger = logging.getLogger(__name__)

# Type for agent handlers
AgentHandler = Callable[[list, dict], "AgentResult"]


def serve(
    agent: Union["Agent", AgentHandler],
    port: int = 8000,
    host: str = "0.0.0.0",
    reload: bool = False,
    log_level: str = "info",
    additional_routers: Sequence["APIRouter"] | None = None,
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
        additional_routers: Optional list of FastAPI APIRouter instances to include.
                           Use this to add custom endpoints beyond /api/chat.
        
    Endpoints:
        GET  /health           - Health check
        POST /api/chat         - Synchronous chat (async, non-blocking)
        POST /api/chat-stream  - Streaming chat (NDJSON, async)
        
        Legacy (backwards compatible):
        POST /api/sendMessage       - Alias for /api/chat
        POST /api/sendMessageStream - Alias for /api/chat-stream
        
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
        
    Note:
        This function blocks until the server is stopped (Ctrl+C).
        For programmatic control, use create_app() instead.
    """
    import uvicorn
    
    # Create the FastAPI app
    app = create_app(agent, additional_routers=additional_routers)
    
    logger.info(f"Starting DCAF server at http://{host}:{port}")
    logger.info("Endpoints:")
    logger.info(f"  GET  http://{host}:{port}/health")
    logger.info(f"  POST http://{host}:{port}/api/chat")
    logger.info(f"  POST http://{host}:{port}/api/chat-stream")
    if additional_routers:
        logger.info(f"  + {len(additional_routers)} custom router(s)")
    
    # Run the server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


def create_app(
    agent: Union["Agent", AgentHandler],
    additional_routers: Sequence["APIRouter"] | None = None,
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


class CallableAdapter:
    """
    Adapts a callable function to work with the FastAPI server.
    
    This allows users to write custom agent functions without
    using the Agent class.
    """
    
    def __init__(self, handler: AgentHandler):
        self.handler = handler
    
    def invoke(self, messages: dict) -> "AgentMessage":
        """
        Handle a synchronous chat request.
        
        Calls the user's handler function and converts the result
        to the HelpDesk protocol format.
        """
        from ..schemas.messages import AgentMessage, ToolCall
        from .primitives import AgentResult
        
        # Extract messages and context
        messages_list = messages.get("messages", [])
        context = self._extract_context(messages_list)
        
        # Add approved tool calls to context if present
        approved = self._extract_approved_tools(messages_list)
        if approved:
            context["approved_tool_calls"] = approved
        
        # Convert to simple format for user's handler
        simple_messages = self._simplify_messages(messages_list)
        
        # Call user's handler
        try:
            result = self.handler(simple_messages, context)
            
            # Handle different return types
            if isinstance(result, AgentResult):
                return self._result_to_message(result)
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
    
    def _result_to_message(self, result: "AgentResult") -> "AgentMessage":
        """Convert AgentResult to AgentMessage."""
        from ..schemas.messages import AgentMessage, ToolCall
        
        msg = AgentMessage(content=result.text)
        
        # Add pending tool calls
        for pending in result.pending_tools:
            msg.data.tool_calls.append(ToolCall(
                id=pending.id,
                name=pending.name,
                input=pending.input,
                tool_description=pending.description,
                intent=pending.intent,
                input_description={},
                execute=False,
            ))
        
        # Add executed tool calls
        for executed in result.executed_tools:
            from ..schemas.messages import ExecutedToolCall
            msg.data.executed_tool_calls.append(ExecutedToolCall(
                id=executed.id,
                name=executed.name,
                input=executed.input,
                output=executed.output,
            ))
        
        return msg
