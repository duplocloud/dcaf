# DCAF - DuploCloud Agent Framework

**DCAF** is a Python framework for building LLM-powered AI agents with tool calling and human-in-the-loop approval. Designed for the DuploCloud HelpDesk, it makes it easy to create agents that can execute infrastructure operations safely.

---

## Features

| Feature | Description |
|---------|-------------|
| 🛠️ **Tool Calling** | Simple `@tool` decorator to create capabilities |
| ✅ **Human-in-the-Loop** | Built-in approval flow for dangerous operations |
| 🔌 **Interceptors** | Hook into request/response for validation, context, security |
| 🌐 **REST API** | One-line server with `serve(agent)` |
| 📡 **Streaming** | Real-time token-by-token responses |
| 🔀 **Custom Logic** | Build complex agents with any structure |

---

## Quick Start

### 1. Install

#### Base Installation
```bash
pip install git+https://github.com/duplocloud/dcaf.git
```

#### With Provider Support

```bash
# Google Gemini
pip install "git+https://github.com/duplocloud/dcaf.git#egg=dcaf[google]"

# AWS Bedrock (included by default)
pip install "git+https://github.com/duplocloud/dcaf.git#egg=dcaf[bedrock]"

# Anthropic Direct
pip install "git+https://github.com/duplocloud/dcaf.git#egg=dcaf[anthropic]"

# OpenAI
pip install "git+https://github.com/duplocloud/dcaf.git#egg=dcaf[openai]"

# All providers
pip install "git+https://github.com/duplocloud/dcaf.git#egg=dcaf[providers]"

# Everything (providers + docs + dev)
pip install "git+https://github.com/duplocloud/dcaf.git#egg=dcaf[all]"
```

### 2. Create an Agent

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

# Define tools with the @tool decorator
@tool(description="List Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    """List pods in a namespace."""
    return f"Pods in {namespace}: nginx, redis, api"

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    """Delete a pod. Requires user approval."""
    return f"Deleted pod {name} from {namespace}"

# Create the agent
agent = Agent(
    tools=[list_pods, delete_pod],
    system_prompt="You are a helpful Kubernetes assistant.",
)

# Start the server
serve(agent)  # Running at http://0.0.0.0:8000
```

### 3. Test It

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What pods are running?"}]}'
```

---

## How It Works

```
User Request → Agent → LLM (Claude) → Tool Calls → Approval → Execution → Response
```

1. **User sends a message** via the REST API
2. **Agent processes** the message and calls the LLM
3. **LLM decides** what tools to use (if any)
4. **Tools requiring approval** are paused for user confirmation
5. **Approved tools execute** and results are returned

---

## Core Concepts

### Tools

Tools are functions your agent can call. Use the `@tool` decorator:

```python
from dcaf.tools import tool

@tool(description="Get current weather")
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Weather in {city}: 72°F, sunny"

@tool(requires_approval=True, description="Send an email")
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email. Requires approval because it's an external action."""
    # Email sending logic here
    return f"Email sent to {to}"
```

### Approval Flow

Tools with `requires_approval=True` pause for user confirmation:

```python
response = agent.run(messages=[
    {"role": "user", "content": "Delete the nginx pod"}
])

if response.needs_approval:
    print("Pending approvals:")
    for tool in response.pending_tools:
        print(f"  - {tool.name}: {tool.input}")
    
    # Approve and continue
    response = response.approve_all()

print(response.text)
```

### Interceptors

Interceptors let you hook into the request/response pipeline:

```python
from dcaf.core import Agent, LLMRequest, LLMResponse, InterceptorError

# Add context before sending to LLM
def add_tenant_context(request: LLMRequest) -> LLMRequest:
    tenant = request.context.get("tenant_name", "unknown")
    request.add_system_context(f"User's tenant: {tenant}")
    return request

# Block suspicious input
def validate_input(request: LLMRequest) -> LLMRequest:
    if "ignore instructions" in request.get_latest_user_message().lower():
        raise InterceptorError("I can't process this request.")
    return request

# Clean up responses
def redact_secrets(response: LLMResponse) -> LLMResponse:
    response.text = response.text.replace("sk-secret", "[REDACTED]")
    return response

agent = Agent(
    tools=[...],
    request_interceptors=[validate_input, add_tenant_context],
    response_interceptors=redact_secrets,
)
```

### Streaming

For real-time responses:

```python
for event in agent.run_stream(messages=[...]):
    if isinstance(event, TextDeltaEvent):
        print(event.text, end="", flush=True)
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/chat` | POST | Synchronous chat |
| `/api/chat-stream` | POST | Streaming (NDJSON) |

---

## Environment Setup

### Option 1: Environment-Driven (Recommended)

Configure provider via environment variables:

```bash
# Choose your provider
export DCAF_PROVIDER=google
export DCAF_MODEL=gemini-3-flash
export GEMINI_API_KEY=your-api-key
```

Then load in code:

```python
from dcaf.core import Agent, load_agent_config

config = load_agent_config()  # Loads from environment
agent = Agent(tools=[my_tool], **config)
```

**Switch providers without code changes:**

```bash
# Switch to Bedrock
export DCAF_PROVIDER=bedrock
export AWS_PROFILE=my-profile
# Code stays the same!
```

### Option 2: Hardcoded (Simple)

Pass configuration directly:

```python
agent = Agent(
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile"
)
```

---

## Supported LLM Providers

DCAF supports multiple LLM providers through the [Agno SDK](https://docs.agno.com/):

| Provider | Models | Configuration |
|----------|--------|---------------|
| **AWS Bedrock** | Claude 3.x | `provider="bedrock"`, AWS credentials |
| **Anthropic** | Claude 3.x | `provider="anthropic"`, API key |
| **Google** | Gemini 3, 2.x, 1.5 | `provider="google"`, API key or Vertex AI |
| **OpenAI** | GPT-4, GPT-3.5 | `provider="openai"`, API key |
| **Azure OpenAI** | GPT models | `provider="azure"`, API key |
| **Ollama** | Local models | `provider="ollama"` |

```python
# AWS Bedrock (default)
agent = Agent(provider="bedrock", aws_profile="my-profile")

# Google Vertex AI (auto-detects project/location on GCP)
agent = Agent(provider="google", model="gemini-2.5-pro")

# Anthropic Direct
agent = Agent(provider="anthropic", model="claude-3-sonnet-20240229", api_key=os.getenv("ANTHROPIC_API_KEY"))
```

## Requirements

- **Python 3.12+**
- **Provider credentials**: AWS (Bedrock), Anthropic, Google, OpenAI, or Azure
- **Dependencies**: `fastapi`, `pydantic`, `uvicorn`, `boto3`, `agno`

---

## Documentation

Full documentation is available at **[https://duplocloud.github.io/dcaf/](https://duplocloud.github.io/dcaf/)**

### View Locally

```bash
# Install docs dependencies
pip install -e ".[docs]"

# Serve documentation
mkdocs serve
# Open http://localhost:8000
```

### Key Guides

- [Getting Started](docs/getting-started.md) - Installation and first steps
- [Core Overview](docs/core/index.md) - Agent class and API
- [Working with Bedrock](docs/guides/working-with-bedrock.md) - AWS Bedrock setup
- [Working with Gemini](docs/guides/working-with-gemini.md) - Google Gemini setup
- [Interceptors Guide](docs/guides/interceptors.md) - Request/response hooks
- [Custom Agents](docs/guides/custom-agents.md) - Building complex agents
- [Architecture](docs/architecture.md) - How DCAF works internally

---

## Project Structure

```
dcaf/
├── core/                  # New Core API (recommended)
│   ├── agent.py          # Agent class (main entry point)
│   ├── interceptors.py   # LLMRequest, LLMResponse, InterceptorError
│   ├── server.py         # serve() function
│   └── ...
├── agents/               # Legacy agents (v1)
├── llm/                  # LLM wrappers (Bedrock)
├── tools.py              # @tool decorator
├── schemas/              # Message schemas
└── agent_server.py       # FastAPI server
```

---

## Legacy API (v1)

> ⚠️ **Note**: The examples below use the legacy v1 API. New projects should use the [Core API](#quick-start) shown above. The legacy API is still supported for backwards compatibility.

### BedrockLLM (Legacy)

Direct access to AWS Bedrock:

```python
from dcaf.llm import BedrockLLM

llm = BedrockLLM(region_name="us-east-1")

response = llm.invoke(
    messages=[{"role": "user", "content": "Hello"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=1000,
    tools=[...],  # Optional tool schemas
)
```

### ToolCallingAgent (Legacy)

The original agent class with manual LLM wiring:

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool
from dcaf.agent_server import create_chat_app
import uvicorn

# Create tools with full schema
@tool(
    schema={
        "name": "get_weather",
        "description": "Get weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    requires_approval=False
)
def get_weather(city: str) -> str:
    return f"Weather in {city}: 72°F, sunny"

# Create LLM and agent separately
llm = BedrockLLM(region_name="us-east-1")
agent = ToolCallingAgent(
    llm=llm,
    tools=[get_weather],
    system_prompt="You are a helpful assistant.",
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_iterations=10,
    enable_terminal_cmds=True,
)

# Create and run server
app = create_chat_app(agent)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Legacy Tool Schema Format

The legacy API requires explicit JSON schemas:

```python
@tool(
    schema={
        "name": "delete_file",
        "description": "Delete a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"}
            },
            "required": ["path"]
        }
    },
    requires_approval=True
)
def delete_file(path: str) -> str:
    return f"Deleted {path}"
```

Compare with the Core API (simpler):

```python
@tool(requires_approval=True, description="Delete a file")
def delete_file(path: str) -> str:
    """Delete a file at the given path."""
    return f"Deleted {path}"
```

### Legacy Endpoints

| Legacy Endpoint | New Endpoint | Description |
|-----------------|--------------|-------------|
| `/api/sendMessage` | `/api/chat` | Synchronous chat |
| `/api/sendMessageStream` | `/api/chat-stream` | Streaming |

The legacy endpoints still work for backwards compatibility.

### Migration Guide

For migrating from v1 to Core API, see the [Migration Guide](docs/guides/migration.md).

---

## Development

```bash
# Clone the repo
git clone https://github.com/duplocloud/dcaf.git
cd dcaf

# Install with dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check .

# Run type checker
mypy dcaf/

# Run tests
pytest
```

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

## Support

- **GitHub Issues**: [dcaf](https://github.com/duplocloud/dcaf/issues)
- **DuploCloud Support**: support@duplocloud.com
