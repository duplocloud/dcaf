# Gemini Support in DCAF

## Summary

DCAF **already had Gemini support** built-in through the Agno adapter! This document provides comprehensive documentation and examples for using Google Gemini models with DCAF.

## What Was Added

### 📚 Documentation

**New Guide:** `docs/guides/working-with-gemini.md`
- Complete guide for using Gemini with DCAF
- Covers all Gemini model families (3.x, 2.x, 1.5)
- Configuration examples (API keys, Vertex AI, model parameters)
- Tool usage with Gemini
- Streaming responses
- REST server setup
- Multi-agent systems
- Best practices and troubleshooting

### 💻 Example Code

**New Example:** `examples/gemini_example.py`
- 6 comprehensive examples demonstrating:
  1. Basic Gemini usage
  2. Tool calling with Gemini
  3. Streaming responses
  4. Model configuration (temperature, max tokens)
  5. Comparing different Gemini models
  6. Multi-turn conversations
- Prerequisites checking
- Error handling
- Production-ready patterns

### 📖 Updated Documentation

**README.md:**
- Added "Supported LLM Providers" section with comparison table
- Gemini listed alongside Bedrock, Anthropic, OpenAI, Azure, Ollama
- Quick reference for provider configuration
- Updated Key Guides section

**mkdocs.yml:**
- Added "Working with Gemini" to Guides navigation
- Positioned after "Working with Bedrock" for consistency

## Existing Gemini Implementation

The implementation was already present in `dcaf/core/adapters/outbound/agno/adapter.py`:

```python
def _create_google_model(self):
    """Create a Google AI (Gemini) model."""
    try:
        from agno.models.google import Gemini
    except ImportError as e:
        raise ImportError(
            "Google provider requires the 'google-generativeai' package. "
            "Install it with: pip install google-generativeai"
        ) from e
    
    model_kwargs = {
        "id": self._model_id,
        "max_output_tokens": self._max_tokens,
        "temperature": self._temperature,
    }
    
    if self._api_key:
        model_kwargs["api_key"] = self._api_key
    
    logger.info(f"Creating Google AI model: {self._model_id}")
    return Gemini(**model_kwargs)
```

**Supported since:** Initial Agno adapter implementation  
**No code changes needed:** Documentation and examples only

## Quick Start

### Installation

```bash
pip install google-generativeai
```

### Basic Usage

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

### Configuration

```bash
# Get API key from: https://aistudio.google.com
export GEMINI_API_KEY="your-api-key-here"

# Run example
python examples/gemini_example.py
```

## Supported Gemini Models

| Model | Family | Use Case |
|-------|--------|----------|
| `gemini-3-pro-preview` | Gemini 3 | Most capable, advanced reasoning |
| `gemini-3-flash` | Gemini 3 | Fast, balanced performance |
| `gemini-2.5-pro` | Gemini 2.x | Advanced with thinking budget |
| `gemini-2.5-flash` | Gemini 2.x | Fast with thinking support |
| `gemini-2.0-flash` | Gemini 2.x | Previous generation |
| `gemini-1.5-pro` | Gemini 1.5 | Large context (2M tokens) |
| `gemini-1.5-flash` | Gemini 1.5 | Lightweight, fast |

## Provider Configuration

DCAF's AgnoAdapter supports these providers:

```python
# Already documented in adapter.py __init__ docstring:
provider: The model provider. Supported values:
    - "bedrock": AWS Bedrock (Claude via AWS)
    - "anthropic": Direct Anthropic API
    - "openai": OpenAI API
    - "azure": Azure OpenAI
    - "google": Google AI (Gemini)      # ← Already supported!
    - "ollama": Local Ollama server
```

## Testing

Run the comprehensive example:

```bash
export GEMINI_API_KEY="your-key"
python examples/gemini_example.py
```

Or try in your code:

```python
from dcaf.core import Agent
import os

# Quick test
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)

print(agent.run([{"role": "user", "content": "Say hello!"}]).text)
```

## Multi-Provider Support

DCAF supports switching providers easily:

```python
# Use Gemini
agent = Agent(
    provider="google",
    model="gemini-3-flash",
    api_key=os.getenv("GEMINI_API_KEY")
)

# Or use Claude on Bedrock
agent = Agent(
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile"
)

# Or use direct Anthropic
agent = Agent(
    provider="anthropic",
    model="claude-3-sonnet-20240229",
    api_key=os.getenv("ANTHROPIC_API_KEY")
)
```

## Multi-Agent Systems

Use Gemini alongside other providers:

```python
from dcaf.core import Agent

# Gemini for research (fast, cost-effective)
researcher = Agent(
    name="researcher",
    provider="google",
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    tools=[web_search]
)

# Claude for orchestration (advanced reasoning)
orchestrator = Agent(
    name="orchestrator",
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile",
    tools=[researcher.as_tool()]
)
```

## File Structure

```
dcaf/
├── core/adapters/outbound/agno/
│   └── adapter.py                    # Gemini support (existing)
│       └── _create_google_model()    # Implementation
├── docs/guides/
│   └── working-with-gemini.md        # NEW: Complete guide
├── examples/
│   └── gemini_example.py             # NEW: Comprehensive examples
├── README.md                         # UPDATED: Provider table
├── mkdocs.yml                        # UPDATED: Navigation
└── GEMINI_SUPPORT.md                # NEW: This file
```

## Dependencies

**Required for Gemini:**
```bash
pip install google-generativeai
```

**Full DCAF with all providers:**
```bash
pip install google-generativeai  # Gemini
pip install anthropic            # Direct Anthropic
pip install openai               # OpenAI & Azure
pip install boto3 aioboto3       # Bedrock
```

## Resources

- **Documentation**: `docs/guides/working-with-gemini.md`
- **Example**: `examples/gemini_example.py`
- **Google AI Studio**: https://aistudio.google.com (get API keys)
- **Gemini API Docs**: https://ai.google.dev/docs
- **Agno Gemini Guide**: https://docs.agno.com/models/google

## Comparison: Providers in DCAF

| Provider | Models | Setup | Use Case |
|----------|--------|-------|----------|
| **Bedrock** | Claude 3.x | AWS credentials | Enterprise, AWS customers |
| **Gemini** | Gemini 3/2.x/1.5 | API key | Fast, cost-effective |
| **Anthropic** | Claude 3.x | API key | Direct API access |
| **OpenAI** | GPT-4/3.5 | API key | General purpose |
| **Azure** | GPT models | API key | Microsoft ecosystem |
| **Ollama** | Local LLMs | None | Offline, privacy |

## Next Steps

1. **Read the Guide**: `docs/guides/working-with-gemini.md`
2. **Run the Example**: `python examples/gemini_example.py`
3. **Try in Your Code**: Copy examples from the guide
4. **Deploy**: Use `serve()` to create REST APIs with Gemini agents
5. **Multi-Agent**: Combine Gemini with Claude for cost optimization

## Support

- Check `docs/guides/working-with-gemini.md` for troubleshooting
- Review Agno's Gemini docs: https://docs.agno.com/models/google
- Verify API key is valid at https://aistudio.google.com
- Open GitHub issues with logs and error messages

---

**Status**: ✅ Fully supported and documented  
**Date Added**: January 9, 2026  
**Implementation**: Already existed, documentation added
