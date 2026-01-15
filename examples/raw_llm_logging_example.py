"""
Example: Raw LLM Request/Response Logging

This example demonstrates how to enable debug logging to see the raw
requests sent to AWS Bedrock and the raw responses received.

This is useful for:
- Debugging unexpected LLM behavior
- Auditing API calls
- Understanding token usage
- Analyzing cache performance
"""

import asyncio
import logging
import os

from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter


def setup_raw_llm_logging():
    """
    Configure logging to show raw LLM requests and responses.

    Raw LLM logging is enabled by default at INFO level, so you just need
    standard logging setup!

    DCAF uses unified logging control - one LOG_LEVEL controls both DCAF
    and Agno SDK logging automatically.
    """
    # Basic logging setup - that's all you need!
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    print("✅ Raw LLM logging enabled (automatically at INFO level)\n")
    print("=" * 80)
    print("You will see:")
    print("  🔍 RAW LLM REQUEST TO BEDROCK - Before sending to LLM")
    print("  🔍 RAW LLM RESPONSE FROM BEDROCK - After receiving from LLM")
    print()
    print("To see Agno SDK debug logs too, use:")
    print("  logging.basicConfig(level=logging.DEBUG)")
    print("=" * 80)
    print()


async def simple_example():
    """Simple question-answer example with raw logging."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Simple Question-Answer")
    print("=" * 80 + "\n")

    # Create adapter with Bedrock
    adapter = AgnoAdapter(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        provider="bedrock",
        max_tokens=1024,
        temperature=0.7,
        model_config={"cache_system_prompt": True},
    )

    # Simple question
    response = await adapter.ainvoke(
        messages=[
            {"role": "user", "content": "What is the capital of France?"}
        ],
        system="You are a helpful geography assistant.",
    )

    print(f"\n📤 User: What is the capital of France?")
    print(f"📥 Assistant: {response.text}")


async def example_with_tools():
    """Example with tool calls to see how tools appear in raw logs."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Tool Call (see tool definitions in raw request)")
    print("=" * 80 + "\n")

    # Create adapter with a tool
    adapter = AgnoAdapter(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        provider="bedrock",
        max_tokens=1024,
        temperature=0.0,
        model_config={"cache_system_prompt": True},
    )

    # Define a simple tool
    def get_weather(location: str) -> str:
        """Get the weather for a location."""
        return f"The weather in {location} is sunny and 72°F"

    # Ask a question that might trigger tool use
    response = await adapter.ainvoke(
        messages=[
            {"role": "user", "content": "What's the weather in Paris?"}
        ],
        system="You are a helpful assistant with access to weather data.",
        tools=[get_weather],
    )

    print(f"\n📤 User: What's the weather in Paris?")
    print(f"📥 Assistant: {response.text}")

    if response.tool_calls:
        print(f"🔧 Tool calls made: {len(response.tool_calls)}")
        for tool_call in response.tool_calls:
            print(f"   - {tool_call.function.name}({tool_call.function.arguments})")


async def example_cache_performance():
    """Example showing cache metrics in raw logs."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Cache Performance (see cache metrics in response)")
    print("=" * 80 + "\n")

    adapter = AgnoAdapter(
        model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
        provider="bedrock",
        max_tokens=512,
        temperature=0.0,
        model_config={"cache_system_prompt": True},
    )

    # Long system prompt to trigger caching (needs 1024+ tokens)
    long_system_prompt = """
You are an expert software engineer specializing in Python, JavaScript, and cloud architecture.
You have deep knowledge of AWS, GCP, and Azure services.
You understand best practices for microservices, event-driven architecture, and distributed systems.
You can help with code review, debugging, architecture design, and performance optimization.
You always provide clear, concise explanations with code examples when relevant.
You follow PEP 8 for Python, ESLint for JavaScript, and industry best practices.
You consider security, scalability, and maintainability in all recommendations.
You are familiar with modern frameworks like React, FastAPI, Django, and Express.
You understand databases including PostgreSQL, MongoDB, Redis, and DynamoDB.
You can help with CI/CD pipelines, Docker, Kubernetes, and infrastructure as code.
You stay up-to-date with the latest technology trends and best practices.
    """ * 10  # Repeat to ensure we exceed 1024 tokens

    print("First call (CACHE MISS - will create cache):")
    response1 = await adapter.ainvoke(
        messages=[{"role": "user", "content": "What is a microservice?"}],
        system=long_system_prompt,
    )
    print(f"📥 Response: {response1.text[:100]}...")

    print("\nSecond call with same system prompt (CACHE HIT):")
    response2 = await adapter.ainvoke(
        messages=[{"role": "user", "content": "What is event-driven architecture?"}],
        system=long_system_prompt,
    )
    print(f"📥 Response: {response2.text[:100]}...")

    print("\n💡 Look for 'cacheReadInputTokens' in the second response!")


async def main():
    """Run all examples."""
    # Enable raw LLM logging
    setup_raw_llm_logging()

    # Check for AWS credentials
    if not os.getenv("AWS_REGION"):
        print("⚠️  WARNING: AWS_REGION not set. Set environment variables:")
        print("   export AWS_REGION=us-west-2")
        print("   export AWS_PROFILE=your-profile")
        print("\nSkipping examples...\n")
        return

    try:
        # Run examples
        await simple_example()
        await example_with_tools()
        await example_cache_performance()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure you have:")
        print("  1. AWS credentials configured")
        print("  2. Bedrock model access enabled")
        print("  3. AWS_REGION environment variable set")

    print("\n" + "=" * 80)
    print("Examples complete!")
    print("=" * 80)
    print("\nNOTE: Look for the 🔍 emoji in the logs above to see raw requests/responses")
    print()


if __name__ == "__main__":
    asyncio.run(main())
