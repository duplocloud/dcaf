# Channel Routing API Reference

The Channel Routing module provides intelligent routing for different messaging channels, determining when agents should respond to messages.

---

## Table of Contents

1. [Overview](#overview)
2. [ChannelResponseRouter](#channelresponserouter)
3. [SlackResponseRouter](#slackresponserouter)
4. [Configuration](#configuration)
5. [Examples](#examples)

---

## Overview

Channel routing helps agents make intelligent decisions about when to respond in multi-party conversations. This is particularly useful for:

- **Slack threads** with multiple participants
- **Multi-agent systems** where different agents handle different topics
- **Smart filtering** to avoid responding to off-topic messages

### Import

```python
from dcaf.channel_routing import SlackResponseRouter, ChannelResponseRouter

# Or from the core module
from dcaf.core import SlackResponseRouter, ChannelResponseRouter

# Or from the top-level module
from dcaf import SlackResponseRouter
```

---

## ChannelResponseRouter

Base class for channel-specific routers.

```python
class ChannelResponseRouter:
    """
    Generic class which will be inherited by subclasses for various channel routers.
    """

    def should_agent_respond(self):
        """Determine if the agent should respond."""
        pass
```

### Extending the Base Class

```python
from dcaf.channel_routing import ChannelResponseRouter
from dcaf.llm import BedrockLLM

class CustomRouter(ChannelResponseRouter):
    def __init__(self, llm: BedrockLLM):
        self.llm = llm
    
    def should_agent_respond(self, messages: list) -> dict:
        # Custom routing logic
        return {
            "should_respond": True,
            "reasoning": "Custom routing decision"
        }
```

---

## SlackResponseRouter

Router that determines whether an agent should respond in Slack threads.

### Class Definition

```python
class SlackResponseRouter(ChannelResponseRouter):
    """
    A router that decides whether a bot should respond to Slack messages.
    
    This class uses an LLM to analyze conversation context and determine if
    the bot should engage or remain silent based on the conversation flow.
    """
```

### Constructor

```python
def __init__(
    self, 
    llm_client: BedrockLLM, 
    agent_name: str = "Assistant", 
    agent_description: str = "",
    model_id: str = None
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_client` | `BedrockLLM` | Required | LLM client for routing decisions |
| `agent_name` | `str` | `"Assistant"` | Name of the agent |
| `agent_description` | `str` | `""` | Description of the agent's capabilities |
| `model_id` | `str` | `None` | Model ID (defaults to Claude Haiku) |

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `llm_client` | `BedrockLLM` | LLM client |
| `agent_name` | `str` | Agent name |
| `agent_description` | `str` | Agent description |
| `model_id` | `str` | Model for routing decisions |

### Methods

#### should_agent_respond()

Determine if the agent should respond to the latest message.

```python
def should_agent_respond(
    self,
    slack_thread: str
) -> dict
```

##### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `slack_thread` | `str` | Complete Slack thread conversation |

##### Returns

```python
{
    "should_respond": bool,  # True if agent should respond
    "reasoning": str         # Brief explanation
}
```

##### Decision Criteria

**RESPOND when:**
- Bot is directly mentioned (@BotName)
- User asks for clarification on agent's previous response
- User reports an error with agent's suggestion
- Follow-up request ("also can you...", "now do...")
- Contains question words directed at agent
- Direct question immediately after agent responded
- Someone asks a direct question the bot can help with

**REMAIN SILENT when:**
- Just acknowledgment ("thanks", "got it", "ok")
- Shifts to different topic outside agent's domain
- Tags a different agent (@other-agent)
- Conversation between humans
- Off-topic chitchat
- Personal/private discussion
- Topic outside bot's expertise

**Default:** When in doubt, **REMAIN SILENT**

---

## Configuration

### Creating a Router

```python
from dcaf.llm import BedrockLLM
from dcaf.channel_routing import SlackResponseRouter

# Create LLM client
llm = BedrockLLM(region_name="us-east-1")

# Create router with description
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="K8sBot",
    agent_description="""
    K8sBot is a Kubernetes and DevOps assistant that helps with:
    - Kubernetes troubleshooting and management
    - Helm chart creation and deployment
    - Docker and container issues
    - DuploCloud platform operations
    """,
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0"  # Fast model
)
```

### Using with Core API (`serve()` / `create_app()`)

The recommended way to use channel routing with DCAF Core agents:

```python
from dcaf.core import Agent, serve, SlackResponseRouter
from dcaf.llm import BedrockLLM

agent = Agent(
    tools=[...],
    system_prompt="You are a Kubernetes assistant.",
)

llm = BedrockLLM()
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="k8s-agent",
    agent_description="Kubernetes and container orchestration specialist",
)

# Pass channel_router to serve()
serve(agent, channel_router=router, port=8000)
```

Or with `create_app()` for programmatic control:

```python
from dcaf.core import Agent, create_app, SlackResponseRouter
from dcaf.llm import BedrockLLM
import uvicorn

agent = Agent(tools=[...])
llm = BedrockLLM()
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="k8s-agent",
    agent_description="Kubernetes specialist",
)

app = create_app(agent, channel_router=router)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Using with Agent Server (Legacy)

```python
from dcaf.agent_server import create_chat_app
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM
from dcaf.channel_routing import SlackResponseRouter

# Create components
llm = BedrockLLM()
agent = ToolCallingAgent(llm=llm, tools=[...], system_prompt="...")

# Create router
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="HelpBot",
    agent_description="A general-purpose help assistant"
)

# Create app with router
app = create_chat_app(agent, router=router)
```

### Request Format for Slack

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Can someone help with this deployment issue?",
            "user": {"name": "alice", "id": "U123"}
        },
        {
            "role": "assistant",
            "content": "I can help! What's the error message?",
            "agent": {"name": "HelpBot", "id": "B456"}
        },
        {
            "role": "user",
            "content": "@charlie can you check the logs?",
            "user": {"name": "bob", "id": "U789"}
        }
    ],
    "source": "slack"
}
```

---

## Examples

### Example 1: Basic Slack Router

```python
from dcaf.llm import BedrockLLM
from dcaf.channel_routing import SlackResponseRouter

llm = BedrockLLM()

router = SlackResponseRouter(
    llm_client=llm,
    agent_name="SupportBot",
    agent_description="Technical support assistant"
)

# Test with a thread
thread = """
[alice]: Hey team, anyone know how to fix this Kubernetes error?
[SupportBot]: I can help! What's the error message?
[alice]: Thanks!
"""

result = router.should_agent_respond(thread)
print(f"Should respond: {result['should_respond']}")
print(f"Reasoning: {result['reasoning']}")
# Should respond: False (just a "thanks" acknowledgment)
```

### Example 2: Multi-Agent Routing

```python
from dcaf.llm import BedrockLLM
from dcaf.channel_routing import SlackResponseRouter

llm = BedrockLLM()

# Create specialized routers
k8s_router = SlackResponseRouter(
    llm_client=llm,
    agent_name="K8sBot",
    agent_description="Kubernetes and container orchestration specialist"
)

aws_router = SlackResponseRouter(
    llm_client=llm,
    agent_name="AWSBot",
    agent_description="AWS cloud infrastructure specialist"
)

# Test with a thread
thread = """
[user1]: My pods keep crashing with OOMKilled
[K8sBot]: This usually means your containers are running out of memory. 
         Try increasing the memory limits in your deployment.
[user1]: Actually, I think this might be an AWS issue with the node
"""

# Check each router
k8s_result = k8s_router.should_agent_respond(thread)
aws_result = aws_router.should_agent_respond(thread)

print(f"K8sBot should respond: {k8s_result['should_respond']}")
print(f"AWSBot should respond: {aws_result['should_respond']}")
```

### Example 3: Full Server Integration (Core API)

```python
from dcaf.core import Agent, serve, SlackResponseRouter
from dcaf.tools import tool
from dcaf.llm import BedrockLLM

# Create tools
@tool(description="Check the status of Kubernetes pods")
def check_pod_status(namespace: str = "default") -> str:
    return f"All pods in {namespace} are running"

# Create agent
agent = Agent(
    tools=[check_pod_status],
    system_prompt="You are K8sBot, a Kubernetes expert.",
)

# Create router
llm = BedrockLLM()
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="K8sBot",
    agent_description="""
    K8sBot specializes in:
    - Kubernetes troubleshooting
    - Pod and deployment management
    - Container orchestration
    - kubectl commands
    """,
)

# Serve with channel routing
if __name__ == "__main__":
    serve(agent, channel_router=router, port=8000)
```

### Example 3b: Full Server Integration (Legacy API)

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.channel_routing import SlackResponseRouter
from dcaf.agent_server import create_chat_app
import uvicorn

# Create LLM
llm = BedrockLLM()

# Create tools
@tool(
    schema={
        "name": "check_pod_status",
        "description": "Check the status of Kubernetes pods",
        "input_schema": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"}
            },
            "required": ["namespace"]
        }
    },
    requires_approval=False
)
def check_pod_status(namespace: str) -> str:
    return f"All pods in {namespace} are running"

# Create agent
agent = ToolCallingAgent(
    llm=llm,
    tools=[check_pod_status],
    system_prompt="You are K8sBot, a Kubernetes expert."
)

# Create router
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="K8sBot",
    agent_description="""
    K8sBot specializes in:
    - Kubernetes troubleshooting
    - Pod and deployment management
    - Container orchestration
    - kubectl commands
    """
)

# Create app with router
app = create_chat_app(agent, router=router)

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

### Example 4: Testing Router Decisions

```python
from dcaf.llm import BedrockLLM
from dcaf.channel_routing import SlackResponseRouter

llm = BedrockLLM()
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="HelpBot",
    agent_description="General help assistant"
)

# Test cases
test_threads = [
    # Should respond - direct mention
    ("""
    [alice]: @HelpBot can you help with this?
    """, True),
    
    # Should respond - follow-up question
    ("""
    [alice]: How do I deploy to production?
    [HelpBot]: You can use kubectl apply -f deploy.yaml
    [alice]: What namespace should I use?
    """, True),
    
    # Should NOT respond - acknowledgment
    ("""
    [alice]: Help me with deployment
    [HelpBot]: Here's the command: kubectl apply...
    [alice]: Thanks!
    """, False),
    
    # Should NOT respond - different agent mentioned
    ("""
    [alice]: @OtherBot can you check the logs?
    """, False),
    
    # Should NOT respond - off-topic
    ("""
    [alice]: Anyone want to grab lunch?
    [bob]: Sure, let's go!
    """, False),
]

print("Router Decision Tests")
print("=" * 50)

for thread, expected in test_threads:
    result = router.should_agent_respond(thread)
    status = "✓" if result["should_respond"] == expected else "✗"
    print(f"{status} Expected: {expected}, Got: {result['should_respond']}")
    if result["should_respond"] != expected:
        print(f"   Reasoning: {result['reasoning']}")
```

### Example 5: Custom Router Implementation

```python
from dcaf.channel_routing import ChannelResponseRouter
from dcaf.llm import BedrockLLM
import re

class KeywordRouter(ChannelResponseRouter):
    """
    Simple keyword-based router that doesn't use LLM.
    """
    
    def __init__(self, agent_name: str, keywords: list):
        self.agent_name = agent_name
        self.keywords = keywords
    
    def should_agent_respond(self, messages: list) -> dict:
        # Get last user message
        last_user = next(
            (m for m in reversed(messages) if m.get("role") == "user"),
            None
        )
        
        if not last_user:
            return {"should_respond": False, "reasoning": "No user message"}
        
        content = last_user.get("content", "").lower()
        
        # Check for direct mention
        if f"@{self.agent_name.lower()}" in content:
            return {
                "should_respond": True,
                "reasoning": "Direct mention"
            }
        
        # Check for keywords
        for keyword in self.keywords:
            if keyword.lower() in content:
                return {
                    "should_respond": True,
                    "reasoning": f"Matched keyword: {keyword}"
                }
        
        return {
            "should_respond": False,
            "reasoning": "No matching keywords"
        }

# Usage
router = KeywordRouter(
    agent_name="K8sBot",
    keywords=["kubernetes", "kubectl", "pod", "deployment", "k8s"]
)

# Test
messages = [
    {"role": "user", "content": "My kubernetes pods are failing"}
]

result = router.should_agent_respond(messages)
print(result)
# {'should_respond': True, 'reasoning': 'Matched keyword: kubernetes'}
```

---

## See Also

- [Core Server — Channel Routing](../core/server.md#channel-routing) - Using channel routing with `serve()` and `create_app()`
- [Agent Server API Reference](./agent-server.md)
- [Agents API Reference](./agents.md)
- [BedrockLLM API Reference](./llm.md)

