#!/usr/bin/env python3
"""
Example demonstrating Google Gemini integration with DCAF.

This example shows how to use various Gemini models with DCAF,
including tool use, streaming, and model configuration.

Prerequisites:
    pip install google-generativeai

Usage:
    export GEMINI_API_KEY="your-api-key"
    python examples/gemini_example.py
"""

from dcaf.core import Agent
from dcaf.tools import tool
import os
import sys


def check_prerequisites():
    """Check if required dependencies and configuration are present."""
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ Error: GEMINI_API_KEY environment variable not set")
        print("\nGet your API key from: https://aistudio.google.com")
        print("Then run: export GEMINI_API_KEY='your-key-here'")
        sys.exit(1)
    
    try:
        import google.generativeai
    except ImportError:
        print("❌ Error: google-generativeai package not installed")
        print("\nInstall with: pip install google-generativeai")
        sys.exit(1)
    
    print("✅ Prerequisites check passed\n")


# ============================================================================
# Example 1: Basic Gemini Usage
# ============================================================================

def example_basic():
    """Basic Gemini agent example."""
    print("="*70)
    print("Example 1: Basic Gemini Usage")
    print("="*70)
    
    agent = Agent(
        provider="google",
        model="gemini-3-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        system_prompt="You are a helpful and concise assistant."
    )
    
    response = agent.run([
        {"role": "user", "content": "What are the three laws of robotics?"}
    ])
    
    print(f"\n📝 Response:\n{response.text}\n")


# ============================================================================
# Example 2: Using Tools with Gemini
# ============================================================================

@tool(description="Search for information on the web")
def web_search(query: str) -> str:
    """
    Search the web for information.
    
    Args:
        query: The search query
        
    Returns:
        Search results
    """
    # Simulated search results
    return f"Search results for '{query}':\n- Result 1: Latest AI developments\n- Result 2: Machine learning advances"


@tool(description="Get weather information for a city")
def get_weather(city: str) -> str:
    """
    Get current weather for a city.
    
    Args:
        city: The city name
        
    Returns:
        Weather information
    """
    # Simulated weather data
    return f"Weather in {city}: Sunny, 72°F (22°C), Light breeze"


def example_with_tools():
    """Gemini agent with tools."""
    print("="*70)
    print("Example 2: Gemini with Tools")
    print("="*70)
    
    agent = Agent(
        provider="google",
        model="gemini-3-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        tools=[web_search, get_weather],
        system_prompt="You are a helpful assistant with access to web search and weather information."
    )
    
    response = agent.run([
        {"role": "user", "content": "What's the weather in Tokyo and any AI news?"}
    ])
    
    print(f"\n📝 Response:\n{response.text}\n")
    
    if response.tool_calls:
        print(f"🔧 Tools Used: {len(response.tool_calls)}")
        for tc in response.tool_calls:
            print(f"  - {tc.name}({tc.arguments})")
        print()


# ============================================================================
# Example 3: Streaming Responses
# ============================================================================

def example_streaming():
    """Stream responses from Gemini."""
    print("="*70)
    print("Example 3: Streaming Responses")
    print("="*70)
    
    agent = Agent(
        provider="google",
        model="gemini-3-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        system_prompt="You are a creative storyteller."
    )
    
    print("\n📝 Streaming response:\n")
    
    for event in agent.stream([
        {"role": "user", "content": "Write a very short haiku about artificial intelligence."}
    ]):
        if event.type == "text_delta":
            print(event.data.text, end="", flush=True)
        elif event.type == "complete":
            print("\n\n✅ Stream complete\n")


# ============================================================================
# Example 4: Model Configuration
# ============================================================================

def example_model_config():
    """Demonstrate different model configurations."""
    print("="*70)
    print("Example 4: Model Configuration")
    print("="*70)
    
    # High creativity (higher temperature)
    creative_agent = Agent(
        provider="google",
        model="gemini-3-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        model_config={
            "temperature": 0.9,  # More creative
            "max_tokens": 100,
        },
        system_prompt="You are a creative writer."
    )
    
    print("\n🎨 Creative (temperature=0.9):")
    response = creative_agent.run([
        {"role": "user", "content": "Describe AI in one sentence."}
    ])
    print(f"{response.text}\n")
    
    # Deterministic (lower temperature)
    factual_agent = Agent(
        provider="google",
        model="gemini-3-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        model_config={
            "temperature": 0.1,  # More deterministic
            "max_tokens": 100,
        },
        system_prompt="You are a factual encyclopedia."
    )
    
    print("📚 Factual (temperature=0.1):")
    response = factual_agent.run([
        {"role": "user", "content": "Describe AI in one sentence."}
    ])
    print(f"{response.text}\n")


# ============================================================================
# Example 5: Different Gemini Models
# ============================================================================

def example_different_models():
    """Compare different Gemini models."""
    print("="*70)
    print("Example 5: Different Gemini Models")
    print("="*70)
    
    models = [
        ("gemini-3-flash", "Fast and efficient"),
        ("gemini-2.5-flash", "Previous gen flash"),
        ("gemini-1.5-flash", "Older but reliable"),
    ]
    
    question = "What is machine learning?"
    
    for model_id, description in models:
        print(f"\n📱 Model: {model_id} ({description})")
        
        agent = Agent(
            provider="google",
            model=model_id,
            api_key=os.getenv("GEMINI_API_KEY"),
            model_config={"max_tokens": 150},
        )
        
        try:
            response = agent.run([
                {"role": "user", "content": question}
            ])
            print(f"Response: {response.text[:200]}...")
        except Exception as e:
            print(f"❌ Error: {e}")


# ============================================================================
# Example 6: Multi-turn Conversation
# ============================================================================

def example_conversation():
    """Multi-turn conversation with Gemini."""
    print("="*70)
    print("Example 6: Multi-turn Conversation")
    print("="*70)
    
    agent = Agent(
        provider="google",
        model="gemini-3-flash",
        api_key=os.getenv("GEMINI_API_KEY"),
        system_prompt="You are a helpful coding assistant."
    )
    
    # Build conversation
    messages = [
        {"role": "user", "content": "What is Python?"}
    ]
    
    print("\n👤 User: What is Python?")
    response = agent.run(messages)
    print(f"🤖 Assistant: {response.text}\n")
    
    # Add to history
    messages.append({"role": "assistant", "content": response.text})
    messages.append({"role": "user", "content": "Give me a simple example."})
    
    print("👤 User: Give me a simple example.")
    response = agent.run(messages)
    print(f"🤖 Assistant: {response.text}\n")


# ============================================================================
# Main
# ============================================================================

def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("DCAF Google Gemini Integration Examples")
    print("="*70 + "\n")
    
    # Check prerequisites
    check_prerequisites()
    
    try:
        # Run examples
        example_basic()
        input("Press Enter to continue to next example...")
        
        example_with_tools()
        input("Press Enter to continue to next example...")
        
        example_streaming()
        input("Press Enter to continue to next example...")
        
        example_model_config()
        input("Press Enter to continue to next example...")
        
        example_different_models()
        input("Press Enter to continue to next example...")
        
        example_conversation()
        
        print("\n" + "="*70)
        print("✅ All examples completed successfully!")
        print("="*70)
        print("\nNext steps:")
        print("- Try different Gemini models (gemini-3-pro-preview, gemini-2.5-pro)")
        print("- Add your own custom tools")
        print("- Deploy with serve() as a REST API")
        print("- Check docs/guides/working-with-gemini.md for more info")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
