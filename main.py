"""
Run with:   python main.py
Or `uvicorn main:app --port 8000` if you prefer the CLI.
"""

from agent_server import create_chat_app, AgentProtocol
from schemas.messages import Messages, AgentMessage


class EchoAgent(AgentProtocol):
    def invoke(self, messages: Messages) -> AgentMessage:
        last_user = next((m for m in reversed(messages.messages) if m.role == "user"), None)
        text = last_user.content if last_user else "I heard nothing."
        return AgentMessage(content=f"Echo: {text}")


app = create_chat_app(EchoAgent())


if __name__ == "__main__":
    import uvicorn

    # For reload to work, we need to use an import string instead of the app object
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,     # set True for auto-reload in dev
        log_level="info",
    )
