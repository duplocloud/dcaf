# Working with Google Vertex AI

DCAF supports Google Vertex AI as a unified provider for both **Google Gemini** and **Anthropic Claude** models, providing zero-configuration deployment on Google Cloud Platform.

## Overview

The `google` provider offers access to multiple model families through Vertex AI:

**Google Gemini Models:**

- **Gemini 3**: Latest generation with advanced reasoning
- **Gemini 2.x**: High-performance models with thinking budgets
- **Gemini 1.5**: Large context windows and efficient inference

**Anthropic Claude Models (via Vertex AI):**

- **Claude Opus 4**: Most capable Claude model for complex tasks
- **Claude Sonnet 4**: Balanced performance and cost
- **Claude Haiku 3.5**: Fast, cost-effective for simple tasks

DCAF automatically detects which model family you're using based on the model ID and routes to the correct backend — no extra configuration needed.

## Installation

Install the required dependencies for the models you plan to use:

```bash
# For Gemini models
pip install google-generativeai google-auth

# For Claude models on Vertex AI
pip install 'anthropic[vertex]'

# Or install DCAF with full Google/Vertex AI support
pip install dcaf[gemini]
```

## Configuration

### Zero Configuration on GCP (Recommended)

When running on GCP (GKE, GCE, Cloud Run), DCAF automatically detects your project and location:

```python
from dcaf.core import Agent

# Gemini — project/location auto-detected on GCP
agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
    system_prompt="You are a helpful assistant."
)

# Claude on Vertex AI — same provider, just change the model ID
agent = Agent(
    provider="google",
    model="claude-sonnet-4@20250514",
    system_prompt="You are a helpful assistant."
)
```

DCAF detects the model family from the model ID (e.g., IDs starting with `claude` are routed to the Anthropic Vertex AI backend) and uses the appropriate Agno model class automatically.

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

### Basic Claude on Vertex AI Agent

```python
from dcaf.core import Agent

agent = Agent(
    provider="google",
    model="claude-sonnet-4@20250514",
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

## Available Claude Models (via Vertex AI)

Anthropic Claude models are available through Vertex AI using the same `provider="google"` configuration. DCAF automatically detects Claude model IDs and routes them through the Vertex AI Anthropic backend.

!!! note "Model ID Format"
    Vertex AI Claude model IDs use the format `model-name@version` (e.g., `claude-sonnet-4@20250514`). This differs from the direct Anthropic API format.

### Claude 4

**claude-opus-4@20250805** - Most capable model for complex, multi-step tasks
```python
agent = Agent(provider="google", model="claude-opus-4@20250805")
```

**claude-sonnet-4@20250514** - Balanced performance and cost
```python
agent = Agent(provider="google", model="claude-sonnet-4@20250514")
```

### Claude 3.5

**claude-3-5-haiku@20241022** - Fast and cost-effective
```python
agent = Agent(provider="google", model="claude-3-5-haiku@20241022")
```

!!! tip "Check Vertex AI Model Garden"
    Available Claude model versions may change. Check the [Vertex AI Model Garden](https://console.cloud.google.com/vertex-ai/model-garden) or [Google Cloud documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude) for the latest available models and versions.

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

The Google provider always uses Vertex AI for both Gemini and Claude models. Project and location are auto-detected on GCP:

```python
from dcaf.core import Agent

# Gemini on Vertex AI - auto-detected!
agent = Agent(
    provider="google",
    model="gemini-2.5-pro",
)

# Claude on Vertex AI - same provider, same auto-detection!
agent = Agent(
    provider="google",
    model="claude-sonnet-4@20250514",
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
4. **For Claude models**: Claude must be enabled in your project's [Vertex AI Model Garden](https://console.cloud.google.com/vertex-ai/model-garden)

## Model Selection Guide

### Gemini Models

| Model | Best For | Context | Speed | Cost |
|-------|----------|---------|-------|------|
| **gemini-3-pro-preview** | Complex reasoning, multi-step tasks | Large | Slow | High |
| **gemini-3-flash** | General-purpose, balanced performance | Large | Fast | Low |
| **gemini-2.5-pro** | Advanced capabilities, thinking | Large | Medium | Medium |
| **gemini-2.5-flash** | Fast inference, good reasoning | Large | Very Fast | Low |
| **gemini-1.5-pro** | Huge context (2M tokens) | Massive | Medium | Medium |
| **gemini-1.5-flash** | Quick tasks, simple queries | Large | Very Fast | Very Low |

### Claude Models (via Vertex AI)

| Model | Best For | Context | Speed | Cost |
|-------|----------|---------|-------|------|
| **claude-opus-4@20250805** | Complex reasoning, agentic tasks | 200K | Slow | High |
| **claude-sonnet-4@20250514** | Balanced performance, tool use | 200K | Fast | Medium |
| **claude-3-5-haiku@20241022** | Quick tasks, high throughput | 200K | Very Fast | Low |

## Error Handling

Handle provider-specific errors:

```python
from dcaf.core import Agent

agent = Agent(
    provider="google",
    model="gemini-3-flash",  # or "claude-sonnet-4@20250514"
)

try:
    response = agent.run([
        {"role": "user", "content": "Hello!"}
    ])
    print(response.text)
except ImportError as e:
    print("Required package not installed:")
    print("  Gemini: pip install google-generativeai google-auth")
    print("  Claude: pip install 'anthropic[vertex]'")
except ValueError as e:
    print(f"Configuration error: {e}")
    print("Ensure GOOGLE_CLOUD_PROJECT and DCAF_GOOGLE_MODEL_LOCATION are set")
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

| Feature | Gemini (Vertex AI) | Claude (Vertex AI) | Claude (Bedrock) | GPT-4 |
|---------|--------------------|--------------------|------------------|-------|
| **Tool Use** | Excellent | Excellent | Excellent | Good |
| **Reasoning** | Strong (G3) | Excellent | Excellent | Strong |
| **Speed** | Very Fast (Flash) | Fast (Haiku) | Fast | Medium |
| **Context** | 2M (1.5 Pro) | 200K | 200K | 128K |
| **Cost** | Low (Flash) | Low (Haiku) | Medium | High |
| **Provider** | `google` | `google` | `bedrock` | `openai` / `azure` |

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
# For Gemini models
pip install google-generativeai google-auth

# For Claude models on Vertex AI
pip install 'anthropic[vertex]'

# Or upgrade if already installed
pip install --upgrade google-generativeai anthropic
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
- [Claude on Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/partner-models/claude)
- [Agno Gemini Guide](https://docs.agno.com/models/google)
- [Agno Vertex AI Claude Guide](https://docs.agno.com/models/providers/cloud/vertexai-claude/overview)
- [DCAF Documentation](../index.md)

## Support

For issues with the Google provider in DCAF:

1. Check this guide
2. Review [Agno's Gemini docs](https://docs.agno.com/models/google) or [Agno's Vertex AI Claude docs](https://docs.agno.com/models/providers/cloud/vertexai-claude/overview)
3. Verify ADC is configured: `gcloud auth application-default login`
4. Check Vertex AI quotas in GCP Console
5. For Claude models, verify access is enabled in [Model Garden](https://console.cloud.google.com/vertex-ai/model-garden)
6. Open an issue on GitHub with logs

---

## How Model Detection Works

When you set `provider="google"`, DCAF inspects the `model` ID to determine which Vertex AI backend to use:

| Model ID Pattern | Backend | Agno Class |
|-----------------|---------|------------|
| Starts with `claude` | Anthropic on Vertex AI | `agno.models.vertexai.claude.Claude` |
| Everything else | Google Gemini on Vertex AI | `agno.models.google.Gemini` |

This means you can switch between Gemini and Claude models by changing only the model ID — no provider or configuration changes required.

---

**Next Steps:**

- [Building Tools](building-tools.md)
- [Multi-Agent Systems](../core/a2a.md)
- [Working with Bedrock](working-with-bedrock.md)
