#!/usr/bin/env python3
"""
Example demonstrating environment-driven agent configuration.

This example shows how to create agents whose provider and model
are configured entirely through environment variables, making it
easy to switch between providers without code changes.

Usage:
    # Bedrock (AWS)
    export DCAF_PROVIDER=bedrock
    export AWS_PROFILE=my-profile
    python examples/config_driven_agent.py

    # Gemini (Google)
    export DCAF_PROVIDER=google
    export DCAF_MODEL=gemini-3-flash
    export GEMINI_API_KEY=your-key
    python examples/config_driven_agent.py

    # Anthropic Direct
    export DCAF_PROVIDER=anthropic
    export DCAF_MODEL=claude-3-sonnet-20240229
    export ANTHROPIC_API_KEY=your-key
    python examples/config_driven_agent.py
"""

import os
import sys

from dcaf.core import Agent, get_provider_from_env, load_agent_config
from dcaf.tools import tool


@tool(description="Get weather information")
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Weather in {city}: Sunny, 72°F (22°C)"


@tool(description="Search the web")
def search(query: str) -> str:
    """Search for information."""
    return f"Search results for '{query}': [simulated results]"


def example_basic_config():
    """Load all configuration from environment."""
    print("=" * 70)
    print("Example 1: Basic Environment Configuration")
    print("=" * 70)

    # Load everything from environment variables
    config = load_agent_config()

    print("\nLoaded configuration:")
    print(f"  Provider: {config['provider']}")
    print(f"  Model: {config['model']}")
    print(f"  Temperature: {config.get('temperature', 'default')}")
    print(f"  Max Tokens: {config.get('max_tokens', 'default')}")

    # Create agent with loaded config
    agent = Agent(tools=[get_weather, search], **config)

    print("\nAgent created successfully!")
    print(f"  Using: {agent.provider} / {agent.model}")

    # Test the agent
    response = agent.run([{"role": "user", "content": "What's the weather in Paris?"}])

    print(f"\n📝 Response:\n{response.text}\n")


def example_with_overrides():
    """Load from environment but override specific values."""
    print("=" * 70)
    print("Example 2: Configuration with Overrides")
    print("=" * 70)

    # Load from env, but override temperature
    config = load_agent_config(temperature=0.9)

    print("\nConfiguration (with override):")
    print(f"  Provider: {config['provider']}")
    print(f"  Model: {config['model']}")
    print(f"  Temperature: {config['temperature']} (overridden)")

    agent = Agent(tools=[get_weather], system_prompt="You are a creative assistant.", **config)

    response = agent.run([{"role": "user", "content": "Describe AI in one sentence."}])

    print(f"\n📝 Response:\n{response.text}\n")


def example_explicit_provider():
    """Explicitly set provider, load rest from environment."""
    print("=" * 70)
    print("Example 3: Explicit Provider Selection")
    print("=" * 70)

    # Get current provider from env
    env_provider = get_provider_from_env()
    print(f"\nEnvironment provider: {env_provider}")

    # Force a specific provider (useful for testing)
    # config = load_agent_config(provider="bedrock")
    config = load_agent_config(provider=env_provider)

    print(f"Using provider: {config['provider']}")
    print(f"Using model: {config['model']}")

    agent = Agent(tools=[get_weather], **config)

    response = agent.run([{"role": "user", "content": "Hello!"}])

    print(f"\n📝 Response:\n{response.text}\n")


def example_multi_environment():
    """Demonstrate switching environments."""
    print("=" * 70)
    print("Example 4: Multi-Environment Setup")
    print("=" * 70)

    print("\nCurrent Configuration:")
    config = load_agent_config()

    print(f"  Provider: {config['provider']}")
    print(f"  Model: {config['model']}")

    if config["provider"] == "bedrock":
        print(f"  AWS Region: {config.get('aws_region', 'default')}")
        print(f"  AWS Profile: {config.get('aws_profile', 'not set')}")
    elif config["provider"] in ["google", "anthropic", "openai"]:
        has_key = "api_key" in config
        print(f"  API Key: {'✓ configured' if has_key else '✗ not set'}")

    print("\nEnvironment Variables:")
    print(f"  DCAF_PROVIDER: {os.getenv('DCAF_PROVIDER', 'not set')}")
    print(f"  DCAF_MODEL: {os.getenv('DCAF_MODEL', 'not set')}")
    print(f"  DCAF_TEMPERATURE: {os.getenv('DCAF_TEMPERATURE', 'not set')}")

    agent = Agent(tools=[get_weather], **config)

    print(f"\n✅ Agent ready with {agent.provider}/{agent.model}\n")


def example_production_pattern():
    """Production-ready pattern with error handling."""
    print("=" * 70)
    print("Example 5: Production Pattern")
    print("=" * 70)

    try:
        # Load config
        config = load_agent_config()

        print("\n✓ Configuration loaded")
        print(f"  Provider: {config['provider']}")
        print(f"  Model: {config['model']}")

        # Create agent
        agent = Agent(
            name="production-agent",
            description="Production agent with env-driven config",
            tools=[get_weather, search],
            system_prompt="You are a helpful assistant.",
            **config,
        )

        print("✓ Agent created")

        # Test request
        response = agent.run([{"role": "user", "content": "What's the weather in Tokyo?"}])

        print("✓ Request successful\n")
        print(f"📝 Response:\n{response.text}\n")

    except ImportError as e:
        print(f"\n❌ Missing dependency: {e}")
        print("Install required packages for your provider")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check environment variables are set correctly")
        print("2. Verify credentials are valid")
        print("3. Ensure required packages are installed")
        sys.exit(1)


def show_configuration_guide():
    """Show configuration guide."""
    print("\n" + "=" * 70)
    print("DCAF Environment Configuration Guide")
    print("=" * 70)

    print("\n📋 Required Environment Variables:\n")
    print("  DCAF_PROVIDER    - Provider name (bedrock, google, anthropic, etc.)")
    print("  DCAF_MODEL       - Model identifier (optional, auto-detected)")

    print("\n🔑 Provider Credentials:\n")
    print("  Bedrock:   AWS_PROFILE or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY")
    print("  Google:    GEMINI_API_KEY or GOOGLE_API_KEY")
    print("  Anthropic: ANTHROPIC_API_KEY")
    print("  OpenAI:    OPENAI_API_KEY")
    print("  Azure:     AZURE_OPENAI_API_KEY")
    print("  Ollama:    (no credentials needed)")

    print("\n⚙️  Optional Configuration:\n")
    print("  DCAF_TEMPERATURE        - Sampling temperature (0.0-1.0)")
    print("  DCAF_MAX_TOKENS         - Maximum output tokens")
    print("  DCAF_AGENT_NAME         - Agent name for A2A")
    print("  DCAF_AGENT_DESCRIPTION  - Agent description")

    print("\n💡 Example .env file:\n")
    print("  # Use Bedrock")
    print("  DCAF_PROVIDER=bedrock")
    print("  AWS_PROFILE=my-profile")
    print("  AWS_REGION=us-west-2")
    print()
    print("  # Or use Gemini")
    print("  DCAF_PROVIDER=google")
    print("  DCAF_MODEL=gemini-3-flash")
    print("  GEMINI_API_KEY=your-key")

    print("\n" + "=" * 70 + "\n")


def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("DCAF Environment-Driven Configuration Examples")
    print("=" * 70 + "\n")

    # Check if any provider is configured
    from dcaf.core.config import get_configured_provider

    configured_provider = get_configured_provider()

    if not configured_provider:
        print("⚠️  No provider configured!")
        show_configuration_guide()
        print("Set environment variables and try again.\n")
        sys.exit(1)

    print(f"✅ Found configured provider: {configured_provider}\n")

    try:
        # Run examples
        example_basic_config()
        input("Press Enter to continue...")

        example_with_overrides()
        input("Press Enter to continue...")

        example_explicit_provider()
        input("Press Enter to continue...")

        example_multi_environment()
        input("Press Enter to continue...")

        example_production_pattern()

        print("=" * 70)
        print("✅ All examples completed!")
        print("=" * 70)

        show_configuration_guide()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
