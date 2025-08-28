"""
Run with:   python main.py
Or `uvicorn main:app --port 8000` if you prefer the CLI.
"""

from agent_server import create_chat_app
from dcaf.llm import BedrockLLM
from agents.llm_passthrough_agent import LLMPassthroughAgent
import dotenv
import uvicorn
import os

# Load environment variables from .env file and override existing ones
dotenv.load_dotenv(override=True)

region_name = os.getenv("AWS_REGION", "us-east-1")
llm = BedrockLLM(region_name=region_name)

# Choose which agent to use
agent = LLMPassthroughAgent(llm)
# agent = EchoAgent()
# agent = LLMPassthroughAgent(BedrockLLM())
# agent = CommandAgent(BedrockLLM())
# agent = BoilerplateAgent()  # Default to the boilerplate agent

app = create_chat_app(agent)
port = os.getenv("PORT", 8000)

if __name__ == "__main__":
        
    # For reload to work, we need to use an import string instead of the app object
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(port),
        reload=True,     # set True for auto-reload in dev
        log_level="info",
    )