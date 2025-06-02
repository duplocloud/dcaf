"""
Run with:   python main.py
Or `uvicorn main:app --port 8000` if you prefer the CLI.
"""

from echo_agent import EchoAgent
from agent_server import create_chat_app
from llm import BedrockAnthropicLLM
from llm_passthrough_agent import LLMPassthroughAgent
import dotenv

# Load environment variables from .env file
dotenv.load_dotenv()


app = create_chat_app(LLMPassthroughAgent(BedrockAnthropicLLM()))


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