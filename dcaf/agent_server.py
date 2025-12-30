from typing import Protocol, runtime_checkable, Dict, Any, List 
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
from .schemas.messages import AgentMessage, Messages
from .schemas.events import DoneEvent, ErrorEvent
import logging
import os
import traceback
import asyncio
from .channel_routing import ChannelResponseRouter, SlackResponseRouter
from fastapi.responses import StreamingResponse

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

@runtime_checkable            
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage: ...


def create_chat_app(agent: AgentProtocol, router: ChannelResponseRouter = None) -> FastAPI:
    # ONE-LINER guardrail — fails fast if agent doesn't meet the protocol
    if not isinstance(agent, AgentProtocol):
        raise TypeError(    
            "Agent must satisfy AgentProtocol "
            "(missing .invoke(messages: Messages) -> Message, perhaps?)"
        )

    app = FastAPI(title="DuploCloud Chat Service", version="0.1.0")

    # ----- health check ------------------------------------------------------
    # Health check is sync and fast - never blocked by LLM calls
    @app.get("/health", tags=["system"])
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    # ----- shared logic for chat endpoints -----------------------------------
    async def _handle_chat(raw_body: Dict[str, Any]) -> AgentMessage:
        """
        Shared async handler for chat endpoints.
        
        Runs the agent in a thread pool so LLM calls don't block
        the event loop (which would block health checks).
        """
        # log request body
        logger.info("Request Body:")
        logger.info(str(raw_body))

        source = raw_body.get("source")
        logger.info("Request Source: %s", source if source else "No Source Provided. Defaulting to 'help-desk'")

        if source == "slack":
            if router:
                should_respond = router.should_agent_respond(
                    raw_body["messages"]
                )
                if not should_respond["should_respond"]:
                    return AgentMessage(
                        role="assistant",
                        content=""
                    )

        # 1. validate presence of 'messages'
        if "messages" not in raw_body:
            raise HTTPException(status_code=400,
                                detail="'messages' field missing from request body")

        try:
            msgs_obj = Messages.model_validate({"messages": raw_body["messages"]})
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=ve.errors())

        # 2. delegate to agent (run in thread pool to not block event loop)
        try:
            msgs_obj = msgs_obj.model_dump()
            logger.info("Invoking agent with messages: %s", msgs_obj)
            
            # Run sync agent.invoke() in a thread pool
            # This prevents blocking the event loop so health checks stay responsive
            assistant_msg = await asyncio.to_thread(agent.invoke, msgs_obj)

            logger.info("Assistant message: %s", assistant_msg)

            # Still validate the response format
            assistant_msg = AgentMessage.model_validate(assistant_msg)  # schema guardrail

            return assistant_msg

        except ValidationError as ve:
            logger.error("Validation error in agent: %s", ve)
            raise HTTPException(status_code=500,
                                detail=f"Agent returned invalid Message: {ve}")

        except Exception as e:
            traceback_error = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error("Unhandled exception in agent:\n%s", traceback_error)
            raise HTTPException(status_code=500, detail=str(e))

    # ----- NEW: /api/chat endpoint (preferred) -------------------------------
    @app.post("/api/chat", response_model=AgentMessage, tags=["chat"])
    async def chat(raw_body: Dict[str, Any] = Body(...)) -> AgentMessage:
        """
        Chat endpoint (async).
        
        Send a message to the agent and get a response.
        LLM calls run in a thread pool so they don't block health checks.
        """
        return await _handle_chat(raw_body)

    # ----- LEGACY: /api/sendMessage endpoint (backwards compatible) ----------
    @app.post("/api/sendMessage", response_model=AgentMessage, tags=["chat", "legacy"])
    async def send_message(raw_body: Dict[str, Any] = Body(...)) -> AgentMessage:
        """
        Legacy chat endpoint (async).
        
        DEPRECATED: Use /api/chat instead.
        Kept for backwards compatibility with existing integrations.
        """
        return await _handle_chat(raw_body)

    # ----- shared logic for stream endpoints ---------------------------------
    async def _handle_stream(raw_body: Dict[str, Any]):
        """
        Shared async handler for streaming endpoints.
        
        Returns a StreamingResponse with NDJSON events.
        """
        logger.info("Stream Request Body: %s", raw_body)

        source = raw_body.get("source")
        logger.info("Request Source: %s", source if source else "No Source Provided. Defaulting to 'help-desk'")

        if source == "slack":
            if router:
                should_respond = router.should_agent_respond(
                    raw_body["messages"]
                )
                if not should_respond["should_respond"]:
                    async def done_generator():
                        yield DoneEvent().model_dump_json() + '\n'
                    return StreamingResponse(
                        done_generator(),
                        media_type='application/x-ndjson'
                    )
        
        # Validate
        if "messages" not in raw_body:
            raise HTTPException(status_code=400, detail="'messages' field missing")
        
        try:
            msgs_obj = Messages.model_validate({"messages": raw_body["messages"]})
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=ve.errors())
        
        # Async generator function that yields events
        async def event_generator():
            try:
                # Run the sync invoke_stream in a thread pool
                def run_stream():
                    return list(agent.invoke_stream(msgs_obj.model_dump()))
                
                events = await asyncio.to_thread(run_stream)
                for event in events:
                    yield event.model_dump_json() + '\n'
            except Exception as e:
                logger.error("Stream error: %s", str(e), exc_info=True)
                error_event = ErrorEvent(error=str(e))
                yield error_event.model_dump_json() + '\n'
        
        return StreamingResponse(
            event_generator(),
            media_type='application/x-ndjson'
        )

    # ----- NEW: /api/chat-stream endpoint (preferred) ------------------------
    @app.post("/api/chat-stream", tags=["chat"])
    async def chat_stream(raw_body: Dict[str, Any] = Body(...)):
        """
        Streaming chat endpoint (async).
        
        Stream agent response as NDJSON events.
        LLM calls run in a thread pool so they don't block health checks.
        """
        return await _handle_stream(raw_body)

    # ----- LEGACY: /api/sendMessageStream endpoint (backwards compatible) ----
    @app.post("/api/sendMessageStream", tags=["chat", "legacy"])
    async def send_message_stream(raw_body: Dict[str, Any] = Body(...)):
        """
        Legacy streaming endpoint (async).
        
        DEPRECATED: Use /api/chat-stream instead.
        Kept for backwards compatibility with existing integrations.
        """
        return await _handle_stream(raw_body)

    return app
