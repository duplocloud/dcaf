from typing import Protocol, runtime_checkable, Dict, Any, List 
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
from .schemas.messages import AgentMessage, Messages
from src.middleware.request_id import RequestIdMiddleware
from src.middleware.user_context import UserContextMiddleware
import logging
import os
import traceback

# Centralised logging
from src.utils.logger import get_logger

# Ensure root logger configured once
logger = get_logger(__name__)

@runtime_checkable            
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage: ...


def create_chat_app(agent: AgentProtocol) -> FastAPI:
    # ONE-LINER guardrail — fails fast if agent doesn’t meet the protocol
    if not isinstance(agent, AgentProtocol):
        raise TypeError(
            "Agent must satisfy AgentProtocol "
            "(missing .invoke(messages: Messages) -> Message, perhaps?)"
        )

    app = FastAPI(title="DuploCloud Chat Service", version="0.1.0")

    # Middleware to attach correlation IDs
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(UserContextMiddleware)

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

    return app
