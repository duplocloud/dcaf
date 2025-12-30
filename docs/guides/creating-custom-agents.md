# Creating Custom Agents Guide (Legacy)

!!! warning "Legacy Guide"
    This documents the **v1 API**. For new projects, see [Custom Agents](./custom-agents.md) using the Core API.
    
    See [Migration Guide](./migration.md) to upgrade existing code.

This guide covers how to create custom agents in DCAF using the v1 API.

---

## Table of Contents

1. [Introduction](#introduction)
2. [The AgentProtocol Interface](#the-agentprotocol-interface)
3. [Simple Custom Agents](#simple-custom-agents)
4. [Tool-Enabled Agents](#tool-enabled-agents)
5. [Stateful Agents](#stateful-agents)
6. [Multi-Agent Systems](#multi-agent-systems)
7. [Testing Custom Agents](#testing-custom-agents)
8. [Best Practices](#best-practices)

---

## Introduction

DCAF agents are Python classes that implement the `AgentProtocol` interface. This simple contract allows you to create agents that:

- Receive conversation messages
- Process them using any logic you need
- Return structured responses

### When to Create a Custom Agent

Create a custom agent when:
- Built-in agents don't fit your use case
- You need specialized processing logic
- You want to integrate with external systems
- You need custom state management
- You want to combine multiple LLMs or services

---

## The AgentProtocol Interface

Every agent must implement this interface:

```python
from typing import Protocol, runtime_checkable, Dict, Any, List
from dcaf.schemas.messages import AgentMessage

@runtime_checkable            
class AgentProtocol(Protocol):
    """Any agent that can respond to a chat."""
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        """
        Process messages and return a response.
        
        Args:
            messages: Dictionary with "messages" key containing conversation history
            
        Returns:
            AgentMessage with response content and optional data
        """
        ...
```

### Message Format

```python
# Input format
{
    "messages": [
        {
            "role": "user",
            "content": "Hello!",
            "data": {...},
            "platform_context": {...}
        },
        {
            "role": "assistant", 
            "content": "Hi there!"
        }
    ]
}
```

### Response Format

```python
from dcaf.schemas.messages import AgentMessage, Data

AgentMessage(
    role="assistant",
    content="Response text",
    data=Data(
        cmds=[...],              # Suggested commands
        tool_calls=[...],        # Tools needing approval
        executed_tool_calls=[...] # Executed tools
    )
)
```

---

## Simple Custom Agents

### Example 1: Echo Agent

The simplest possible agent:

```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage
from typing import Dict, Any, List

class EchoAgent(AgentProtocol):
    """Echoes back user messages."""
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        messages_list = messages.get("messages", [])
        
        # Find last user message
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            None
        )
        
        if last_user:
            return AgentMessage(content=f"Echo: {last_user.get('content', '')}")
        
        return AgentMessage(content="No message to echo")
```

### Example 2: Greeting Agent

Agent with configurable behavior:

```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage
from typing import Dict, Any, List

class GreetingAgent(AgentProtocol):
    """Greets users with a personalized message."""
    
    def __init__(self, greeting_template: str = "Hello, {name}!"):
        self.greeting_template = greeting_template
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        messages_list = messages.get("messages", [])
        
        # Get user info from platform context
        last_user_msg = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        
        platform_context = last_user_msg.get("platform_context", {})
        user_name = platform_context.get("user_id", "Guest")
        
        greeting = self.greeting_template.format(name=user_name)
        return AgentMessage(content=greeting)
```

### Example 3: FAQ Agent

Agent with predefined responses:

```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage
from typing import Dict, Any, List
import re

class FAQAgent(AgentProtocol):
    """Answers frequently asked questions."""
    
    def __init__(self):
        self.faqs = {
            r"what is (dcaf|duplocloud agent framework)": 
                "DCAF is the DuploCloud Agent Framework for building AI agents.",
            r"how do i (install|set up)":
                "Install with: pip install git+https://github.com/duplocloud/service-desk-agents.git",
            r"where is the documentation":
                "Documentation is at docs/index.md in the repository.",
            r"(help|what can you do)":
                "I can answer questions about DCAF. Ask about installation, features, or usage."
        }
        self.default_response = "I don't have an answer for that. Try asking about DCAF installation or features."
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        messages_list = messages.get("messages", [])
        
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        
        question = last_user.get("content", "").lower()
        
        # Match against FAQ patterns
        for pattern, answer in self.faqs.items():
            if re.search(pattern, question):
                return AgentMessage(content=answer)
        
        return AgentMessage(content=self.default_response)
```

---

## Tool-Enabled Agents

### Extending ToolCallingAgent

```python
from dcaf.agents.tool_calling_agent import ToolCallingAgent
from dcaf.llm import BedrockLLM
from dcaf.tools import tool
from dcaf.schemas.messages import AgentMessage

class EnhancedToolAgent(ToolCallingAgent):
    """ToolCallingAgent with custom enhancements."""
    
    def __init__(self, llm: BedrockLLM, company_name: str = "Acme"):
        # Create custom tools
        tools = self._create_tools()
        
        # Custom system prompt
        system_prompt = f"""You are an assistant for {company_name}.
        Use the available tools to help users.
        Be concise and helpful."""
        
        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        )
        
        self.company_name = company_name
    
    def _create_tools(self):
        @tool(
            schema={
                "name": "get_company_info",
                "description": "Get company information",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        )
        def get_company_info() -> str:
            return "Company info here..."
        
        return [get_company_info]
    
    def invoke(self, messages):
        # Pre-processing
        self._log_request(messages)
        
        # Call parent
        response = super().invoke(messages)
        
        # Post-processing
        self._log_response(response)
        
        return response
    
    def _log_request(self, messages):
        msg_count = len(messages.get("messages", []))
        print(f"[{self.company_name}] Processing {msg_count} messages")
    
    def _log_response(self, response):
        print(f"[{self.company_name}] Responded: {response.content[:50]}...")
```

### Building from Scratch

```python
from dcaf.agent_server import AgentProtocol
from dcaf.llm import BedrockLLM
from dcaf.tools import tool, Tool
from dcaf.schemas.messages import AgentMessage, Data, ToolCall, ExecutedToolCall
from typing import Dict, Any, List

class CustomToolAgent(AgentProtocol):
    """Custom agent with tool support built from scratch."""
    
    def __init__(self, llm: BedrockLLM):
        self.llm = llm
        self.tools = self._create_tools()
        self.tool_schemas = [t.get_schema() for t in self.tools]
        self.tool_map = {t.name: t for t in self.tools}
    
    def _create_tools(self) -> List[Tool]:
        @tool(
            schema={
                "name": "search",
                "description": "Search for information",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            },
            requires_approval=False
        )
        def search(query: str) -> str:
            return f"Found results for: {query}"
        
        return [search]
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        # Prepare conversation
        conversation = self._preprocess_messages(messages)
        
        # Call LLM
        response = self.llm.invoke(
            messages=conversation,
            model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
            system_prompt="You are helpful. Use tools when needed.",
            tools=self.tool_schemas,
            max_tokens=1000
        )
        
        # Process response
        return self._process_response(response, messages)
    
    def _preprocess_messages(self, messages):
        processed = []
        for msg in messages.get("messages", []):
            if msg.get("role") in ["user", "assistant"]:
                processed.append({
                    "role": msg["role"],
                    "content": msg.get("content", "")
                })
        return processed
    
    def _process_response(self, response, original_messages):
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        
        executed_tools = []
        text_content = ""
        
        for block in content_blocks:
            if "text" in block:
                text_content = block["text"]
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                tool_name = tool_use["name"]
                tool_input = tool_use["input"]
                
                if tool_name in self.tool_map:
                    tool = self.tool_map[tool_name]
                    result = tool.execute(tool_input)
                    
                    executed_tools.append(ExecutedToolCall(
                        id=tool_use["toolUseId"],
                        name=tool_name,
                        input=tool_input,
                        output=result
                    ))
        
        return AgentMessage(
            content=text_content or "I processed your request.",
            data=Data(executed_tool_calls=executed_tools)
        )
```

---

## Stateful Agents

### In-Memory State

```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage
from collections import defaultdict
from typing import Dict, Any, List

class StatefulAgent(AgentProtocol):
    """Agent that maintains state across requests."""
    
    def __init__(self):
        # Per-user state
        self.user_state = defaultdict(lambda: {
            "interactions": 0,
            "preferences": {},
            "last_topic": None
        })
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        messages_list = messages.get("messages", [])
        
        # Get user ID
        user_id = self._get_user_id(messages_list)
        
        # Update state
        self.user_state[user_id]["interactions"] += 1
        count = self.user_state[user_id]["interactions"]
        
        # Get last message
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        content = last_user.get("content", "")
        
        # Store topic
        self.user_state[user_id]["last_topic"] = content[:50]
        
        return AgentMessage(
            content=f"Hello {user_id}! This is interaction #{count}. "
                   f"You said: {content}"
        )
    
    def _get_user_id(self, messages_list):
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                context = msg.get("platform_context", {})
                return context.get("user_id", "anonymous")
        return "anonymous"
```

### Persistent State with Redis

```python
import redis
import json
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage

class RedisStatefulAgent(AgentProtocol):
    """Agent with Redis-backed persistent state."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
    
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        user_id = self._get_user_id(messages_list)
        
        # Get or initialize state
        state = self._get_state(user_id)
        state["interactions"] = state.get("interactions", 0) + 1
        
        # Save state
        self._save_state(user_id, state)
        
        return AgentMessage(
            content=f"Welcome back! Interaction #{state['interactions']}"
        )
    
    def _get_state(self, user_id):
        data = self.redis.get(f"agent:state:{user_id}")
        return json.loads(data) if data else {}
    
    def _save_state(self, user_id, state):
        self.redis.set(
            f"agent:state:{user_id}",
            json.dumps(state),
            ex=86400  # 24 hour TTL
        )
    
    def _get_user_id(self, messages_list):
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                return msg.get("platform_context", {}).get("user_id", "anon")
        return "anon"
```

---

## Multi-Agent Systems

### Router Agent

```python
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage
from dcaf.llm import BedrockLLM
from typing import Dict, Any, List

class RouterAgent(AgentProtocol):
    """Routes requests to specialized sub-agents."""
    
    def __init__(self, llm: BedrockLLM, agents: Dict[str, AgentProtocol]):
        self.llm = llm
        self.agents = agents
    
    def invoke(self, messages: Dict[str, List[Dict[str, Any]]]) -> AgentMessage:
        # Get the last user message
        messages_list = messages.get("messages", [])
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        content = last_user.get("content", "")
        
        # Classify the request
        agent_name = self._classify_request(content)
        
        if agent_name in self.agents:
            # Route to specialized agent
            return self.agents[agent_name].invoke(messages)
        else:
            return AgentMessage(
                content="I'm not sure how to help with that. "
                       "Try asking about Kubernetes, AWS, or general help."
            )
    
    def _classify_request(self, content: str) -> str:
        """Use LLM to classify the request."""
        response = self.llm.invoke(
            messages=[{
                "role": "user",
                "content": f"Classify this request into one of: kubernetes, aws, general\n\nRequest: {content}"
            }],
            model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            max_tokens=10,
            temperature=0
        )
        
        classification = response["output"]["message"]["content"][0]["text"].lower()
        
        if "kubernetes" in classification or "k8s" in classification:
            return "k8s"
        elif "aws" in classification:
            return "aws"
        else:
            return "general"

# Usage
from dcaf.agents.k8s_agent import K8sAgent
from dcaf.agents.aws_agent import AWSAgent

llm = BedrockLLM()
router = RouterAgent(
    llm=llm,
    agents={
        "k8s": K8sAgent(llm),
        "aws": AWSAgent(llm),
        "general": SimpleAgent()
    }
)
```

### Parallel Agent Execution

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dcaf.agent_server import AgentProtocol
from dcaf.schemas.messages import AgentMessage

class ParallelAgent(AgentProtocol):
    """Runs multiple agents in parallel and combines results."""
    
    def __init__(self, agents: List[AgentProtocol]):
        self.agents = agents
        self.executor = ThreadPoolExecutor(max_workers=len(agents))
    
    def invoke(self, messages):
        # Run all agents in parallel
        futures = [
            self.executor.submit(agent.invoke, messages)
            for agent in self.agents
        ]
        
        # Collect results
        results = []
        for future in futures:
            try:
                result = future.result(timeout=30)
                results.append(result.content)
            except Exception as e:
                results.append(f"Error: {e}")
        
        # Combine results
        combined = "\n\n---\n\n".join(results)
        return AgentMessage(content=combined)
```

---

## Testing Custom Agents

### Unit Tests

```python
import pytest
from dcaf.schemas.messages import AgentMessage
from my_agents import MyCustomAgent

class TestMyCustomAgent:
    def setup_method(self):
        self.agent = MyCustomAgent()
    
    def test_basic_response(self):
        messages = {
            "messages": [
                {"role": "user", "content": "Hello"}
            ]
        }
        
        response = self.agent.invoke(messages)
        
        assert isinstance(response, AgentMessage)
        assert response.role == "assistant"
        assert len(response.content) > 0
    
    def test_empty_messages(self):
        messages = {"messages": []}
        
        response = self.agent.invoke(messages)
        
        assert isinstance(response, AgentMessage)
    
    def test_with_platform_context(self):
        messages = {
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "platform_context": {
                        "user_id": "test_user",
                        "tenant_name": "test_tenant"
                    }
                }
            ]
        }
        
        response = self.agent.invoke(messages)
        
        assert "test_user" in response.content or response.content
```

### Integration Tests

```python
from fastapi.testclient import TestClient
from dcaf.agent_server import create_chat_app
from my_agents import MyCustomAgent

def test_agent_server_integration():
    agent = MyCustomAgent()
    app = create_chat_app(agent)
    client = TestClient(app)
    
    # Test health endpoint
    response = client.get("/health")
    assert response.status_code == 200
    
    # Test send message
    response = client.post(
        "/api/sendMessage",
        json={
            "messages": [
                {"role": "user", "content": "Test message"}
            ]
        }
    )
    assert response.status_code == 200
    assert "content" in response.json()
```

### Mock LLM Testing

```python
from unittest.mock import Mock, patch
from dcaf.llm import BedrockLLM
from my_agents import MyLLMAgent

def test_agent_with_mock_llm():
    # Create mock LLM
    mock_llm = Mock(spec=BedrockLLM)
    mock_llm.invoke.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Mocked response"}]
            }
        }
    }
    
    # Create agent with mock
    agent = MyLLMAgent(llm=mock_llm)
    
    # Test
    response = agent.invoke({
        "messages": [{"role": "user", "content": "Test"}]
    })
    
    assert response.content == "Mocked response"
    mock_llm.invoke.assert_called_once()
```

---

## Best Practices

### 1. Always Return AgentMessage

```python
# ✅ Good
def invoke(self, messages):
    try:
        result = self.process(messages)
        return AgentMessage(content=result)
    except Exception as e:
        return AgentMessage(content=f"Error: {e}")

# ❌ Bad
def invoke(self, messages):
    return self.process(messages)  # May not be AgentMessage
```

### 2. Handle Missing Data Gracefully

```python
# ✅ Good
def invoke(self, messages):
    messages_list = messages.get("messages", [])
    last_user = next(
        (m for m in reversed(messages_list) if m.get("role") == "user"),
        None
    )
    
    if not last_user:
        return AgentMessage(content="No user message found")
    
    content = last_user.get("content", "")
    ...

# ❌ Bad
def invoke(self, messages):
    content = messages["messages"][-1]["content"]  # May crash
```

### 3. Use Logging

```python
import logging

logger = logging.getLogger(__name__)

class MyAgent(AgentProtocol):
    def invoke(self, messages):
        logger.info(f"Processing {len(messages.get('messages', []))} messages")
        
        try:
            result = self._process(messages)
            logger.info(f"Response: {result.content[:100]}...")
            return result
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            return AgentMessage(content=f"Error: {e}")
```

### 4. Make Agents Configurable

```python
class ConfigurableAgent(AgentProtocol):
    def __init__(
        self,
        llm: BedrockLLM,
        system_prompt: str = "You are helpful.",
        max_tokens: int = 1000,
        temperature: float = 0.7
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
```

### 5. Document Your Agents

```python
class DocumentedAgent(AgentProtocol):
    """
    A well-documented agent.
    
    This agent processes user messages and responds using
    a combination of tools and LLM reasoning.
    
    Attributes:
        llm: The LLM client for generating responses
        tools: List of available tools
        
    Configuration:
        Requires platform_context with:
        - user_id: Current user identifier
        - tenant_name: DuploCloud tenant name
        
    Example:
        agent = DocumentedAgent(llm, tools=[my_tool])
        app = create_chat_app(agent)
    """
```

---

## See Also

- [Agents API Reference](../api-reference/agents.md)
- [Building Tools Guide](./building-tools.md)
- [Message Protocol Guide](./message-protocol.md)
- [Examples](../examples/examples.md)

