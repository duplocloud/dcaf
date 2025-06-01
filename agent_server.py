from typing import Protocol, runtime_checkable, Dict, Any  # 👈 import decorator
from fastapi import FastAPI, HTTPException, Body
from pydantic import ValidationError
from schemas.messages import Messages, Message


@runtime_checkable            
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""
    def invoke(self, messages: Messages) -> Message: ...
    # (If you add more required methods later, this check auto-updates.)


def create_chat_app(agent: AgentProtocol) -> FastAPI:
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
    @app.post("/api/sendMessage", response_model=Message, tags=["chat"])
    def send_message(raw_body: Dict[str, Any] = Body(...)) -> Message:
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
            assistant_msg = agent.invoke(msgs_obj)
            assistant_msg = Message.model_validate(assistant_msg)  # schema guardrail

            if assistant_msg.role != "assistant":
                raise ValueError("Agent must return a Message with role='assistant'")

            return assistant_msg

        except ValidationError as ve:
            raise HTTPException(status_code=500,
                                detail=f"Agent returned invalid Message: {ve}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app
