from typing import Protocol, runtime_checkable, Dict, Any, List 
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
from .schemas.messages import AgentMessage, Messages
import logging
import os
import traceback
from .channel_routing import ChannelResponseRouter, SlackResponseRouter

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
    # ONE-LINER guardrail — fails fast if agent doesn’t meet the protocol
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

    # ----- chat endpoint -----------------------------------------------------
    @app.post("/api/sendMessage", response_model=AgentMessage, tags=["chat"])
    def send_message(raw_body: Dict[str, Any] = Body(...)) -> AgentMessage:

       
        # log request body
        logger.info("Request Body:")
        logger.info(str(raw_body))

        source = raw_body.get("source", "No Source Provided. Defaulting to 'help-desk'")
        logger.info("Request Source: %s", source)

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
            logger.info("Invoking agent with messages: %s", msgs_obj)
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
        
        # Validate
        if "messages" not in raw_body:
            raise HTTPException(status_code=400, detail="'messages' field missing")
        
        try:
            msgs_obj = Messages.model_validate({"messages": raw_body["messages"]})
        except ValidationError as ve:
            raise HTTPException(status_code=422, detail=ve.errors())
        
        # Generator function
        def event_generator():
            try:
                for event in agent.invoke_stream(msgs_obj.model_dump()):
                    yield event.model_dump_json() + '\n'
            except Exception as e:
                logger.error("Stream error: %s", str(e), exc_info=True)
                error_event = ErrorEvent(error=str(e))
                yield error_event.model_dump_json() + '\n'
        
        return StreamingResponse(
            event_generator(),
            media_type='application/x-ndjson'
        )

    return app
