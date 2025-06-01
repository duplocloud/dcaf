"""
Run with:   python main.py
Or `uvicorn main:app --port 8000` if you prefer the CLI).
"""

from agent_server import create_chat_app, AgentProtocol
from schemas.messages import Message, Messages


class EchoAgent(AgentProtocol)  :
    def invoke(self, messages: Messages) -> Message:
        last_user = next((m for m in reversed(messages.messages) if m.role == "user"), None)
        text = last_user.content if last_user else "I heard nothing."
        return Message(role="assistant", content=f"Echo: {text}")


app = create_chat_app(EchoAgent())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,     # set True for auto-reload in dev
        log_level="info",
    )
