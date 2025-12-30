# DCAF Code Examples

This page contains comprehensive code examples for using DCAF in various scenarios.

---

## Table of Contents

1. [Quick Start Examples](#quick-start-examples)
2. [Tool Examples](#tool-examples)
3. [Agent Examples](#agent-examples)
4. [Server Examples](#server-examples)
5. [Client Examples](#client-examples)
6. [Advanced Examples](#advanced-examples)

---

## Quick Start Examples

### Minimal Agent

The simplest possible DCAF agent:

```python
#!/usr/bin/env python3
"""minimal_agent.py - Simplest DCAF agent"""

from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
import uvicorn

class MinimalAgent(AgentProtocol):
    def invoke(self, messages):
        return AgentMessage(content="Hello from DCAF!")

app = create_chat_app(MinimalAgent())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Echo Agent

Agent that echoes back user messages:

```python
#!/usr/bin/env python3
"""echo_agent.py - Echo back user messages"""

from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
import uvicorn

class EchoAgent(AgentProtocol):
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {"content": ""}
        )
        text = last_user.get("content", "")
        return AgentMessage(content=f"You said: {text}")

app = create_chat_app(EchoAgent())

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

### LLM Chat Agent

Basic chat agent using Bedrock:

```python
#!/usr/bin/env python3
"""chat_agent.py - Basic LLM chat"""

from dcaf.llm import BedrockLLM
from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
import uvicorn
import dotenv

dotenv.load_dotenv()

class ChatAgent(AgentProtocol):
    def __init__(self):
        self.llm = BedrockLLM(region_name="us-east-1")
        self.model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
    
    def invoke(self, messages):
        # Preprocess messages
        msgs = [
            {"role": m["role"], "content": m.get("content", "")}
            for m in messages.get("messages", [])
            if m.get("role") in ["user", "assistant"]
        ]
        
        # Call LLM
        response = self.llm.invoke(
            messages=msgs,
            model_id=self.model_id,
            system_prompt="You are a helpful assistant.",
            max_tokens=1000
        )
        
        # Extract text
        content = response["output"]["message"]["content"]
        text = next((b["text"] for b in content if "text" in b), "")
        
        return AgentMessage(content=text)

app = create_chat_app(ChatAgent())

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

---

## Tool Examples

### Basic Calculator Tool

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "calculate",
        "description": "Perform arithmetic calculations",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                    "description": "The operation to perform"
                },
                "a": {"type": "number", "description": "First number"},
                "b": {"type": "number", "description": "Second number"}
            },
            "required": ["operation", "a", "b"]
        }
    },
    requires_approval=False
)
def calculate(operation: str, a: float, b: float) -> str:
    """Perform a calculation."""
    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "undefined"
    }
    result = ops[operation](a, b)
    return f"{a} {operation} {b} = {result}"

# Test
print(calculate.execute({"operation": "multiply", "a": 7, "b": 8}))
# Output: 7 multiply 8 = 56
```

### Weather Tool with Enum

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "get_weather",
        "description": "Get weather for a location",
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
                    "description": "Temperature unit",
                    "default": "fahrenheit"
                }
            },
            "required": ["location"]
        }
    },
    requires_approval=False
)
def get_weather(location: str, unit: str = "fahrenheit") -> str:
    """Get weather (simulated)."""
    # In production, call a real weather API
    temps = {"celsius": "22°C", "fahrenheit": "72°F"}
    return f"Weather in {location}: {temps[unit]}, sunny with light clouds"

# Test
print(get_weather.execute({"location": "Seattle, WA"}))
print(get_weather.execute({"location": "London, UK", "unit": "celsius"}))
```

### Tool with Platform Context

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "list_user_resources",
        "description": "List resources for the current user",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "enum": ["pods", "services", "deployments"],
                    "description": "Type of resource to list"
                }
            },
            "required": ["resource_type"]
        }
    },
    requires_approval=False
)
def list_user_resources(resource_type: str, platform_context: dict) -> str:
    """List resources using platform context."""
    tenant = platform_context.get("tenant_name", "default")
    namespace = platform_context.get("k8s_namespace", "default")
    user = platform_context.get("user_id", "unknown")
    
    # Simulated - in production, query Kubernetes
    return f"Found 5 {resource_type} in {tenant}/{namespace} for user {user}"

# Test with context
context = {"tenant_name": "prod", "k8s_namespace": "web-app", "user_id": "alice"}
print(list_user_resources.execute({"resource_type": "pods"}, context))
```

### Approval-Required Tool

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "delete_deployment",
        "description": "Delete a Kubernetes deployment",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the deployment"
                },
                "namespace": {
                    "type": "string",
                    "description": "Kubernetes namespace",
                    "default": "default"
                },
                "force": {
                    "type": "boolean",
                    "description": "Force delete without grace period",
                    "default": False
                }
            },
            "required": ["name"]
        }
    },
    requires_approval=True  # Requires user approval
)
def delete_deployment(
    name: str, 
    namespace: str = "default", 
    force: bool = False,
    platform_context: dict = None
) -> str:
    """Delete a deployment."""
    user = platform_context.get("user_id", "system") if platform_context else "system"
    mode = "force deleted" if force else "deleted"
    return f"Deployment '{name}' in namespace '{namespace}' {mode} by {user}"

# Verify tool properties
print(f"Requires approval: {delete_deployment.requires_approval}")  # True
print(f"Has platform context: {delete_deployment.requires_platform_context}")  # True
```

### Programmatic Tool Creation

```python
from dcaf.tools import create_tool

# Define function
def search_logs(query: str, limit: int = 100, source: str = None) -> str:
    """Search application logs."""
    sources = f" from {source}" if source else ""
    return f"Found 42 log entries matching '{query}'{sources} (limit: {limit})"

# Create tool programmatically
search_tool = create_tool(
    func=search_logs,
    schema={
        "name": "search_logs",
        "description": "Search application logs for patterns",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (regex supported)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 100
                },
                "source": {
                    "type": "string",
                    "enum": ["app", "system", "security"],
                    "description": "Log source to search"
                }
            },
            "required": ["query"]
        }
    },
    requires_approval=False
)

# Test
print(search_tool.execute({"query": "error.*timeout", "source": "app"}))
```

---

## Agent Examples

### Complete Tool-Calling Agent

```python
#!/usr/bin/env python3
"""tool_agent.py - Complete agent with tools"""

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
        "name": "get_time",
        "description": "Get current date and time",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    requires_approval=False
)
def get_time() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool(
    schema={
        "name": "calculate",
        "description": "Perform arithmetic",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Math expression (e.g., '2 + 2')"
                }
            },
            "required": ["expression"]
        }
    },
    requires_approval=False
)
def calculate(expression: str) -> str:
    try:
        # Safe eval for simple math
        allowed = set("0123456789+-*/.() ")
        if all(c in allowed for c in expression):
            result = eval(expression)
            return f"{expression} = {result}"
        return "Error: Invalid expression"
    except Exception as e:
        return f"Error: {e}"

@tool(
    schema={
        "name": "send_email",
        "description": "Send an email (simulated)",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"}
            },
            "required": ["to", "subject", "body"]
        }
    },
    requires_approval=True  # Requires approval
)
def send_email(to: str, subject: str, body: str) -> str:
    # In production, send actual email
    return f"Email sent to {to}: '{subject}'"

# Create agent
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[get_time, calculate, send_email],
    system_prompt="""You are a helpful assistant with access to tools.
    Use tools when appropriate to help the user.
    For email sending, always confirm the details before sending.""",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations=10
)

app = create_chat_app(agent)

if __name__ == "__main__":
    print("Starting agent on http://localhost:8000")
    print("Try: curl -X POST http://localhost:8000/api/sendMessage \\")
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"messages": [{"role": "user", "content": "What time is it?"}]}\'')
    uvicorn.run(app, port=8000)
```

### FAQ Agent

```python
#!/usr/bin/env python3
"""faq_agent.py - FAQ-based agent"""

from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
import uvicorn
import re

class FAQAgent(AgentProtocol):
    def __init__(self):
        self.faqs = [
            (r"(what is|explain|define) dcaf", 
             "DCAF (DuploCloud Agent Framework) is a Python framework for building "
             "LLM-powered AI agents with tool calling capabilities."),
            
            (r"how (do i|to) install",
             "Install DCAF with: `pip install git+https://github.com/duplocloud/service-desk-agents.git`"),
            
            (r"(list|what are) (the )?(tools|features)",
             "DCAF features:\n"
             "- Tool calling with approval workflows\n"
             "- AWS Bedrock LLM integration\n"
             "- FastAPI server\n"
             "- Streaming responses\n"
             "- Platform context support"),
            
            (r"(hello|hi|hey)",
             "Hello! I'm the FAQ bot. Ask me about DCAF installation, features, or usage."),
            
            (r"(help|what can you do)",
             "I can answer questions about DCAF. Try asking:\n"
             "- What is DCAF?\n"
             "- How do I install DCAF?\n"
             "- What features does DCAF have?")
        ]
        
        self.default = ("I don't have a specific answer for that. "
                       "Try asking about DCAF installation or features.")
    
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        
        question = last_user.get("content", "").lower()
        
        for pattern, answer in self.faqs:
            if re.search(pattern, question):
                return AgentMessage(content=answer)
        
        return AgentMessage(content=self.default)

app = create_chat_app(FAQAgent())

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

### Stateful Conversation Agent

```python
#!/usr/bin/env python3
"""stateful_agent.py - Agent with conversation memory"""

from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
from dcaf.llm import BedrockLLM
from collections import defaultdict
import uvicorn
import dotenv

dotenv.load_dotenv()

class StatefulAgent(AgentProtocol):
    def __init__(self):
        self.llm = BedrockLLM()
        self.model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
        self.user_sessions = defaultdict(list)
    
    def invoke(self, messages):
        messages_list = messages.get("messages", [])
        
        # Get user ID
        user_id = self._get_user_id(messages_list)
        
        # Get current message
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        current_message = last_user.get("content", "")
        
        # Add to session history
        self.user_sessions[user_id].append({
            "role": "user",
            "content": current_message
        })
        
        # Build conversation with history
        conversation = self.user_sessions[user_id].copy()
        
        # Call LLM
        response = self.llm.invoke(
            messages=conversation,
            model_id=self.model_id,
            system_prompt=f"You are a helpful assistant. The user's ID is {user_id}.",
            max_tokens=1000
        )
        
        # Extract response
        content = response["output"]["message"]["content"]
        text = next((b["text"] for b in content if "text" in b), "")
        
        # Add response to history
        self.user_sessions[user_id].append({
            "role": "assistant",
            "content": text
        })
        
        # Limit history length
        if len(self.user_sessions[user_id]) > 20:
            self.user_sessions[user_id] = self.user_sessions[user_id][-20:]
        
        return AgentMessage(content=text)
    
    def _get_user_id(self, messages_list):
        for msg in reversed(messages_list):
            if msg.get("role") == "user":
                ctx = msg.get("platform_context", {})
                return ctx.get("user_id", "anonymous")
        return "anonymous"

app = create_chat_app(StatefulAgent())

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

---

## Server Examples

### Production Server with CORS

```python
#!/usr/bin/env python3
"""production_server.py - Production-ready server"""

from dcaf.agent_server import create_chat_app
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM
from dcaf.tools import tool
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

dotenv.load_dotenv()

# Define tools
@tool(
    schema={
        "name": "health_check",
        "description": "Check service health",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
)
def health_check() -> str:
    return "All systems operational"

# Create agent
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[health_check],
    system_prompt="You are a production assistant."
)

# Create app
app = create_chat_app(agent)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom middleware
@app.middleware("http")
async def log_requests(request, call_next):
    logging.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logging.info(f"Response: {response.status_code}")
    return response

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True
    )
```

### Server with Slack Router

```python
#!/usr/bin/env python3
"""slack_server.py - Server with Slack routing"""

from dcaf.agent_server import create_chat_app
from dcaf.agents import ToolCallingAgent
from dcaf.llm import BedrockLLM
from dcaf.channel_routing import SlackResponseRouter
from dcaf.tools import tool
import uvicorn
import dotenv

dotenv.load_dotenv()

# Create LLM
llm = BedrockLLM()

# Define tools
@tool(
    schema={
        "name": "get_status",
        "description": "Get system status",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
)
def get_status() -> str:
    return "All systems running normally"

# Create agent
agent = ToolCallingAgent(
    llm=llm,
    tools=[get_status],
    system_prompt="You are SlackBot, a helpful assistant."
)

# Create Slack router
router = SlackResponseRouter(
    llm_client=llm,
    agent_name="SlackBot",
    agent_description="""SlackBot helps with:
    - System status checks
    - General questions
    - Technical support""",
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0"
)

# Create app with router
app = create_chat_app(agent, router=router)

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

---

## Client Examples

### Python Client

```python
#!/usr/bin/env python3
"""client.py - Python client example"""

import requests
import json

BASE_URL = "http://localhost:8000"

def send_message(content: str, history: list = None) -> dict:
    """Send a message to the agent."""
    messages = history or []
    messages.append({"role": "user", "content": content})
    
    response = requests.post(
        f"{BASE_URL}/api/sendMessage",
        json={"messages": messages}
    )
    response.raise_for_status()
    return response.json()

def stream_message(content: str, history: list = None):
    """Stream a message response."""
    messages = history or []
    messages.append({"role": "user", "content": content})
    
    response = requests.post(
        f"{BASE_URL}/api/sendMessageStream",
        json={"messages": messages},
        stream=True
    )
    
    for line in response.iter_lines():
        if line:
            event = json.loads(line)
            yield event

def chat():
    """Interactive chat loop."""
    history = []
    print("Chat with the agent (type 'quit' to exit)")
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() == 'quit':
            break
        
        # Send message
        response = send_message(user_input, history)
        
        # Print response
        print(f"\nAgent: {response['content']}")
        
        # Check for tool calls
        data = response.get("data", {})
        if data.get("tool_calls"):
            print("\n[Tool calls pending approval]")
            for tc in data["tool_calls"]:
                print(f"  - {tc['name']}: {tc['input']}")
        
        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response["content"]})

if __name__ == "__main__":
    chat()
```

### Streaming Client

```python
#!/usr/bin/env python3
"""streaming_client.py - Streaming client example"""

import requests
import json
import sys

def stream_chat(message: str):
    """Stream a chat response."""
    response = requests.post(
        "http://localhost:8000/api/sendMessageStream",
        json={
            "messages": [{"role": "user", "content": message}]
        },
        stream=True
    )
    
    accumulated = ""
    
    for line in response.iter_lines():
        if not line:
            continue
        
        event = json.loads(line)
        event_type = event.get("type")
        
        if event_type == "text_delta":
            text = event.get("text", "")
            accumulated += text
            sys.stdout.write(text)
            sys.stdout.flush()
        
        elif event_type == "tool_calls":
            print("\n\n[Tools requiring approval:]")
            for tc in event.get("tool_calls", []):
                print(f"  • {tc['name']}")
                print(f"    Input: {tc['input']}")
        
        elif event_type == "executed_tool_calls":
            print("\n\n[Executed tools:]")
            for tc in event.get("executed_tool_calls", []):
                print(f"  • {tc['name']}: {tc['output'][:100]}...")
        
        elif event_type == "done":
            print(f"\n\n[Complete: {event.get('stop_reason')}]")
        
        elif event_type == "error":
            print(f"\n\n[Error: {event.get('error')}]")
    
    return accumulated

if __name__ == "__main__":
    message = sys.argv[1] if len(sys.argv) > 1 else "Tell me a short story"
    stream_chat(message)
```

---

## Advanced Examples

### Multi-Agent Router

```python
#!/usr/bin/env python3
"""multi_agent.py - Multi-agent routing"""

from dcaf.agent_server import AgentProtocol, create_chat_app
from dcaf.schemas.messages import AgentMessage
from dcaf.llm import BedrockLLM
from dcaf.tools import tool
from dcaf.agents import ToolCallingAgent
import uvicorn
import dotenv

dotenv.load_dotenv()

class RouterAgent(AgentProtocol):
    """Routes to specialized agents based on intent."""
    
    def __init__(self):
        self.llm = BedrockLLM()
        self.agents = self._create_agents()
    
    def _create_agents(self):
        # Weather agent
        @tool(
            schema={
                "name": "get_weather",
                "description": "Get weather",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    },
                    "required": ["location"]
                }
            }
        )
        def get_weather(location: str) -> str:
            return f"Weather in {location}: 72°F, sunny"
        
        weather_agent = ToolCallingAgent(
            llm=self.llm,
            tools=[get_weather],
            system_prompt="You are a weather assistant."
        )
        
        # Math agent
        @tool(
            schema={
                "name": "calculate",
                "description": "Calculate",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "expr": {"type": "string"}
                    },
                    "required": ["expr"]
                }
            }
        )
        def calculate(expr: str) -> str:
            try:
                return str(eval(expr))
            except:
                return "Error"
        
        math_agent = ToolCallingAgent(
            llm=self.llm,
            tools=[calculate],
            system_prompt="You are a math assistant."
        )
        
        return {
            "weather": weather_agent,
            "math": math_agent
        }
    
    def invoke(self, messages):
        # Classify intent
        messages_list = messages.get("messages", [])
        last_user = next(
            (m for m in reversed(messages_list) if m.get("role") == "user"),
            {}
        )
        content = last_user.get("content", "").lower()
        
        # Simple keyword routing
        if any(w in content for w in ["weather", "temperature", "forecast"]):
            return self.agents["weather"].invoke(messages)
        elif any(w in content for w in ["calculate", "math", "+", "-", "*", "/"]):
            return self.agents["math"].invoke(messages)
        else:
            return AgentMessage(
                content="I can help with weather or math. What would you like?"
            )

app = create_chat_app(RouterAgent())

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

### Agent with External API Integration

```python
#!/usr/bin/env python3
"""api_agent.py - Agent with external API integration"""

from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import requests
import uvicorn
import dotenv

dotenv.load_dotenv()

# External API tools
@tool(
    schema={
        "name": "search_github",
        "description": "Search GitHub repositories",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "language": {"type": "string", "description": "Programming language filter"}
            },
            "required": ["query"]
        }
    },
    requires_approval=False
)
def search_github(query: str, language: str = None) -> str:
    """Search GitHub via API."""
    search_query = query
    if language:
        search_query += f" language:{language}"
    
    response = requests.get(
        "https://api.github.com/search/repositories",
        params={"q": search_query, "per_page": 5},
        headers={"Accept": "application/vnd.github.v3+json"}
    )
    
    if response.status_code != 200:
        return f"Error: {response.status_code}"
    
    data = response.json()
    results = []
    for repo in data.get("items", [])[:5]:
        results.append(f"• {repo['full_name']} ({repo['stargazers_count']}⭐)")
    
    return f"Found {data['total_count']} repos:\n" + "\n".join(results)

@tool(
    schema={
        "name": "get_ip_info",
        "description": "Get information about an IP address",
        "input_schema": {
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "IP address to lookup"}
            },
            "required": ["ip"]
        }
    },
    requires_approval=False
)
def get_ip_info(ip: str) -> str:
    """Get IP information."""
    response = requests.get(f"https://ipapi.co/{ip}/json/")
    
    if response.status_code != 200:
        return f"Error: {response.status_code}"
    
    data = response.json()
    return (
        f"IP: {data.get('ip')}\n"
        f"City: {data.get('city')}\n"
        f"Region: {data.get('region')}\n"
        f"Country: {data.get('country_name')}\n"
        f"ISP: {data.get('org')}"
    )

# Create agent
llm = BedrockLLM()
agent = ToolCallingAgent(
    llm=llm,
    tools=[search_github, get_ip_info],
    system_prompt="You are a helpful assistant with access to external APIs."
)

app = create_chat_app(agent)

if __name__ == "__main__":
    uvicorn.run(app, port=8000)
```

### Complete Production Application

```python
#!/usr/bin/env python3
"""production_app.py - Complete production application"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import dotenv

from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app

# Load environment
dotenv.load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Define tools
@tool(
    schema={
        "name": "get_deployment_status",
        "description": "Get status of a deployment",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Deployment name"},
                "namespace": {"type": "string", "default": "default"}
            },
            "required": ["name"]
        }
    }
)
def get_deployment_status(name: str, namespace: str = "default", platform_context: dict = None) -> str:
    tenant = platform_context.get("tenant_name", "unknown") if platform_context else "unknown"
    return f"Deployment {name} in {namespace} ({tenant}): Running (3/3 replicas)"

@tool(
    schema={
        "name": "scale_deployment",
        "description": "Scale a deployment",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "replicas": {"type": "integer", "minimum": 0, "maximum": 10}
            },
            "required": ["name", "replicas"]
        }
    },
    requires_approval=True
)
def scale_deployment(name: str, replicas: int, platform_context: dict = None) -> str:
    user = platform_context.get("user_id", "system") if platform_context else "system"
    return f"Deployment {name} scaled to {replicas} replicas by {user}"

# Create agent
llm = BedrockLLM(region_name=os.getenv("AWS_REGION", "us-east-1"))
agent = ToolCallingAgent(
    llm=llm,
    tools=[get_deployment_status, scale_deployment],
    system_prompt="""You are a Kubernetes assistant for DuploCloud.
    Help users manage their deployments.
    Always verify the deployment exists before scaling.""",
    model_id=os.getenv(
        "BEDROCK_MODEL_ID",
        "us.anthropic.claude-3-5-sonnet-20240620-v1:0"
    )
)

# Create app
app = create_chat_app(agent)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom endpoints
@app.get("/version")
def version():
    return {
        "version": os.getenv("APP_VERSION", "1.0.0"),
        "model": os.getenv("BEDROCK_MODEL_ID")
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting production server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
```

---

## See Also

- [Getting Started](../getting-started.md)
- [API Reference](../api-reference/llm.md)
- [Building Tools Guide](../guides/building-tools.md)
- [Creating Custom Agents Guide](../guides/creating-custom-agents.md)

