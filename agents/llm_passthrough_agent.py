from typing import Dict, Any, List
from agent_server import AgentProtocol
from schemas.messages import AgentMessage
from services.llm import BedrockAnthropicLLM
import os

class LLMPassthroughAgent(AgentProtocol):
    def __init__(self, llm: BedrockAnthropicLLM):
        self.llm = llm
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0")

    def call_bedrock_anthropic_llm(self, messages: list):
        return self.llm.invoke(messages=messages, model_id=self.model_id)

    def preprocess_messages(self, messages: Dict[str, List[Dict[str, Any]]]):
        preprocessed_messages = []
        # Extract the messages list from the dictionary
        messages_list = messages.get("messages", [])
        
        for message in messages_list:
            # Ensure role is one of the allowed values (user or assistant) as per the schema
            if message.get("role") == "user":
                preprocessed_messages.append({"role": "user", "content": message.get("content", "")})
            elif message.get("role") == "assistant":
                preprocessed_messages.append({"role": "assistant", "content": message.get("content", "")})
        return preprocessed_messages
        
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        preprocessed_messages = self.preprocess_messages(messages)
        content = self.call_bedrock_anthropic_llm(messages=preprocessed_messages)
        return AgentMessage(content=content)