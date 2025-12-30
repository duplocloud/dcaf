# Agents API Reference (Legacy)

!!! warning "Legacy API"
    This documents the **v1 API**. For new projects, use the [Core API](../core/index.md) instead.
    
    See [Migration Guide](../guides/migration.md) to upgrade existing code.

The Agents module provides pre-built agent implementations and the `AgentProtocol` interface for creating custom agents.

---

## Table of Contents

1. [Overview](#overview)
2. [AgentProtocol](#agentprotocol)
3. [ToolCallingAgent](#toolcallingagent)
4. [ToolCallingCmdAgent](#toolcallingcmdagent)
5. [Other Agents](#other-agents)
6. [Creating Custom Agents](#creating-custom-agents)
7. [Examples](#examples)

---

## Overview

DCAF provides several agent implementations:

| Agent | Description | Use Case |
|-------|-------------|----------|
| `ToolCallingAgent` | Full-featured agent with tool execution | General purpose with tools |
| `ToolCallingCmdAgent` | Agent with terminal command support | CLI-style interactions |
| `EchoAgent` | Simple echo for testing | Development/testing |
| `LLMPassthroughAgent` | Direct LLM passthrough | Simple chat |
| `BoilerplateAgent` | Template for custom agents | Starting point |
| `AWSAgent` | AWS CLI command agent | AWS operations |
| `K8sAgent` | Kubernetes/Helm agent | K8s operations |
| `CommandAgent` | Terminal command agent | Shell operations |

### Import

```python
from dcaf.agents import ToolCallingAgent, ToolCallingCmdAgent

# Or individual agents
from dcaf.agents.tool_calling_agent import ToolCallingAgent
from dcaf.agents.echo_agent import EchoAgent
```

---

## AgentProtocol

The `AgentProtocol` defines the interface that all agents must implement.

```python
from typing import Protocol, runtime_checkable, Dict, Any, List
from dcaf.schemas.messages import AgentMessage

@runtime_checkable            
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """Process messages and return a response."""
        ...
```

### Method: invoke()

```python
def invoke(
    self, 
    messages: Dict[str, List[Dict[str, Any]]]
) -> AgentMessage
```

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `messages` | `Dict` | Message dictionary with `"messages"` key |

#### Message Format

```python
{
    "messages": [
        {
            "role": "user",
            "content": "Hello!",
            "data": {...},           # Optional: Data payload
            "platform_context": {...} # Optional: Runtime context
        },
        {
            "role": "assistant",
            "content": "Hi there!",
            "data": {...}
        }
    ]
}
```

#### Returns

`AgentMessage` - The agent's response with content and data.

---

## ToolCallingAgent

The primary agent for tool-based interactions with approval workflows.

```python
class ToolCallingAgent:
    """Agent that can call tools and suggest terminal commands."""
```

### Constructor

```python
def __init__(
    self,
    llm: BedrockLLM,
    tools: List[Tool],
    system_prompt: str = "You are a helpful assistant.",
    model_id: str = "us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations: int = 10,
    enable_terminal_cmds: bool = False,
    llm_visible_platform_context_fields: List[str] = ["tenant_name"]
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm` | `BedrockLLM` | Required | LLM instance for model calls |
| `tools` | `List[Tool]` | Required | List of tools available to agent |
| `system_prompt` | `str` | `"You are a helpful assistant."` | System prompt for LLM |
| `model_id` | `str` | `"us.anthropic.claude-3-5-sonnet-20240620-v1:0"` | Bedrock model ID |
| `max_iterations` | `int` | `10` | Max LLM call iterations |
| `enable_terminal_cmds` | `bool` | `False` | Enable terminal command suggestions |
| `llm_visible_platform_context_fields` | `List[str]` | `["tenant_name"]` | Context fields visible to LLM |

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `llm` | `BedrockLLM` | LLM client |
| `tools` | `Dict[str, Tool]` | Tools by name |
| `system_prompt` | `str` | System prompt |
| `model_id` | `str` | Model ID |
| `max_iterations` | `int` | Max iterations |
| `tool_schemas` | `List[Dict]` | LLM-ready tool schemas |

### Methods

#### invoke()

Main entry point for agent interaction.

```python
def invoke(
    self,
    messages: Dict[str, List[Dict[str, Any]]]
) -> AgentMessage
```

**Behavior:**
1. Extracts platform context from last user message
2. Processes any approved tool calls
3. Runs LLM loop until response or max iterations
4. Handles tool execution and approval requests

#### execute_tool()

Execute a specific tool.

```python
def execute_tool(
    self, 
    tool_name: str, 
    tool_input: Dict[str, Any],
    platform_context: Dict[str, Any]
) -> str
```

#### create_tool_call_for_approval()

Create a `ToolCall` object for user approval.

```python
def create_tool_call_for_approval(
    self,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_use_id: str
) -> ToolCall
```

#### process_approved_tool_calls()

Process approved tools from incoming messages.

```python
def process_approved_tool_calls(
    self,
    messages: Dict[str, List[Dict[str, Any]]],
    platform_context: Dict[str, Any]
) -> List[ExecutedToolCall]
```

#### process_tool_calls()

Process tool calls from LLM response.

```python
def process_tool_calls(
    self,
    response_content: List[Dict[str, Any]],
    platform_context: Dict[str, Any]
) -> tuple[List[ExecutedToolCall], List[ToolCall]]
```

Returns:
- `executed`: Tools that ran immediately
- `approval_needed`: Tools requiring user approval

#### preprocess_messages()

Convert input messages to LLM format with context injection.

```python
def preprocess_messages(
    self,
    messages: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]
```

### Complete Example

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import uvicorn
import dotenv

dotenv.load_dotenv()

# Define tools
@tool(
    schema={
        "name": "get_weather",
        "description": "Get current weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and state, e.g., 'San Francisco, CA'"
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "default": "fahrenheit"
                }
            },
            "required": ["location"]
        }
    },
    requires_approval=False
)
def get_weather(location: str, unit: str = "fahrenheit") -> str:
    # Simulated weather
    return f"The weather in {location} is 72°{unit[0].upper()}, sunny"

@tool(
    schema={
        "name": "send_notification",
        "description": "Send a notification to a user",
        "input_schema": {
            "type": "object",
            "properties": {
                "user": {"type": "string", "description": "Username"},
                "message": {"type": "string", "description": "Notification message"}
            },
            "required": ["user", "message"]
        }
    },
    requires_approval=True  # Requires user approval
)
def send_notification(user: str, message: str) -> str:
    return f"Notification sent to {user}: {message}"

# Create agent
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[get_weather, send_notification],
    system_prompt="""You are a helpful assistant.
    Use tools when appropriate to help the user.""",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations=10
)

# Create and run server
app = create_chat_app(agent)
uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Tool Execution Flow

```
User Message
    │
    ▼
┌───────────────────┐
│ preprocess_messages│
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ process_approved  │◄──┐
│ _tool_calls       │   │
└─────────┬─────────┘   │
          │             │
          ▼             │
┌───────────────────┐   │
│   LLM.invoke()    │   │
└─────────┬─────────┘   │
          │             │
          ▼             │
    ┌───────────┐       │
    │Tool Calls?│       │
    └─────┬─────┘       │
          │             │
    ┌─────┴─────┐       │
    │           │       │
    ▼           ▼       │
┌───────┐  ┌────────┐   │
│Execute│  │Approval│   │
│ Auto  │  │Required│   │
└───┬───┘  └────┬───┘   │
    │           │       │
    ▼           ▼       │
┌───────┐  ┌────────┐   │
│Add to │  │ Return │   │
│Context│  │ToolCall│   │
└───┬───┘  └────────┘   │
    │                   │
    └───────────────────┘
          │
          ▼ (after approval)
┌───────────────────┐
│  Return Response  │
└───────────────────┘
```

---

## ToolCallingCmdAgent

Agent with built-in terminal command support and example tools.

```python
class ToolCallingCmdAgent(AgentProtocol):
    def __init__(self, llm: BedrockLLM)
```

### Built-in Tools

| Tool | Description |
|------|-------------|
| `get_weather` | Get weather for a location |
| `get_stock_price` | Get stock price for a ticker |
| `get_current_time` | Get current date and time |
| `return_final_response_to_user` | Return structured response with commands |

### Example

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingCmdAgent
from dcaf.agent_server import create_chat_app

llm = BedrockLLM()
agent = ToolCallingCmdAgent(llm)
app = create_chat_app(agent)
```

---

## Other Agents

### EchoAgent

Simple agent that echoes back user messages. Useful for testing.

```python
from dcaf.agents.echo_agent import EchoAgent
from dcaf.agent_server import create_chat_app

agent = EchoAgent()
app = create_chat_app(agent)

# Test
# Input: {"messages": [{"role": "user", "content": "Hello!"}]}
# Output: {"role": "assistant", "content": "Echo: Hello!"}
```

### LLMPassthroughAgent

Direct passthrough to LLM without tool support.

```python
from dcaf.llm import BedrockLLM
from dcaf.agents.llm_passthrough_agent import LLMPassthroughAgent

llm = BedrockLLM()
agent = LLMPassthroughAgent(llm)
```

### BoilerplateAgent

Template for creating custom agents.

```python
from dcaf.agents.boilerplate_agent import BoilerplateAgent
from dcaf.schemas.messages import AgentMessage

class MyAgent(BoilerplateAgent):
    def invoke(self, messages):
        # Your custom logic here
        return AgentMessage(content="Custom response")
```

### AWSAgent

Agent specialized for AWS CLI operations.

```python
from dcaf.agents.aws_agent import AWSAgent
from dcaf.llm import BedrockLLM

llm = BedrockLLM()
agent = AWSAgent(
    llm=llm,
    system_prompt="Custom AWS assistant prompt"  # Optional
)
```

Features:
- AWS CLI command suggestions
- Command approval workflow
- Structured response schema
- DuploCloud context awareness

### K8sAgent

Agent specialized for Kubernetes and Helm operations.

```python
from dcaf.agents.k8s_agent import K8sAgent
from dcaf.llm import BedrockLLM

llm = BedrockLLM()
agent = K8sAgent(llm)
```

Features:
- kubectl command suggestions
- Helm chart creation
- Docker Compose to Helm conversion
- Service rollback support
- Kubeconfig handling (base64 encoded)
- File creation for commands

### CommandAgent

General-purpose terminal command agent.

```python
from dcaf.agents.cmd_agent import CommandAgent
from dcaf.llm import BedrockLLM

llm = BedrockLLM()
agent = CommandAgent(
    llm=llm,
    system_prompt="Custom terminal assistant"  # Optional
)
```

---

## Creating Custom Agents

### Method 1: Implement AgentProtocol

```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage, Data, ToolCall
from typing import Dict, Any, List

class MyCustomAgent(AgentProtocol):
    """Custom agent implementation."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
    
    def invoke(
        self, 
        messages: Dict[str, List[Dict[str, Any]]]
    ) -> AgentMessage:
        # Extract messages
        messages_list = messages.get("messages", [])
        
        # Get last user message
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            None
        )
        
        if not last_user:
            return AgentMessage(content="No message received")
        
        user_content = last_user.get("content", "")
        
        # Your custom logic here
        response = self.process_message(user_content)
        
        return AgentMessage(content=response)
    
    def process_message(self, content: str) -> str:
        # Custom processing
        return f"Processed: {content}"
```

### Method 2: Extend BoilerplateAgent

```python
from dcaf.agents.boilerplate_agent import BoilerplateAgent
from dcaf.schemas.messages import AgentMessage

class SmartBoilerplate(BoilerplateAgent):
    def __init__(self, name: str = "Bot"):
        self.name = name
    
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        
        # Count messages
        user_msgs = sum(1 for m in messages_list if m.get("role") == "user")
        
        return AgentMessage(
            content=f"Hello! I'm {self.name}. "
                   f"You've sent {user_msgs} message(s) so far."
        )
```

### Method 3: Extend ToolCallingAgent

```python
from dcaf.agents.tool_calling_agent import ToolCallingAgent
from dcaf.llm import BedrockLLM
from dcaf.tools import tool
from dcaf.schemas.messages import AgentMessage

class EnhancedToolAgent(ToolCallingAgent):
    """ToolCallingAgent with custom pre/post processing."""
    
    def __init__(self, llm: BedrockLLM, **kwargs):
        # Create custom tools
        my_tools = self.create_tools()
        super().__init__(llm=llm, tools=my_tools, **kwargs)
    
    def create_tools(self):
        @tool(
            schema={
                "name": "custom_action",
                "description": "Perform custom action",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"}
                    },
                    "required": ["action"]
                }
            }
        )
        def custom_action(action: str) -> str:
            return f"Performed: {action}"
        
        return [custom_action]
    
    def invoke(self, messages):
        # Pre-processing
        self.log_request(messages)
        
        # Call parent implementation
        response = super().invoke(messages)
        
        # Post-processing
        self.log_response(response)
        
        return response
    
    def log_request(self, messages):
        print(f"Received {len(messages.get('messages', []))} messages")
    
    def log_response(self, response):
        print(f"Responding with: {response.content[:50]}...")
```

---

## Examples

### Example 1: Simple Q&A Agent

```python
from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
import uvicorn

class QAAgent(AgentProtocol):
    """Simple Q&A agent with predefined answers."""
    
    def __init__(self):
        self.answers = {
            "what is dcaf": "DCAF is the DuploCloud Agent Framework",
            "who made dcaf": "DCAF was created by DuploCloud",
            "how do i use dcaf": "See the documentation at docs/index.md"
        }
    
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {"content": ""}
        )
        
        question = last_user.get("content", "").lower().strip("?")
        
        # Find matching answer
        for key, answer in self.answers.items():
            if key in question:
                return AgentMessage(content=answer)
        
        return AgentMessage(
            content="I don't know the answer to that. "
                   "Try asking about DCAF!"
        )

agent = QAAgent()
app = create_chat_app(agent)

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

### Example 2: Stateful Agent

```python
from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
from collections import defaultdict
import uvicorn

class StatefulAgent(AgentProtocol):
    """Agent that maintains state across requests."""
    
    def __init__(self):
        self.user_data = defaultdict(dict)
    
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        
        # Get user from platform context
        last_user_msg = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        platform_context = last_user_msg.get("platform_context", {})
        user_id = platform_context.get("user_id", "anonymous")
        
        content = last_user_msg.get("content", "")
        
        # Track interaction count
        if "count" not in self.user_data[user_id]:
            self.user_data[user_id]["count"] = 0
        self.user_data[user_id]["count"] += 1
        
        count = self.user_data[user_id]["count"]
        
        return AgentMessage(
            content=f"Hello {user_id}! This is interaction #{count}. "
                   f"You said: {content}"
        )

agent = StatefulAgent()
app = create_chat_app(agent)
```

### Example 3: Multi-Tool Agent

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import dotenv

dotenv.load_dotenv()

# Define multiple tools
@tool(
    schema={
        "name": "search_products",
        "description": "Search for products in the catalog",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["electronics", "clothing", "home", "all"]
                },
                "max_results": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    requires_approval=False
)
def search_products(query: str, category: str = "all", max_results: int = 5) -> str:
    return f"Found {max_results} products for '{query}' in {category}"

@tool(
    schema={
        "name": "add_to_cart",
        "description": "Add a product to the shopping cart",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1}
            },
            "required": ["product_id", "quantity"]
        }
    },
    requires_approval=True  # Requires confirmation
)
def add_to_cart(product_id: str, quantity: int, platform_context: dict) -> str:
    user = platform_context.get("user_id", "guest")
    return f"Added {quantity}x {product_id} to {user}'s cart"

@tool(
    schema={
        "name": "checkout",
        "description": "Process checkout for the cart",
        "input_schema": {
            "type": "object",
            "properties": {
                "payment_method": {
                    "type": "string",
                    "enum": ["credit_card", "paypal", "bank_transfer"]
                }
            },
            "required": ["payment_method"]
        }
    },
    requires_approval=True
)
def checkout(payment_method: str, platform_context: dict) -> str:
    user = platform_context.get("user_id", "guest")
    return f"Checkout completed for {user} via {payment_method}"

# Create agent
llm = BedrockLLM()
agent = ToolCallingAgent(
    llm=llm,
    tools=[search_products, add_to_cart, checkout],
    system_prompt="""You are a helpful shopping assistant.
    Help users find products, add them to cart, and checkout.
    Always confirm before adding to cart or checking out."""
)

app = create_chat_app(agent)
```

---

## See Also

- [Agent Server API Reference](./agent-server.md)
- [Tools API Reference](./tools.md)
- [Creating Custom Agents Guide](../guides/creating-custom-agents.md)
- [Schemas API Reference](./schemas.md)

