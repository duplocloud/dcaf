# Working with Google Gemini

DCAF supports Google's Gemini models through Vertex AI, providing zero-configuration deployment on Google Cloud Platform.

## Overview

Google Gemini offers:
- **Gemini 3**: Latest generation with advanced reasoning
- **Gemini 2.x**: High-performance models with thinking budgets
- **Gemini 1.5**: Large context windows and efficient inference
- **Vertex AI**: Enterprise integration through Google Cloud Platform

## Installation

Install the required Google AI dependencies:

```bash
pip install google-generativeai google-auth

# Or install DCAF with Gemini support
pip install dcaf[gemini]
```

## Configuration

### Zero Configuration on GCP (Recommended)

When running on GCP (GKE, GCE, Cloud Run), DCAF automatically detects your project and location:

```python
from dcaf.core import Agent

# That's it! Project/location auto-detected on GCP
agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
    system_prompt="You are a helpful assistant."
)
```

### Environment Variables (Optional)

Override auto-detected values if needed:

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export DCAF_GOOGLE_MODEL_LOCATION="us-central1"  # Optional, defaults to us-central1
```

## Quick Start

### Basic Gemini Agent

```python
from dcaf.core import Agent

agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
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
agent = Agent(provider="google", model="gemini-3-pro-preview")
```

**gemini-3-flash** - Fast inference with strong reasoning
```python
agent = Agent(provider="google", model="gemini-3-flash")
```

### Gemini 2.x

**gemini-2.5-flash** - Fast model with thinking support
```python
agent = Agent(provider="google", model="gemini-2.5-flash")
```

**gemini-2.5-pro** - More capable, supports thinking budget
```python
agent = Agent(provider="google", model="gemini-2.5-pro")
```

**gemini-2.0-flash** - Previous generation flash
```python
agent = Agent(provider="google", model="gemini-2.0-flash")
```

### Gemini 1.5

**gemini-1.5-flash** - Lightweight, fast responses
```python
agent = Agent(provider="google", model="gemini-1.5-flash")
```

**gemini-1.5-pro** - Large context window (2M tokens)
```python
agent = Agent(provider="google", model="gemini-1.5-pro")
```

## Model Configuration

### Temperature and Max Tokens

Control generation behavior:

```python
agent = Agent(
    provider="google",
    model="gemini-3-flash",
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

agent = Agent(
    provider="google",
    model="gemini-3-flash",
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

## Vertex AI (Default)

The Google provider always uses Vertex AI. Project and location are auto-detected on GCP:

```python
from dcaf.core import Agent

# On GCP - this is all you need!
agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
)
```

### How Auto-Detection Works

DCAF automatically detects your GCP environment:

1. **google.auth.default()**: Gets project ID from ADC (works with Workload Identity)
2. **Metadata service**: Falls back to `http://metadata.google.internal/` for project/zone
3. **Default location**: Uses `us-central1` if location can't be detected

### Explicit Configuration

Override auto-detected values if needed:

```python
agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
    google_project_id="my-project",      # Explicit project
    google_location="europe-west1",       # Explicit region
)
```

Or via environment variables:

```bash
export GOOGLE_CLOUD_PROJECT="my-project"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

### Requirements

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

agent = Agent(
    provider="google",
    model="gemini-3-flash",
)

try:
    response = agent.run([
        {"role": "user", "content": "Hello!"}
    ])
    print(response.text)
except ImportError as e:
    print("Google AI package not installed:")
    print("  pip install google-generativeai google-auth")
except ValueError as e:
    print(f"Configuration error: {e}")
    print("Ensure GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION are set")
except Exception as e:
    print(f"Error: {e}")
```

## Best Practices

### 1. Choose the Right Model

```python
# For production - use flash models for speed and cost
production_agent = Agent(
    provider="google",
    model="gemini-3-flash",  # Fast, cost-effective
)

# For complex reasoning - use pro models
research_agent = Agent(
    provider="google",
    model="gemini-3-pro-preview",  # Advanced reasoning
)
```

### 2. Monitor Token Usage

Gemini models have different context windows and pricing:

```python
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    model_config={
        "max_tokens": 2048,  # Limit output to control costs
    }
)
```

### 3. Test with Flash, Deploy with Pro

```python
import os

# Development/testing
if os.getenv("ENV") == "development":
    model = "gemini-3-flash"
else:
    model = "gemini-3-pro-preview"

agent = Agent(
    provider="google",
    model=model,
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

### Project or Location Not Found

```bash
# Check if environment variables are set
echo $GOOGLE_CLOUD_PROJECT
echo $GOOGLE_CLOUD_LOCATION

# Set them if not on GCP (for local development)
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_LOCATION="us-central1"

# Or use gcloud to set up ADC
gcloud auth application-default login
```

### Import Error

```bash
# Install the Google AI packages
pip install google-generativeai google-auth

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

- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Gemini API Documentation](https://ai.google.dev/docs)
- [Agno Gemini Guide](https://docs.agno.com/models/google)
- [DCAF Documentation](../index.md)

## Support

For issues with Gemini in DCAF:

1. Check this guide
2. Review [Agno's Gemini docs](https://docs.agno.com/models/google)
3. Verify ADC is configured: `gcloud auth application-default login`
4. Check Vertex AI quotas in GCP Console
5. Open an issue on GitHub with logs

---

**Next Steps:**
- [Building Tools](building-tools.md)
- [Multi-Agent Systems](../core/a2a.md)
- [Working with Bedrock](working-with-bedrock.md)
