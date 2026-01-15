from typing import Protocol, runtime_checkable, Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
from .schemas.messages import AgentMessage, Messages
from .schemas.events import DoneEvent, ErrorEvent
import logging
import os
import traceback
from .channel_routing import ChannelResponseRouter, SlackResponseRouter
from fastapi.responses import StreamingResponse
import inspect
import json
from pathlib import Path

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(levelname)s | %(asctime)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

@runtime_checkable            
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]], thread_id: Optional[str] = None) -> AgentMessage: ...


def create_chat_app(
    agent: AgentProtocol,
    router: ChannelResponseRouter = None,
    a2a_agent_card_path: Optional[str] = None,
) -> FastAPI:
    # ONE-LINER guardrail — fails fast if agent doesn't meet the protocol
    if not isinstance(agent, AgentProtocol):
        raise TypeError(    
            "Agent must satisfy AgentProtocol "
            "(missing .invoke(messages: Messages) -> Message, perhaps?)"
        )

    app = FastAPI(title="DuploCloud Chat Service", version="0.1.0")

    # ----- health check ------------------------------------------------------
    @app.get("/health", tags=["system"])
    def health() -> Dict[str, str]:
        return {"status": "ok"}

    # ----- agent card (A2A) --------------------------------------------------
    if a2a_agent_card_path:
        card_path = Path(a2a_agent_card_path)

        @app.get("/.well-known/agent.json", tags=["system"])
        def get_agent_card() -> Dict[str, Any]:
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
        
    # ----- chat endpoint -----------------------------------------------------
    @app.post("/api/sendMessage", response_model=AgentMessage, tags=["chat"])
    def send_message(raw_body: Dict[str, Any] = Body(...)) -> AgentMessage:

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

        # 2. delegate to agent
        try:
            # Pass the raw messages dictionary directly to the agent
            msgs_obj = msgs_obj.model_dump()
            
            # Extract thread_id from raw_body if present
            thread_id = raw_body.get("thread_id")
            
            # Check if the agent's invoke method accepts thread_id parameter
            sig = inspect.signature(agent.invoke)
            if "thread_id" in sig.parameters:
                logger.info("Invoking agent with messages and thread_id: %s", thread_id)
                assistant_msg = agent.invoke(msgs_obj, thread_id=thread_id)
            else:
                logger.info("Invoking agent with messages (no thread_id support)")
                assistant_msg = agent.invoke(msgs_obj)

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
    
    #----- stream chat endpoint -----------------------------------------------------
    @app.post("/api/sendMessageStream", tags=["chat"])
    def send_message_stream(raw_body: Dict[str, Any] = Body(...)):
        """Stream response as NDJSON"""
        
        logger.info("Stream Request Body: %s", raw_body)

        source = raw_body.get("source")
        logger.info("Request Source: %s", source if source else "No Source Provided. Defaulting to 'help-desk'")

        if source == "slack":
            if router:
                should_respond = router.should_agent_respond(
                    raw_body["messages"]
                )
                if not should_respond["should_respond"]:
                    #return done event using StreamingResponse
                    def done_generator():
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
        
        # Extract thread_id from raw_body if present
        thread_id = raw_body.get("thread_id")
        
        # Generator function
        def event_generator():
            # Accumulate events for logging
            text_parts = []
            event_counts = {}
            executed_commands = []
            executed_tool_calls = []
            tool_calls = []
            commands = []
            stop_reason = None

            try:
                # Check if the agent's invoke_stream method accepts thread_id parameter
                sig = inspect.signature(agent.invoke_stream)
                if "thread_id" in sig.parameters:
                    logger.info("Invoking stream agent with messages and thread_id: %s", thread_id)
                    event_stream = agent.invoke_stream(msgs_obj.model_dump(), thread_id=thread_id)
                else:
                    logger.info("Invoking stream agent with messages (no thread_id support)")
                    event_stream = agent.invoke_stream(msgs_obj.model_dump())

                for event in event_stream:
                    event_type = event.type
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1

                    # Accumulate data based on event type
                    if event_type == "text_delta":
                        text_parts.append(event.text)
                    elif event_type == "executed_commands":
                        executed_commands.extend(event.executed_cmds)
                    elif event_type == "executed_tool_calls":
                        executed_tool_calls.extend(event.executed_tool_calls)
                    elif event_type == "tool_calls":
                        tool_calls.extend(event.tool_calls)
                    elif event_type == "commands":
                        commands.extend(event.commands)
                    elif event_type == "done":
                        stop_reason = event.stop_reason

                    yield event.model_dump_json() + '\n'

                # Log final aggregated response
                logger.info("Stream completed - Event counts: %s", event_counts)
                if text_parts:
                    full_text = ''.join(text_parts)
                    logger.info("Streamed assistant message: %s", f'{full_text}')
                if executed_tool_calls:
                    logger.info("Executed tool calls: %s", executed_tool_calls)
                if tool_calls:
                    logger.info("Tool calls requested: %s", tool_calls)
                if commands:
                    logger.info("Commands requested: %s", commands)
                if stop_reason:
                    logger.info("Stop reason: %s", stop_reason)

            except Exception as e:
                logger.error("Stream error: %s", str(e), exc_info=True)
                error_event = ErrorEvent(error=str(e))
                yield error_event.model_dump_json() + '\n'
        
        return StreamingResponse(
            event_generator(),
            media_type='application/x-ndjson'
        )

    return app