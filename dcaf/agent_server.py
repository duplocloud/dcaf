import asyncio
import inspect
import json
import logging
import os
import traceback
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
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
    """
    Any agent that can respond to a chat.

    Required:
        invoke(): Synchronous or async method to process messages and return a response.

    Optional:
        invoke_stream(): If implemented, enables streaming endpoints. If not implemented,
                        streaming endpoints will fall back to invoke() and wrap the
                        response in stream events.
    """

    def invoke(self, messages: dict[str, list[dict[str, Any]]]) -> AgentMessage: ...


def create_chat_app(
    agent: AgentProtocol,
    router: ChannelResponseRouter | None = None,
    a2a_agent_card_path: str | None = None,
) -> FastAPI:
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

    # ----- agent card (A2A) --------------------------------------------------
    if a2a_agent_card_path:
        card_path = Path(a2a_agent_card_path)

        @app.get("/.well-known/agent.json", tags=["system"])
        def get_agent_card() -> dict[str, Any]:
            """
            Serves the Agent2Agent agent card JSON.
            https://agent2agent.info/docs/concepts/agentcard/
            """
            if not card_path.exists() or not card_path.is_file():
                raise HTTPException(
                    status_code=404,
                    detail=f"Agent card not found at path: {card_path}",
                )

            try:
                raw = card_path.read_text(encoding="utf-8")
                return json.loads(raw)
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in agent card file %s: %s", card_path, str(e))
                raise HTTPException(
                    status_code=500,
                    detail=f"Invalid JSON in agent card file: {card_path}",
                )
            except Exception as e:
                logger.error("Failed reading agent card file %s: %s", card_path, str(e))
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed reading agent card file: {card_path}",
                )

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

            # Extract thread_id for v1 backwards compatibility
            thread_id = request_fields.get("thread_id")

            # Check if agent's invoke method accepts thread_id parameter (v1 pattern)
            sig = inspect.signature(agent.invoke)
            accepts_thread_id = "thread_id" in sig.parameters

            # If the agent's invoke is async, await it directly;
            # otherwise run it in a thread pool so it doesn't block the event loop.
            if inspect.iscoroutinefunction(agent.invoke):
                if accepts_thread_id:
                    assistant_msg = await agent.invoke(msgs_dict, thread_id=thread_id)
                else:
                    assistant_msg = await agent.invoke(msgs_dict)
            else:
                if accepts_thread_id:
                    assistant_msg = await asyncio.to_thread(agent.invoke, msgs_dict, thread_id=thread_id)
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
    def _has_invoke_stream() -> bool:
        """Check if the agent has an invoke_stream method."""
        return hasattr(agent, "invoke_stream") and callable(getattr(agent, "invoke_stream", None))

    async def _handle_stream(raw_body: dict[str, Any]):
        """
        Shared async handler for streaming endpoints.

        Returns a StreamingResponse with NDJSON events.

        If the agent doesn't implement invoke_stream(), falls back to invoke()
        and wraps the response in stream events for backwards compatibility.
        """
        from .schemas.events import TextDeltaEvent

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

        # Extract thread_id for v1 backwards compatibility
        thread_id = request_fields.get("thread_id")

        # Async generator function that yields events
        async def event_generator():
            try:
                # Check if agent has invoke_stream method
                if _has_invoke_stream():
                    # Check if invoke_stream accepts thread_id (v1 pattern)
                    sig = inspect.signature(agent.invoke_stream)
                    accepts_thread_id = "thread_id" in sig.parameters

                    if inspect.iscoroutinefunction(agent.invoke_stream) or inspect.isasyncgenfunction(agent.invoke_stream):
                        # Async streaming: await each event directly
                        if accepts_thread_id:
                            async for event in agent.invoke_stream(msgs_dict, thread_id=thread_id):
                                yield event.model_dump_json() + "\n"
                        else:
                            async for event in agent.invoke_stream(msgs_dict):
                                yield event.model_dump_json() + "\n"
                    else:
                        # Sync streaming: run in thread pool
                        if accepts_thread_id:
                            def run_stream():
                                return list(agent.invoke_stream(msgs_dict, thread_id=thread_id))
                        else:
                            def run_stream():
                                return list(agent.invoke_stream(msgs_dict))

                        events = await asyncio.to_thread(run_stream)
                        for event in events:
                            yield event.model_dump_json() + "\n"
                else:
                    # Fallback: agent doesn't have invoke_stream, use invoke() instead
                    # and wrap the response in stream events
                    logger.debug("Agent doesn't have invoke_stream, falling back to invoke()")

                    # Check if invoke accepts thread_id (v1 pattern)
                    sig = inspect.signature(agent.invoke)
                    accepts_thread_id = "thread_id" in sig.parameters

                    if inspect.iscoroutinefunction(agent.invoke):
                        if accepts_thread_id:
                            response = await agent.invoke(msgs_dict, thread_id=thread_id)
                        else:
                            response = await agent.invoke(msgs_dict)
                    else:
                        if accepts_thread_id:
                            response = await asyncio.to_thread(agent.invoke, msgs_dict, thread_id=thread_id)
                        else:
                            response = await asyncio.to_thread(agent.invoke, msgs_dict)

                    # Wrap response in stream events
                    response = AgentMessage.model_validate(response)
                    if response.content:
                        yield TextDeltaEvent(text=response.content).model_dump_json() + "\n"
                    yield DoneEvent().model_dump_json() + "\n"

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

    # ----- LEGACY: /api/sendMessage endpoint (deprecated) --------------------
    # Per ADR-007, these endpoints are preserved for backwards compatibility
    # with existing clients. New integrations should use /api/chat instead.
    @app.post("/api/sendMessage", response_model=AgentMessage, tags=["chat"], deprecated=True)
    async def send_message_legacy(raw_body: dict[str, Any] = Body(...)) -> AgentMessage:
        """
        Legacy chat endpoint (deprecated).

        .. deprecated::
            Use ``/api/chat`` instead. This endpoint is maintained for
            backwards compatibility with existing clients.
        """
        return await _handle_chat(raw_body)

    # ----- LEGACY: /api/sendMessageStream endpoint (deprecated) --------------
    @app.post("/api/sendMessageStream", tags=["chat"], deprecated=True)
    async def send_message_stream_legacy(raw_body: dict[str, Any] = Body(...)):
        """
        Legacy streaming chat endpoint (deprecated).

        .. deprecated::
            Use ``/api/chat-stream`` instead. This endpoint is maintained for
            backwards compatibility with existing clients.
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

                # Extract thread_id for v1 backwards compatibility
                thread_id = request_fields.get("thread_id")

                # Stream response events
                try:
                    from .schemas.events import TextDeltaEvent

                    if _has_invoke_stream():
                        # Check if invoke_stream accepts thread_id (v1 pattern)
                        sig = inspect.signature(agent.invoke_stream)
                        accepts_thread_id = "thread_id" in sig.parameters

                        if inspect.iscoroutinefunction(agent.invoke_stream) or inspect.isasyncgenfunction(agent.invoke_stream):
                            if accepts_thread_id:
                                async for event in agent.invoke_stream(msgs_dict, thread_id=thread_id):
                                    await websocket.send_text(event.model_dump_json())
                            else:
                                async for event in agent.invoke_stream(msgs_dict):
                                    await websocket.send_text(event.model_dump_json())
                        else:
                            if accepts_thread_id:
                                def run_stream():
                                    return list(agent.invoke_stream(msgs_dict, thread_id=thread_id))
                            else:
                                def run_stream():
                                    return list(agent.invoke_stream(msgs_dict))

                            events = await asyncio.to_thread(run_stream)
                            for event in events:
                                await websocket.send_text(event.model_dump_json())
                    else:
                        # Fallback: agent doesn't have invoke_stream, use invoke()
                        logger.debug("Agent doesn't have invoke_stream, falling back to invoke()")

                        # Check if invoke accepts thread_id (v1 pattern)
                        sig = inspect.signature(agent.invoke)
                        accepts_thread_id = "thread_id" in sig.parameters

                        if inspect.iscoroutinefunction(agent.invoke):
                            if accepts_thread_id:
                                response = await agent.invoke(msgs_dict, thread_id=thread_id)
                            else:
                                response = await agent.invoke(msgs_dict)
                        else:
                            if accepts_thread_id:
                                response = await asyncio.to_thread(agent.invoke, msgs_dict, thread_id=thread_id)
                            else:
                                response = await asyncio.to_thread(agent.invoke, msgs_dict)

                        response = AgentMessage.model_validate(response)
                        if response.content:
                            await websocket.send_text(TextDeltaEvent(text=response.content).model_dump_json())
                        await websocket.send_text(DoneEvent().model_dump_json())
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
