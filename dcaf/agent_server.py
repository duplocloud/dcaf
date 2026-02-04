import asyncio
import inspect
import json
import logging
import os
import traceback
from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol, runtime_checkable

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .channel_routing import ChannelResponseRouter
from .schemas.events import DoneEvent, ErrorEvent
from .schemas.messages import AgentMessage, Messages

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""

    def invoke(self, messages: dict[str, list[dict[str, Any]]]) -> AgentMessage: ...

    def invoke_stream(self, messages: dict[str, Any]) -> Iterator[Any]: ...


def create_chat_app(agent: AgentProtocol, router: ChannelResponseRouter | None = None) -> FastAPI:
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
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ----- shared logic for chat endpoints -----------------------------------
    async def _handle_chat(raw_body: dict[str, Any]) -> AgentMessage:
        """
        Shared async handler for chat endpoints.

        Runs the agent in a thread pool so LLM calls don't block
        the event loop (which would block health checks).
        """
        # log request body
        logger.info("Request Body:")
        logger.info(str(raw_body))

        source = raw_body.get("source")
        logger.info(
            "Request Source: %s",
            source if source else "No Source Provided. Defaulting to 'help-desk'",
        )

        if source == "slack" and router:
            should_respond = router.should_agent_respond(raw_body["messages"])
            if not should_respond["should_respond"]:
                return AgentMessage(role="assistant", content="")

        # 1. validate presence of 'messages'
        if "messages" not in raw_body:
            raise HTTPException(
                status_code=400, detail="'messages' field missing from request body"
            )

        try:
            msgs_obj = Messages.model_validate({"messages": raw_body["messages"]})
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=ve.errors()) from ve

        # 2. delegate to agent (run in thread pool to not block event loop)
        try:
            msgs_dict = msgs_obj.model_dump()

            # Forward top-level request fields (thread_id, tenant_id, source, etc.)
            # so adapters can merge them into the agent context
            request_fields = {k: v for k, v in raw_body.items() if k != "messages"}
            msgs_dict["_request_fields"] = request_fields

            logger.info("Invoking agent with messages: %s", msgs_dict)

            # If the agent's invoke is async, await it directly;
            # otherwise run it in a thread pool so it doesn't block the event loop.
            if inspect.iscoroutinefunction(agent.invoke):
                assistant_msg = await agent.invoke(msgs_dict)
            else:
                assistant_msg = await asyncio.to_thread(agent.invoke, msgs_dict)

            logger.info("Assistant message: %s", assistant_msg)

            # Still validate the response format
            assistant_msg = AgentMessage.model_validate(assistant_msg)  # schema guardrail

            # Echo top-level request fields back for client correlation
            if request_fields:
                assistant_msg.meta_data["request_context"] = request_fields

            return assistant_msg

        except ValidationError as ve:
            logger.error("Validation error in agent: %s", ve)
            raise HTTPException(
                status_code=500, detail=f"Agent returned invalid Message: {ve}"
            ) from ve

        except Exception as e:
            traceback_error = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error("Unhandled exception in agent:\n%s", traceback_error)
            raise HTTPException(status_code=500, detail=str(e)) from e

    # ----- NEW: /api/chat endpoint (preferred) -------------------------------
    @app.post("/api/chat", response_model=AgentMessage, tags=["chat"])
    async def chat(raw_body: dict[str, Any] = Body(...)) -> AgentMessage:
        """
        Chat endpoint (async).

        Send a message to the agent and get a response.
        LLM calls run in a thread pool so they don't block health checks.
        """
        return await _handle_chat(raw_body)

    # ----- shared logic for stream endpoints ---------------------------------
    async def _handle_stream(raw_body: dict[str, Any]):
        """
        Shared async handler for streaming endpoints.

        Returns a StreamingResponse with NDJSON events.
        """
        logger.info("Stream Request Body: %s", raw_body)

        source = raw_body.get("source")
        logger.info(
            "Request Source: %s",
            source if source else "No Source Provided. Defaulting to 'help-desk'",
        )

        if source == "slack" and router:
            should_respond = router.should_agent_respond(raw_body["messages"])
            if not should_respond["should_respond"]:

                async def done_generator():
                    yield DoneEvent().model_dump_json() + "\n"

                return StreamingResponse(done_generator(), media_type="application/x-ndjson")

        # Validate
        if "messages" not in raw_body:
            raise HTTPException(status_code=400, detail="'messages' field missing")

        try:
            msgs_obj = Messages.model_validate({"messages": raw_body["messages"]})
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=ve.errors()) from ve

        # Forward top-level request fields (thread_id, tenant_id, source, etc.)
        msgs_dict = msgs_obj.model_dump()
        request_fields = {k: v for k, v in raw_body.items() if k != "messages"}
        msgs_dict["_request_fields"] = request_fields

        # Async generator function that yields events
        async def event_generator():
            try:
                if inspect.iscoroutinefunction(agent.invoke_stream) or inspect.isasyncgenfunction(agent.invoke_stream):
                    # Async streaming: await each event directly
                    async for event in agent.invoke_stream(msgs_dict):
                        yield event.model_dump_json() + "\n"
                else:
                    # Sync streaming: run in thread pool
                    def run_stream():
                        return list(agent.invoke_stream(msgs_dict))

                    events = await asyncio.to_thread(run_stream)
                    for event in events:
                        yield event.model_dump_json() + "\n"
            except Exception as e:
                logger.error("Stream error: %s", str(e), exc_info=True)
                error_event = ErrorEvent(error=str(e))
                yield error_event.model_dump_json() + "\n"

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    # ----- NEW: /api/chat-stream endpoint (preferred) ------------------------
    @app.post("/api/chat-stream", tags=["chat"])
    async def chat_stream(raw_body: dict[str, Any] = Body(...)):
        """
        Streaming chat endpoint (async).

        Stream agent response as NDJSON events.
        LLM calls run in a thread pool so they don't block health checks.
        """
        return await _handle_stream(raw_body)

    # ----- WebSocket: /api/chat-ws endpoint ------------------------------------
    @app.websocket("/api/chat-ws")
    async def chat_ws(websocket: WebSocket):
        """
        Bidirectional streaming chat over WebSocket.

        Each client text frame is a JSON object with the same shape as the HTTP
        endpoints (``{"messages": [...]}``) representing one conversation turn.
        The server streams back ``StreamEvent`` JSON frames, ending each turn
        with a ``DoneEvent``.  The connection stays open for multiple turns.
        """
        await websocket.accept()

        try:
            while True:
                raw_text = await websocket.receive_text()

                # Parse JSON
                try:
                    raw_body = json.loads(raw_text)
                except json.JSONDecodeError as e:
                    await websocket.send_text(ErrorEvent(error=f"Invalid JSON: {e}").model_dump_json())
                    continue

                # Validate messages field
                if "messages" not in raw_body:
                    await websocket.send_text(ErrorEvent(error="'messages' field missing").model_dump_json())
                    continue

                try:
                    msgs_obj = Messages.model_validate({"messages": raw_body["messages"]})
                except ValidationError as ve:
                    await websocket.send_text(ErrorEvent(error=str(ve.errors())).model_dump_json())
                    continue

                # Forward top-level request fields (thread_id, tenant_id, source, etc.)
                msgs_dict = msgs_obj.model_dump()
                request_fields = {k: v for k, v in raw_body.items() if k != "messages"}
                msgs_dict["_request_fields"] = request_fields

                # Stream response events
                try:
                    if inspect.iscoroutinefunction(agent.invoke_stream) or inspect.isasyncgenfunction(agent.invoke_stream):
                        async for event in agent.invoke_stream(msgs_dict):
                            await websocket.send_text(event.model_dump_json())
                    else:
                        def run_stream():
                            return list(agent.invoke_stream(msgs_dict))

                        events = await asyncio.to_thread(run_stream)
                        for event in events:
                            await websocket.send_text(event.model_dump_json())
                except Exception as e:
                    logger.error("WebSocket stream error: %s", str(e), exc_info=True)
                    await websocket.send_text(ErrorEvent(error=str(e)).model_dump_json())

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error("WebSocket connection error: %s", str(e), exc_info=True)
            try:
                await websocket.send_text(ErrorEvent(error=str(e)).model_dump_json())
                await websocket.close(code=1011, reason=str(e))
            except Exception:
                pass

    return app
