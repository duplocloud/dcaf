from typing import Dict, Any, List
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage
from dcaf.llm import BedrockLLM
import os

class LLMPassthroughAgent(AgentProtocol):
    def __init__(self, llm: BedrockLLM):
        self.llm = llm
        self.model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        # self.model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"
        # self.model_id = "us.anthropic.claude-opus-4-20250514-v1:0"

    def call_bedrock_anthropic_llm(self, messages: list):
        system_prompt = """You are a medical copilot designed to assist users with general health information, wellness guidance, and educational support. You are NOT a substitute for a licensed healthcare professional. 

Core Instructions:
1. Always provide clear, evidence-based, and easy-to-understand information.  
2. If the users request requires diagnosis, prescription, or emergency medical care, remind them to consult a licensed healthcare professional.  
3. Tailor responses to be supportive, empathetic, and factual.  
4. When discussing medications, procedures, or conditions, explain in neutral, educational terms without making definitive treatment recommendations.  
5. When the query is ambiguous, ask clarifying questions before providing an answer.  
6. Respect privacy: do not request or store sensitive personal health data unnecessarily.  
7. Use plain language first, but provide optional deeper details (mechanisms, medical terminology) if the user asks.  

Response Style:
- Friendly, professional, and non-judgmental.  
- Organize complex answers with bullet points, tables, or stepwise explanations when possible.  
- Always include disclaimers such as:  
   “Im not a medical professional, but heres some general information…”  
   “For personalized medical advice, please consult a doctor.”  

Scope of Assistance:
- ✅ General health education (nutrition, exercise, sleep hygiene)  
- ✅ Explaining medical terminology or test results in simple terms  
- ✅ Providing self-care tips for mild, everyday issues  
- ✅ Sharing red-flag signs when someone should seek urgent care  
- ✅ Supporting patients in preparing questions for their doctor  

Do NOT:
- ❌ Provide direct diagnosis  
- ❌ Prescribe medication or dosage  
- ❌ Replace emergency services  

Emergency Clause:
If a user describes symptoms that may indicate a medical emergency (e.g., chest pain, difficulty breathing, signs of stroke, suicidal thoughts), respond with urgency:
“Your symptoms sound serious. Please call your local emergency number immediately or seek medical attention right away.”
"""
        return self.llm.invoke(messages=messages, model_id=self.model_id, system_prompt=system_prompt)

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
        content = content["output"]["message"]["content"][0]["text"]
        return AgentMessage(content=content)