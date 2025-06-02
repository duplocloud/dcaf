from agent_server import AgentProtocol
from schemas.messages import Messages, AgentMessage


class EchoAgent(AgentProtocol):
    def invoke(self, messages: Messages) -> AgentMessage:
        last_user = next((m for m in reversed(messages.messages) if m.role == "user"), None)
        text = last_user.content if last_user else "I heard nothing."
        return AgentMessage(content=f"Echo: {text}")