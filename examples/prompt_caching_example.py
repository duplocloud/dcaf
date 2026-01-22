"""
Example: Using Bedrock Prompt Caching with DCAF

This example demonstrates how to use prompt caching to reduce costs and latency
when working with agents that have static instructions and dynamic context.
"""

import logging

from dcaf.core import Agent
from dcaf.tools import tool

# Enable detailed logging to see cache metrics
logging.basicConfig(level=logging.INFO)


# Define some example tools
@tool(description="List all Kubernetes pods in a namespace")
def list_pods(namespace: str = "default") -> str:
    """List pods (simulated)."""
    return f"Pods in {namespace}: pod-1, pod-2, pod-3"


@tool(description="Get details about a specific pod")
def get_pod(name: str, namespace: str = "default") -> str:
    """Get pod details (simulated)."""
    return f"Pod {name} in {namespace}: Running, 2 containers"


# Example 1: Basic caching with static prompt only
def example_basic_caching():
    """Simple caching example with just a static prompt."""
    print("\n=== Example 1: Basic Caching ===\n")

    agent = Agent(
        system_prompt="""
        You are a Kubernetes expert assistant. Your role is to help users
        manage their Kubernetes clusters safely and efficiently.

        Guidelines:
        - Always verify namespace before operations
        - Explain what each command does
        - Ask for confirmation on destructive operations
        - Use kubectl best practices
        - Provide helpful error messages

        (Add more detailed instructions here to exceed 1024 tokens for caching)
        """
        * 3,  # Repeat to exceed minimum token threshold
        tools=[list_pods, get_pod],
        model_config={
            "cache_system_prompt": True  # Enable caching
        },
    )

    # First request - cache MISS (creates cache)
    print("First request (cache MISS):")
    result1 = agent.run([{"role": "user", "content": "List pods"}])
    print(f"Response: {result1.text}\n")

    # Second request - cache HIT (reuses cache)
    print("Second request (cache HIT):")
    result2 = agent.run([{"role": "user", "content": "Get details for pod-1"}])
    print(f"Response: {result2.text}\n")

    print("Check logs above for cache HIT/MISS indicators")


# Example 2: Static instructions + dynamic context
def example_static_and_dynamic():
    """Caching with separated static and dynamic parts."""
    print("\n=== Example 2: Static + Dynamic Context ===\n")

    agent = Agent(
        # Static part - cached (same for all requests)
        system_prompt="""
        You are a Kubernetes expert assistant for a multi-tenant platform.

        Your responsibilities:
        - Help users manage pods, services, and deployments
        - Ensure operations are scoped to the correct tenant and namespace
        - Follow security best practices
        - Provide clear explanations

        Guidelines:
        - Always check tenant context before operations
        - Verify namespace matches tenant configuration
        - Ask for confirmation on destructive operations
        - Log all operations for audit trail

        (Add detailed instructions to exceed 1024 tokens)
        """
        * 3,
        # Dynamic part - NOT cached (changes per request)
        system_context=lambda ctx: f"""
        === CURRENT CONTEXT ===
        Tenant: {ctx.get("tenant_name", "unknown")}
        Namespace: {ctx.get("k8s_namespace", "default")}
        User: {ctx.get("user_email", "anonymous")}
        Environment: {ctx.get("environment", "production")}

        You MUST scope all operations to the above context.
        """,
        tools=[list_pods, get_pod],
        model_config={"cache_system_prompt": True},
    )

    # Request 1: Tenant A
    print("Request for Tenant A:")
    context_a = {
        "tenant_name": "acme-corp",
        "k8s_namespace": "acme-prod",
        "user_email": "alice@acme.com",
        "environment": "production",
    }
    result1 = agent.run([{"role": "user", "content": "List all pods"}], context=context_a)
    print(f"Response: {result1.text}\n")

    # Request 2: Tenant B (cache HIT for static, fresh dynamic)
    print("Request for Tenant B:")
    context_b = {
        "tenant_name": "widgets-inc",
        "k8s_namespace": "widgets-dev",
        "user_email": "bob@widgets.com",
        "environment": "development",
    }
    result2 = agent.run([{"role": "user", "content": "Show pod-1 details"}], context=context_b)
    print(f"Response: {result2.text}\n")

    print("Static instructions are cached, dynamic context is fresh each time")


# Example 3: Cost comparison (conceptual)
def example_cost_comparison():
    """Show the cost impact of caching."""
    print("\n=== Example 3: Cost Impact ===\n")

    # Simulated token counts
    static_tokens = 1500  # Long system prompt
    dynamic_tokens = 100  # Short context

    print("Without caching:")
    print(f"  Per request: {static_tokens + dynamic_tokens} input tokens")
    print(f"  100 requests: {(static_tokens + dynamic_tokens) * 100} tokens")
    print(f"  Approx cost: ${((static_tokens + dynamic_tokens) * 100) * 0.000003:.4f}")

    print("\nWith caching:")
    print(f"  First request: {static_tokens + dynamic_tokens} tokens (cache MISS)")
    print(f"  Subsequent 99: {dynamic_tokens * 99} tokens (cache HIT)")
    print(f"  Total: {static_tokens + dynamic_tokens + (dynamic_tokens * 99)} tokens")
    print(
        f"  Approx cost: ${(static_tokens + dynamic_tokens + (dynamic_tokens * 99)) * 0.000003:.4f}"
    )

    savings = 100 - (
        (static_tokens + dynamic_tokens + (dynamic_tokens * 99))
        / ((static_tokens + dynamic_tokens) * 100)
        * 100
    )
    print(f"\n  Savings: ~{savings:.1f}%")


if __name__ == "__main__":
    print("Bedrock Prompt Caching Examples")
    print("=" * 50)

    # Run examples
    example_basic_caching()
    example_static_and_dynamic()
    example_cost_comparison()

    print("\n" + "=" * 50)
    print("Examples complete!")
    print("\nKey takeaways:")
    print("1. Enable caching with model_config={'cache_system_prompt': True}")
    print("2. Separate static (cached) and dynamic (fresh) content")
    print("3. Ensure static content exceeds 1024 tokens for best results")
    print("4. Monitor logs for cache HIT/MISS indicators")
