# Building Custom Agents

This guide shows how to build agents with custom logic using DCAF.

---

## When to Use Custom Functions

Use **`Agent` directly with `serve()`** for simple use cases:

```python
from dcaf.core import Agent, serve

agent = Agent(tools=[my_tool])
serve(agent)
```

Use **custom functions** when you need:

- Multiple LLM calls
- Complex branching logic
- Custom pre/post processing
- Integration with external systems
- Different models for different tasks

---

## Quick Start

```python
from dcaf.core import Agent, AgentResult, serve
from dcaf.tools import tool

@tool(description="Get current time")
def get_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()

def my_agent(messages: list, context: dict) -> AgentResult:
    """Your custom agent logic."""
    
    # Create an agent and run it
    agent = Agent(
        tools=[get_time],
        system="You are a helpful assistant.",
    )
    
    response = agent.run(messages)
    
    # Return the result
    return AgentResult(text=response.text)

# Serve it
serve(my_agent)
```

---

## The Pattern

### Custom functions return `AgentResult`

```python
from dcaf.core import AgentResult, ToolApproval, ToolResult

# Simple text response
return AgentResult(text="Here are your pods: nginx, redis, api")

# Needs approval
return AgentResult(
    text="I need approval to delete the pod.",
    pending_tools=[
        ToolApproval(
            id="tc_123",
            name="delete_pod",
            input={"name": "nginx-abc"},
            description="Delete pod nginx-abc from production",
        )
    ],
)

# Tool was executed
return AgentResult(
    text="Pod deleted successfully.",
    executed_tools=[
        ToolResult(
            id="tc_123",
            name="delete_pod",
            input={"name": "nginx-abc"},
            output="pod 'nginx-abc' deleted",
        )
    ],
)
```

### Use `from_agent_response()` for convenience

```python
from dcaf.core import Agent, from_agent_response, serve

def my_agent(messages: list, context: dict) -> AgentResult:
    agent = Agent(tools=[...])
    response = agent.run(messages)
    return from_agent_response(response)

serve(my_agent)
```

---

## Multi-Call Patterns

### Pattern 1: Sequential Calls

Each call depends on the previous:

```python
from dcaf.core import Agent, AgentResult

def research_agent(messages: list, context: dict) -> AgentResult:
    user_question = messages[-1]["content"]
    
    # Step 1: Classify the question
    classifier = Agent(system="Classify as: factual, opinion, or action. Reply with one word.")
    classification = classifier.run(messages)
    
    # Step 2: Handle based on classification
    if "factual" in classification.text.lower():
        # Research the topic
        researcher = Agent(system="Provide detailed factual information.")
        research = researcher.run([{"role": "user", "content": f"Research: {user_question}"}])
        
        # Step 3: Summarize
        summarizer = Agent(system="Provide a concise summary.")
        summary = summarizer.run([{"role": "user", "content": f"Summarize: {research.text}"}])
        
        return AgentResult(text=summary.text)
    
    elif "action" in classification.text.lower():
        # Use tools
        executor = Agent(tools=[...], system="Execute the requested action.")
        result = executor.run(messages)
        
        return AgentResult(
            text=result.text,
            pending_tools=[
                ToolApproval(id=p.id, name=p.name, input=p.input, description=p.description)
                for p in result.pending_tools
            ],
        )
    
    else:
        # Simple response
        responder = Agent(system="Be helpful and friendly.")
        result = responder.run(messages)
        return AgentResult(text=result.text)
```

### Pattern 2: Parallel Calls

When calls are independent, run them in parallel:

```python
from concurrent.futures import ThreadPoolExecutor
from dcaf.core import Agent, AgentResult

executor = ThreadPoolExecutor(max_workers=5)

def parallel_agent(messages: list, context: dict) -> AgentResult:
    user_question = messages[-1]["content"]
    
    # Define parallel tasks
    def get_weather():
        agent = Agent(system="Answer weather questions briefly.")
        return agent.run([{"role": "user", "content": "What's the weather?"}]).text
    
    def get_news():
        agent = Agent(system="Summarize recent news briefly.")
        return agent.run([{"role": "user", "content": "What's the news?"}]).text
    
    def get_stocks():
        agent = Agent(system="Summarize stock market briefly.")
        return agent.run([{"role": "user", "content": "How are stocks?"}]).text
    
    # Run in parallel
    weather_future = executor.submit(get_weather)
    news_future = executor.submit(get_news)
    stocks_future = executor.submit(get_stocks)
    
    # Combine results
    combined = f"""
    Weather: {weather_future.result()}
    News: {news_future.result()}
    Stocks: {stocks_future.result()}
    """
    
    # Final synthesis
    synthesizer = Agent(system="Create a cohesive summary from the information provided.")
    final = synthesizer.run([{"role": "user", "content": f"Summarize this:\n{combined}"}])
    
    return AgentResult(text=final.text)
```

### Pattern 3: Agentic Loop

Let the LLM decide when it's done:

```python
from dcaf.core import Agent, AgentResult, ToolApproval
from dcaf.tools import tool

@tool(description="Mark the task as complete")
def finish(result: str) -> str:
    return f"DONE: {result}"

def agentic_loop(messages: list, context: dict) -> AgentResult:
    MAX_ITERATIONS = 10
    tools = [search, calculate, finish]
    
    agent = Agent(tools=tools, system="Complete the task. Call finish() when done.")
    conversation = list(messages)
    all_executed = []
    
    for i in range(MAX_ITERATIONS):
        response = agent.run(conversation)
        
        # Check if agent called finish
        if "DONE:" in response.text:
            return AgentResult(
                text=response.text.replace("DONE:", "").strip(),
                executed_tools=all_executed,
            )
        
        # Check for pending approvals
        if response.pending_tools:
            return AgentResult(
                text=response.text,
                pending_tools=[
                    ToolApproval(id=p.id, name=p.name, input=p.input, description=p.description)
                    for p in response.pending_tools
                ],
                executed_tools=all_executed,
            )
        
        # Add response to conversation and continue
        conversation.append({"role": "assistant", "content": response.text})
        conversation.append({"role": "user", "content": "Continue with the task."})
    
    return AgentResult(text="Max iterations reached.", executed_tools=all_executed)
```

### Pattern 4: Pre/Post Processing

Add logic before and after LLM calls:

```python
from dcaf.core import Agent, AgentResult

def processing_agent(messages: list, context: dict) -> AgentResult:
    # ==================
    # PRE-PROCESSING
    # ==================
    
    # Validate tenant
    tenant = context.get("tenant_name")
    if not tenant:
        return AgentResult(text="Error: No tenant specified.")
    
    # Enrich with tenant info
    tenant_info = get_tenant_info(tenant)
    enriched_system = f"""
    You are helping tenant: {tenant}
    Cluster: {tenant_info['cluster']}
    Namespace: {tenant_info['namespace']}
    """
    
    # Filter messages (e.g., remove PII)
    safe_messages = sanitize_messages(messages)
    
    # ==================
    # LLM CALL
    # ==================
    
    agent = Agent(
        tools=get_tools_for_tenant(tenant),
        system=enriched_system,
    )
    response = agent.run(safe_messages)
    
    # ==================
    # POST-PROCESSING
    # ==================
    
    # Audit logging
    log_interaction(tenant, messages, response)
    
    # Validate response
    response_text = response.text
    if contains_sensitive_info(response_text):
        response_text = redact_sensitive(response_text)
    
    # Apply rate limiting
    if is_rate_limited(tenant):
        return AgentResult(text="Rate limit exceeded. Please try again later.")
    
    return AgentResult(
        text=response_text,
        pending_tools=[
            ToolApproval(id=p.id, name=p.name, input=p.input, description=p.description)
            for p in response.pending_tools
        ],
    )
```

---

## Using Different Models

Create agents with different configurations for different tasks:

```python
from dcaf.core import Agent, AgentResult

def smart_routing_agent(messages: list, context: dict) -> AgentResult:
    # Fast model for classification
    classifier = Agent(
        model="anthropic.claude-3-haiku",
        system="Classify the complexity: simple or complex. Reply with one word.",
    )
    complexity = classifier.run(messages)
    
    if "complex" in complexity.text.lower():
        # Smart model for complex tasks
        smart_agent = Agent(
            model="anthropic.claude-3-opus",
            tools=[...],
            system="Handle complex queries thoroughly.",
        )
        response = smart_agent.run(messages)
    else:
        # Fast model for simple tasks
        fast_agent = Agent(
            model="anthropic.claude-3-haiku",
            system="Answer simply and briefly.",
        )
        response = fast_agent.run(messages)
    
    return AgentResult(text=response.text)
```

---

## Complete Example

```python
"""
Multi-step Kubernetes agent using DCAF.
"""

from dcaf.core import Agent, AgentResult, ToolApproval, ToolResult, serve
from dcaf.tools import tool

# Define tools
@tool(description="List pods in a namespace")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

TOOLS = [list_pods, delete_pod]

def k8s_agent(messages: list, context: dict) -> AgentResult:
    """Kubernetes assistant with approval flow."""
    
    user_message = messages[-1]["content"]
    
    # Step 1: Classify intent
    classifier = Agent(system="Classify as: query, action, or other. Reply with one word.")
    intent = classifier.run([{"role": "user", "content": user_message}])
    
    # Step 2: Handle based on intent
    if "query" in intent.text.lower():
        # Just answer questions using tools
        executor = Agent(
            tools=TOOLS,
            system="You are a Kubernetes assistant. Answer questions about the cluster.",
        )
        response = executor.run(messages)
        
        return AgentResult(text=response.text)
    
    elif "action" in intent.text.lower():
        # Actions may need approval
        executor = Agent(
            tools=TOOLS,
            system="You are a Kubernetes assistant. Help with cluster management.",
        )
        response = executor.run(messages)
        
        return AgentResult(
            text=response.text or "I need approval for this action.",
            pending_tools=[
                ToolApproval(id=p.id, name=p.name, input=p.input, description=p.description)
                for p in response.pending_tools
            ],
        )
    
    else:
        # General conversation
        responder = Agent(system="You are a friendly Kubernetes assistant.")
        response = responder.run(messages)
        return AgentResult(text=response.text)


if __name__ == "__main__":
    serve(k8s_agent, port=8000)
```

---

## See Also

- [Server Documentation](../core/server.md) - Running agents as REST APIs
- [Core Overview](../core/index.md) - The simple Agent class
- [Building Tools](./building-tools.md) - Creating tools with @tool decorator
