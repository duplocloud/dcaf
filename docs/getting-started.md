# Getting Started with DCAF

This guide walks you through installation, setup, and building your first agent.

---

## Prerequisites

### Required

- **Python 3.11+** - DCAF supports Python 3.11, 3.12, and 3.13
- **AWS Account** - With access to AWS Bedrock
- **AWS Credentials** - With permissions to invoke Bedrock models

### Optional

- **DuploCloud Account** - For credential management CLI
- **Docker** - For containerized deployments

---

## Installation

### From GitHub

```bash
pip install git+https://github.com/duplocloud/service-desk-agents.git
```

### For Development

```bash
git clone https://github.com/duplocloud/service-desk-agents.git
cd service-desk-agents
pip install -r requirements.txt
```

### Verify Installation

```python
from dcaf.core import Agent, serve
print("DCAF installed successfully!")
```

---

## Environment Setup

### Option 1: AWS Profiles (Recommended)

Use AWS profiles from `~/.aws/credentials`:

```python
from dcaf.core import Agent

agent = Agent(
    aws_profile="my-profile",    # Use this AWS profile
    aws_region="us-east-1",      # Optional region override
)
```

Configure profiles in `~/.aws/credentials`:

```ini
[default]
aws_access_key_id = AKIA...
aws_secret_access_key = ...

[production]
aws_access_key_id = AKIA...
aws_secret_access_key = ...
region = us-west-2
```

### Option 2: Environment Variables

Create a `.env` file:

```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_SESSION_TOKEN=your_session_token  # Optional
AWS_REGION=us-east-1

# Optional: Bedrock Configuration
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-sonnet-20240620-v1:0

# For other providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### Option 3: DuploCloud (Optional)

```bash
# Update AWS credentials via DuploCloud
dcaf env-update-aws-creds --tenant=your-tenant --host=https://your-duplo-host.duplocloud.net
```

---

## Choosing a Provider

DCAF supports multiple LLM providers:

| Provider | Description | Model Examples |
|----------|-------------|----------------|
| `bedrock` | AWS Bedrock (default) | `anthropic.claude-3-sonnet-20240229-v1:0` |
| `anthropic` | Direct Anthropic API | `claude-3-sonnet-20240229` |
| `openai` | OpenAI API | `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo` |
| `azure` | Azure OpenAI | Deployment names |
| `google` | Google AI | `gemini-pro` |
| `ollama` | Local Ollama | `llama2`, `mistral`, `codellama` |

### Provider Examples

```python
from dcaf.core import Agent

# AWS Bedrock (default)
agent = Agent(
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile",
)

# Direct Anthropic
agent = Agent(
    provider="anthropic",
    model="claude-3-sonnet-20240229",
    api_key="sk-ant-...",  # or set ANTHROPIC_API_KEY
)

# OpenAI
agent = Agent(
    provider="openai",
    model="gpt-4",
    api_key="sk-...",  # or set OPENAI_API_KEY
)

# Local Ollama (free, runs locally)
agent = Agent(
    provider="ollama",
    model="llama2",
)
```

---

## Quick Start: Build Your First Agent

### Step 1: Create a Tool

```python
from dcaf.tools import tool

@tool(description="Perform arithmetic calculations")
def calculate(operation: str, a: float, b: float) -> str:
    """Simple calculator."""
    ops = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b != 0 else "undefined",
    }
    result = ops.get(operation, f"Unknown: {operation}")
    symbols = {"add": "+", "subtract": "-", "multiply": "×", "divide": "÷"}
    return f"{a} {symbols.get(operation, '?')} {b} = {result}"
```

### Step 2: Create an Agent

```python
from dcaf.core import Agent

agent = Agent(
    tools=[calculate],
    system="You are a helpful math assistant. Use the calculate tool for arithmetic.",
)
```

### Step 3: Serve It

```python
from dcaf.core import serve

serve(agent, port=8000)
```

### Complete Example

```python
#!/usr/bin/env python3
"""calculator_agent.py - A complete DCAF example"""

from dcaf.core import Agent, serve
from dcaf.tools import tool
import dotenv

# Load environment variables
dotenv.load_dotenv(override=True)

@tool(description="Perform arithmetic calculations")
def calculate(operation: str, a: float, b: float) -> str:
    """Calculator supporting add, subtract, multiply, divide."""
    ops = {
        "add": a + b,
        "subtract": a - b,
        "multiply": a * b,
        "divide": a / b if b != 0 else "undefined (division by zero)",
    }
    result = ops.get(operation, f"Unknown operation: {operation}")
    symbols = {"add": "+", "subtract": "-", "multiply": "×", "divide": "÷"}
    return f"{a} {symbols.get(operation, '?')} {b} = {result}"

# Create the agent
agent = Agent(
    tools=[calculate],
    system="You are a helpful math assistant. Use the calculate tool for arithmetic.",
)

if __name__ == "__main__":
    print("Starting Calculator Agent at http://localhost:8000")
    print()
    print("Try:")
    print('  curl -X POST http://localhost:8000/api/chat \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"messages": [{"role": "user", "content": "What is 15 × 7?"}]}\'')
    print()
    serve(agent, port=8000)
```

### Step 4: Test Your Agent

Run the server:

```bash
python calculator_agent.py
```

Test with curl:

```bash
# Simple calculation
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is 42 divided by 6?"}]}'

# Multiple calculations
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Calculate 15 + 27 and then multiply by 3"}]}'
```

Test with Python:

```python
import requests

response = requests.post(
    "http://localhost:8000/api/chat",
    json={"messages": [{"role": "user", "content": "What is 100 - 37?"}]}
)
print(response.json())
```

---

## Adding Tool Approval

For dangerous operations, require human approval:

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool

@tool(description="List pods")
def list_pods(namespace: str = "default") -> str:
    return kubectl(f"get pods -n {namespace}")

@tool(requires_approval=True, description="Delete a pod")
def delete_pod(name: str, namespace: str = "default") -> str:
    return kubectl(f"delete pod {name} -n {namespace}")

agent = Agent(tools=[list_pods, delete_pod])
serve(agent)
```

When `delete_pod` is called, the agent will pause and request approval.

---

## Streaming Responses

For real-time output:

```bash
curl -X POST http://localhost:8000/api/chat-stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Explain Kubernetes"}]}'
```

Response (NDJSON):

```json
{"type": "text_delta", "text": "Kubernetes"}
{"type": "text_delta", "text": " is"}
{"type": "text_delta", "text": " a container orchestration platform..."}
{"type": "done"}
```

---

## Troubleshooting

### AWS Credentials Expired

```
ExpiredTokenException: The security token included in the request is expired
```

**Solution:**

```bash
# Using DuploCloud
dcaf env-update-aws-creds --tenant=your-tenant --host=your-duplo-host

# Or manually update .env with fresh credentials
```

### Model Not Found

```
ResourceNotFoundException: Could not find model with id...
```

**Solution:**

- Verify the model ID is correct
- Check Bedrock is enabled in your AWS account
- Ensure your region has access to the model

### Expected toolResult Blocks

```
ValidationException: Expected toolResult blocks...
```

**Solution:**

This occurs when Bedrock receives tool-related messages in an invalid state. DCAF automatically handles this by:

1. Filtering tool messages from conversation history
2. Limiting parallel tool calls to 1
3. Adding a system prompt instruction for single tool calls

If you still see this error, check:

```python
# Ensure you're using the latest adapter
agent = Agent(
    tools=[...],
    # These are handled automatically, but you can configure:
    # AGNO_TOOL_CALL_LIMIT=1
    # AGNO_DISABLE_HISTORY=false
)
```

### Message Alternation Error

```
ValidationException: Messages must alternate between user and assistant
```

**Solution:**

DCAF automatically enforces message alternation. If you see this:

1. Check for manual message manipulation
2. Ensure you're not passing raw Bedrock-style messages

### Connection Timeout

```
ReadTimeoutError: Read timed out
```

**Solution:**

```bash
export BOTO3_READ_TIMEOUT=60
export BOTO3_CONNECT_TIMEOUT=30
```

### Import Errors

```
ModuleNotFoundError: No module named 'dcaf'
```

**Solution:**

```bash
pip install git+https://github.com/duplocloud/service-desk-agents.git
```

### Provider Package Missing

```
ImportError: OpenAI provider requires the 'openai' package...
```

**Solution:**

Install the required package for your provider:

```bash
# For OpenAI/Azure
pip install openai

# For Google AI
pip install google-generativeai

# For Ollama
pip install ollama
```

---

## Next Steps

- **[Core Overview](./core/index.md)** - Full Agent API documentation
- **[Building Tools](./guides/building-tools.md)** - Advanced tool creation
- **[Custom Agents](./guides/custom-agents.md)** - Complex multi-step agents
- **[Server](./core/server.md)** - Deployment and configuration
- **[Examples](./examples/examples.md)** - More code examples

---

## Getting Help

- Check [GitHub Issues](https://github.com/duplocloud/service-desk-agents/issues)
- Enable debug logging: `export LOG_LEVEL=DEBUG`
- Contact DuploCloud: support@duplocloud.com
