from agent_server import AgentProtocol
from schemas.messages import Messages, AgentMessage
from llm import BedrockAnthropicLLM
import os

class LLMPassthroughAgent(AgentProtocol):
    def __init__(self, llm: BedrockAnthropicLLM):
        self.llm = llm
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")

    def call_bedrock_anthropic_llm(self, messages: list):
        return self.llm.invoke(messages = messages, model_id = self.model_id)

    def preprocess_messages(self, messages: Messages):
        preprocessed_messages = []
        for message in messages:
            if message["role"] == "user":
                preprocessed_messages.append({"role": "user", "content": message["content"]})
            elif message["role"] == "assistant":
                preprocessed_messages.append({"role": "assistant", "content": message["content"]})
        return preprocessed_messages
        
    def invoke(self, messages: Messages) -> AgentMessage:

        preprocessed_messages = self.preprocess_messages(messages)
        content = self.call_bedrock_anthropic_llm(messages = preprocessed_messages)
        return AgentMessage(content=content)