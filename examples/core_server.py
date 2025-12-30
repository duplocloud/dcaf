"""
Example: Running a DCAF Core agent as a server.

This demonstrates the simplest way to create an agent and
expose it via REST endpoints.

Run with:
    python examples/core_server.py

Then test with:
    curl http://localhost:8000/health
    
    curl -X POST http://localhost:8000/api/chat \
        -H "Content-Type: application/json" \
        -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dotenv
dotenv.load_dotenv(override=True)

from dcaf.core import Agent, serve
from dcaf.tools import tool


# Define some example tools
@tool(description="Get the current time")
def get_time() -> str:
    """Get the current time."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool(description="Echo back a message")
def echo(message: str) -> str:
    """Echo back the given message."""
    return f"You said: {message}"


@tool(requires_approval=True, description="Perform a dangerous operation")
def dangerous_operation(action: str) -> str:
    """
    A tool that requires user approval before execution.
    
    This demonstrates the human-in-the-loop pattern.
    """
    return f"Executed dangerous action: {action}"


# Create the agent
agent = Agent(
    tools=[get_time, echo, dangerous_operation],
    system_prompt="""You are a helpful assistant. You have access to the following tools:
    
- get_time: Returns the current time
- echo: Echoes back a message
- dangerous_operation: Requires approval before execution

When the user asks you to do something, use the appropriate tool.
""",
)


if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.getenv("PORT", 8000))
    
    print("=" * 60)
    print("DCAF Core Agent Server")
    print("=" * 60)
    print(f"\nStarting server on http://0.0.0.0:{port}")
    print("\nAvailable endpoints:")
    print(f"  GET  http://localhost:{port}/health")
    print(f"  POST http://localhost:{port}/api/chat")
    print(f"  POST http://localhost:{port}/api/chat-stream")
    print("\nLegacy endpoints (backwards compatible):")
    print(f"  POST http://localhost:{port}/api/sendMessage")
    print(f"  POST http://localhost:{port}/api/sendMessageStream")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)
    
    # Start the server
    serve(agent, port=port)
