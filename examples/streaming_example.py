"""
Example: Streaming responses from a DCAF Core agent.

This demonstrates how to use run_stream() for real-time
token-by-token output.

Run with:
    python examples/streaming_example.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dotenv
dotenv.load_dotenv(override=True)

from dcaf.core import Agent, ChatMessage, TextDeltaEvent, ToolCallsEvent, DoneEvent, ErrorEvent
from dcaf.tools import tool


@tool(description="Get information about a topic")
def get_info(topic: str) -> str:
    """Get information about a topic."""
    return f"Information about {topic}: This is simulated content."


@tool(requires_approval=True, description="Perform a dangerous operation")
def dangerous_op(action: str) -> str:
    """Requires approval before execution."""
    return f"Executed: {action}"


# Create the agent
agent = Agent(
    tools=[get_info, dangerous_op],
    system_prompt="You are a helpful assistant. Be concise.",
)


def main():
    print("=" * 60)
    print("DCAF Core Streaming Example")
    print("=" * 60)
    
    # Example 1: Simple streaming
    print("\n--- Example 1: Simple Streaming ---\n")
    
    for event in agent.run_stream(messages=[
        ChatMessage.user("Tell me about Kubernetes")
    ]):
        if isinstance(event, TextDeltaEvent):
            # Print each text token as it arrives
            print(event.text, end="", flush=True)
        elif isinstance(event, DoneEvent):
            print("\n\n[Stream completed]")
        elif isinstance(event, ErrorEvent):
            print(f"\n[Error: {event.error}]")
    
    # Example 2: Handling tool calls in stream
    print("\n--- Example 2: Tool Calls in Stream ---\n")
    
    for event in agent.run_stream(messages=[
        ChatMessage.user("Do the dangerous operation 'delete all'")
    ]):
        if isinstance(event, TextDeltaEvent):
            print(event.text, end="", flush=True)
        elif isinstance(event, ToolCallsEvent):
            print("\n[Tool calls need approval:]")
            for tc in event.tool_calls:
                print(f"  - {tc.name}: {tc.input}")
        elif isinstance(event, DoneEvent):
            print("\n[Stream completed]")
    
    print("\n" + "=" * 60)
    print("Examples complete!")


if __name__ == "__main__":
    main()
