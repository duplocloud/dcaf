"""
A2A (Agent-to-Agent) Example

This example demonstrates how to create a multi-agent system using
DCAF's A2A protocol support. It shows:
1. Creating specialist agents (Kubernetes, AWS)
2. Exposing agents via A2A
3. Creating an orchestrator that calls specialist agents
4. Testing with RemoteAgent

To run this example:
1. Start the specialist agents in separate terminals:
   python examples/a2a_example.py k8s
   python examples/a2a_example.py aws

2. Start the orchestrator:
   python examples/a2a_example.py orchestrator

3. Test with the client:
   python examples/a2a_example.py client
"""

import sys

from dcaf.core import Agent, serve
from dcaf.core.a2a import RemoteAgent
from dcaf.tools import tool

# === Kubernetes Agent ===


def kubectl(cmd: str) -> str:
    """Mock kubectl command (replace with real implementation)."""
    return f"Simulated kubectl output for: {cmd}"


@tool(description="List Kubernetes pods in a namespace")
def list_pods(namespace: str = "default") -> str:
    """List all pods in a namespace."""
    return kubectl(f"get pods -n {namespace}")


@tool(description="Get detailed information about a pod")
def describe_pod(name: str, namespace: str = "default") -> str:
    """Get detailed information about a specific pod."""
    return kubectl(f"describe pod {name} -n {namespace}")


@tool(requires_approval=True, description="Delete a Kubernetes pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    """Delete a pod. Requires user approval."""
    return kubectl(f"delete pod {name} -n {namespace}")


def run_k8s_agent():
    """Run the Kubernetes specialist agent."""
    agent = Agent(
        name="k8s-assistant",
        description="Manages Kubernetes clusters. Can list, describe, and delete pods.",
        tools=[list_pods, describe_pod, delete_pod],
        system_prompt="You are a Kubernetes expert. Help users manage their clusters.",
    )

    print("Starting Kubernetes agent on port 8001...")
    print("Agent card: http://localhost:8001/.well-known/agent.json")
    serve(agent, port=8001, a2a=True)


# === AWS Agent ===


@tool(description="List EC2 instances")
def list_ec2() -> str:
    """List all EC2 instances."""
    return "Simulated EC2 list:\n- i-abc123 (running)\n- i-def456 (stopped)"


@tool(description="Get AWS cost estimate")
def get_aws_cost(service: str = "all") -> str:
    """Get cost estimate for AWS services."""
    return f"Simulated cost for {service}: $125.50/month"


def run_aws_agent():
    """Run the AWS specialist agent."""
    agent = Agent(
        name="aws-assistant",
        description="Manages AWS resources. Can list EC2 instances and estimate costs.",
        tools=[list_ec2, get_aws_cost],
        system_prompt="You are an AWS expert. Help users manage their AWS infrastructure.",
    )

    print("Starting AWS agent on port 8002...")
    print("Agent card: http://localhost:8002/.well-known/agent.json")
    serve(agent, port=8002, a2a=True)


# === Orchestrator Agent ===


def run_orchestrator():
    """Run the orchestrator agent that routes to specialists."""
    # Connect to specialist agents
    k8s = RemoteAgent(url="http://localhost:8001")
    aws = RemoteAgent(url="http://localhost:8002")

    # Create orchestrator
    orchestrator = Agent(
        name="orchestrator",
        description="Intelligent orchestrator that routes requests to specialist agents",
        tools=[k8s.as_tool(), aws.as_tool()],
        system_prompt="""You are an intelligent orchestrator for infrastructure management.

You have access to two specialist agents:
- k8s_assistant: For Kubernetes questions (pods, deployments, services)
- aws_assistant: For AWS questions (EC2, costs, resources)

Route each question to the appropriate specialist. You can call multiple specialists if needed.
Always provide a comprehensive answer based on the specialists' responses.""",
    )

    print("Starting orchestrator on port 8000...")
    print("Agent card: http://localhost:8000/.well-known/agent.json")
    print("\nThe orchestrator can route requests to:")
    print(f"  - {k8s.name}: {k8s.description}")
    print(f"  - {aws.name}: {aws.description}")
    serve(orchestrator, port=8000, a2a=True)


# === Client ===


def run_client():
    """Run the test client."""
    print("Testing A2A agents...\n")

    # Connect to orchestrator
    orchestrator = RemoteAgent(url="http://localhost:8000")

    print(f"Connected to: {orchestrator.name}")
    print(f"Description: {orchestrator.description}")
    print(f"Skills: {orchestrator.skills}\n")

    # Test questions
    questions = [
        "How many pods are running in the default namespace?",
        "What's my AWS cost this month?",
        "Give me a status report of my entire infrastructure",
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n{'=' * 70}")
        print(f"Question {i}: {question}")
        print("=" * 70)

        try:
            result = orchestrator.send(question, timeout=30.0)
            print(f"\nResponse:\n{result.text}")
            print(f"\nStatus: {result.status}")
        except Exception as e:
            print(f"Error: {e}")

    print("\n" + "=" * 70)
    print("Testing complete!")


# === Main ===


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "k8s":
        run_k8s_agent()
    elif mode == "aws":
        run_aws_agent()
    elif mode == "orchestrator":
        run_orchestrator()
    elif mode == "client":
        run_client()
    else:
        print(f"Unknown mode: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
