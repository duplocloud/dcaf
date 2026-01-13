# Working with Google Gemini

DCAF supports Google's Gemini models through the Agno adapter, providing access to the latest Gemini 3 and Gemini 2.x models for agent orchestration.

## Overview

Google Gemini offers:
- **Gemini 3**: Latest generation with advanced reasoning
- **Gemini 2.x**: High-performance models with thinking budgets
- **Gemini 1.5**: Large context windows and efficient inference
- **Vertex AI**: Enterprise integration through Google Cloud Platform

## Installation

Install the required Google AI dependencies:

```bash
# For Google AI Studio (direct API)
pip install google-generativeai

# Or install DCAF with Gemini support
pip install dcaf[gemini]
```

## Configuration

### Option 1: Environment Variable (Recommended)

Set your Gemini API key:

```bash
export GEMINI_API_KEY="your-api-key-here"
```

Get your API key from [Google AI Studio](https://aistudio.google.com).

### Option 2: Pass Directly

Pass the API key when creating your agent:

```python
from dcaf.core import Agent

agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key="your-api-key-here"
)
```

## Quick Start

### Basic Gemini Agent

```python
from dcaf.core import Agent
import os

agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    system_prompt="You are a helpful assistant."
)

response = agent.run([
    {"role": "user", "content": "What's the capital of France?"}
])

print(response.text)
```

## Available Gemini Models

### Gemini 3 (Latest)

**gemini-3-pro-preview** - Most capable model with advanced reasoning
```python
agent = Agent(
    provider="google",
    model="gemini-3-pro-preview",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

**gemini-3-flash** - Fast inference with strong reasoning
```python
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

### Gemini 2.x

**gemini-2.5-flash** - Fast model with thinking support
```python
agent = Agent(
    provider="google",
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

**gemini-2.5-pro** - More capable, supports thinking budget
```python
agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

**gemini-2.0-flash** - Previous generation flash
```python
agent = Agent(
    provider="google",
    model="gemini-2.0-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

### Gemini 1.5

**gemini-1.5-flash** - Lightweight, fast responses
```python
agent = Agent(
    provider="google",
    model="gemini-1.5-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

**gemini-1.5-pro** - Large context window (2M tokens)
```python
agent = Agent(
    provider="google",
    model="gemini-1.5-pro",
    api_key=os.getenv("GEMINI_API_KEY")
)
```

## Model Configuration

### Temperature and Max Tokens

Control generation behavior:

```python
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    model_config={
        "temperature": 0.7,      # 0.0 to 1.0 (default: 0.1)
        "max_tokens": 8192,      # Maximum output tokens
    }
)
```

### Advanced Model Configuration

Pass additional Gemini-specific parameters:

```python
agent = Agent(
    provider="google",
    model="gemini-3-pro-preview",
    api_key=os.getenv("GEMINI_API_KEY"),
    model_config={
        "thinking_level": "high",     # "low" or "high" (Gemini 3 only)
        "top_p": 0.9,
        "top_k": 40,
    }
)
```

**Note:** Gemini 3 models use `thinking_level`, while Gemini 2.5 models use `thinking_budget`. See Agno's documentation for model-specific parameters.

## Using Tools with Gemini

Gemini excels at tool use and function calling:

```python
from dcaf.core import Agent
from dcaf.tools import tool
import os

@tool(description="Search for current information")
def search(query: str) -> str:
    """Search the web for information."""
    # Your search implementation
    return f"Results for: {query}"

@tool(description="Get weather information")
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f"Weather in {city}: Sunny, 72°F"

agent = Agent(
    provider="google",
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    tools=[search, get_weather],
    system_prompt="You are a helpful assistant with access to search and weather tools."
)

response = agent.run([
    {"role": "user", "content": "What's the weather in Paris and any recent news?"}
])

print(response.text)
```

## Streaming Responses

Use streaming for real-time token generation:

```python
from dcaf.core import Agent
import os

agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)

for event in agent.stream([
    {"role": "user", "content": "Write a short story about AI."}
]):
    if event.type == "text_delta":
        print(event.data.text, end="", flush=True)
    elif event.type == "complete":
        print("\n\nDone!")
```

## REST Server with Gemini

Expose a Gemini agent as a REST API:

```python
from dcaf.core import Agent, serve
from dcaf.tools import tool
import os

@tool(description="Analyze code for issues")
def analyze_code(code: str, language: str) -> str:
    """Analyze code and return suggestions."""
    return f"Analyzing {language} code..."

agent = Agent(
    name="code-reviewer",
    description="AI code review assistant",
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    tools=[analyze_code]
)

# Start server with A2A support
serve(agent, port=8000, a2a=True)
```

Access via:
- **HTTP**: `POST http://localhost:8000/api/chat`
- **A2A**: `GET http://localhost:8000/.well-known/agent.json`

## Multi-Agent Systems with Gemini

Use Gemini in multi-agent architectures:

```python
from dcaf.core import Agent
from dcaf.core.a2a import RemoteAgent
import os

# Specialist agent using Gemini
research_agent = Agent(
    name="researcher",
    provider="google",
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    tools=[web_search],
    system_prompt="You are a research specialist. Gather information from the web."
)

# Orchestrator using Claude on Bedrock
orchestrator = Agent(
    name="orchestrator",
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile",
    tools=[research_agent.as_tool()],  # Gemini agent as a tool
    system_prompt="Route research tasks to the specialist."
)

response = orchestrator.run([
    {"role": "user", "content": "Research the latest AI developments"}
])
```

## Using Vertex AI (Google Cloud)

For enterprise deployments on Google Cloud Platform, use Vertex AI with service account authentication:

```python
from dcaf.core import Agent

agent = Agent(
    provider="google",
    model="gemini-2.5-flash",
    vertexai=True,
    google_project_id="your-gcp-project-id",
    google_location="us-central1",
)

response = agent.run([
    {"role": "user", "content": "Hello from Vertex AI!"}
])
```

### GKE Workload Identity

For Kubernetes deployments with Workload Identity, the agent automatically uses the pod's service account:

```python
# In GKE with Workload Identity - no API key needed!
agent = Agent(
    provider="google",
    model="gemini-2.5-flash",
    vertexai=True,
    google_project_id="your-gcp-project-id",
    google_location="us-central1",
)
```

### Environment Variables

You can also configure Vertex AI via environment variables:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=your-gcp-project-id
export GOOGLE_CLOUD_LOCATION=us-central1
```

Then simply:

```python
from dcaf.core import Agent
from dcaf.core.config import load_agent_config

# Automatically picks up Vertex AI config from environment
config = load_agent_config(provider="google", model="gemini-2.5-flash")
agent = Agent(**config)
```

**Requirements:**
1. GCP project with Vertex AI API enabled
2. Application Default Credentials configured:
   - **Local dev**: `gcloud auth application-default login`
   - **GKE**: Workload Identity with appropriate IAM bindings
   - **GCE/Cloud Run**: Attached service account
3. IAM role: `roles/aiplatform.user` on the service account

## Model Selection Guide

| Model | Best For | Context | Speed | Cost |
|-------|----------|---------|-------|------|
| **gemini-3-pro-preview** | Complex reasoning, multi-step tasks | Large | Slow | High |
| **gemini-3-flash** | General-purpose, balanced performance | Large | Fast | Low |
| **gemini-2.5-pro** | Advanced capabilities, thinking | Large | Medium | Medium |
| **gemini-2.5-flash** | Fast inference, good reasoning | Large | Very Fast | Low |
| **gemini-1.5-pro** | Huge context (2M tokens) | Massive | Medium | Medium |
| **gemini-1.5-flash** | Quick tasks, simple queries | Large | Very Fast | Very Low |

## Error Handling

Handle Gemini-specific errors:

```python
from dcaf.core import Agent
import os

agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)

try:
    response = agent.run([
        {"role": "user", "content": "Hello!"}
    ])
    print(response.text)
except ImportError as e:
    print("Google AI package not installed:")
    print("  pip install google-generativeai")
except Exception as e:
    print(f"Error: {e}")
    print("Check your GEMINI_API_KEY is set correctly")
```

## Best Practices

### 1. Choose the Right Model

```python
# For production - use flash models for speed and cost
production_agent = Agent(
    provider="google",
    model="gemini-3-flash",  # Fast, cost-effective
    api_key=os.getenv("GEMINI_API_KEY")
)

# For complex reasoning - use pro models
research_agent = Agent(
    provider="google",
    model="gemini-3-pro-preview",  # Advanced reasoning
    api_key=os.getenv("GEMINI_API_KEY")
)
```

### 2. Use Environment Variables

```python
# Good: Environment variable
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY")  # ✓
)

# Avoid: Hardcoded API key
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key="AIzaSy..."  # ✗ Don't commit API keys!
)
```

### 3. Monitor Token Usage

Gemini models have different context windows and pricing:

```python
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    model_config={
        "max_tokens": 2048,  # Limit output to control costs
    }
)
```

### 4. Test with Flash, Deploy with Pro

```python
# Development/testing
if os.getenv("ENV") == "development":
    model = "gemini-3-flash"
else:
    model = "gemini-3-pro-preview"

agent = Agent(
    provider="google",
    model=model,
    api_key=os.getenv("GEMINI_API_KEY")
)
```

## Comparison: Gemini vs Claude vs GPT

| Feature | Gemini | Claude (Bedrock) | GPT-4 |
|---------|--------|------------------|-------|
| **Tool Use** | Excellent | Excellent | Good |
| **Reasoning** | Strong (G3) | Excellent | Strong |
| **Speed** | Very Fast (Flash) | Fast | Medium |
| **Context** | 2M (1.5 Pro) | 200K | 128K |
| **Cost** | Low (Flash) | Medium | High |
| **Deployment** | Direct API or Vertex | AWS Bedrock | OpenAI or Azure |

## Troubleshooting

### API Key Not Found

```bash
# Check if environment variable is set
echo $GEMINI_API_KEY

# Set it if missing
export GEMINI_API_KEY="your-key-here"

# Or add to your ~/.zshrc or ~/.bashrc
echo 'export GEMINI_API_KEY="your-key-here"' >> ~/.zshrc
```

### Import Error

```bash
# Install the Google AI package
pip install google-generativeai

# Or upgrade if already installed
pip install --upgrade google-generativeai
```

### Rate Limiting

Gemini API has rate limits. Handle gracefully:

```python
import time
from dcaf.core import Agent

agent = Agent(provider="google", model="gemini-3-flash")

for i in range(10):
    try:
        response = agent.run([{"role": "user", "content": f"Request {i}"}])
        print(response.text)
    except Exception as e:
        if "429" in str(e) or "rate limit" in str(e).lower():
            print("Rate limited, waiting...")
            time.sleep(60)
        else:
            raise
```

## Examples

Complete examples available in the repository:

- `examples/gemini_basic.py` - Basic Gemini usage
- `examples/gemini_tools.py` - Tool use with Gemini
- `examples/gemini_multi_agent.py` - Multi-agent with Gemini

## Resources

- [Google AI Studio](https://aistudio.google.com) - Get API keys
- [Gemini API Documentation](https://ai.google.dev/docs)
- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Agno Gemini Guide](https://docs.agno.com/models/google)
- [DCAF Documentation](../index.md)

## Support

For issues with Gemini in DCAF:

1. Check this guide
2. Review [Agno's Gemini docs](https://docs.agno.com/models/google)
3. Verify your API key is valid
4. Check Google AI Studio quotas
5. Open an issue on GitHub with logs

---

**Next Steps:**
- [Building Tools](building-tools.md)
- [Multi-Agent Systems](../core/a2a.md)
- [Working with Bedrock](working-with-bedrock.md)
