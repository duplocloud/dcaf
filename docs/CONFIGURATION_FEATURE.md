# Environment-Driven Configuration Feature

## Summary

DCAF now supports full configuration through environment variables, making it production-ready for multi-environment deployments where provider and model settings can be changed without code modifications.

## What Was Added

### Core Configuration Module

**New Module:** `dcaf/core/config.py`
- Centralized configuration loading from environment variables
- Support for all providers (Bedrock, Gemini, Anthropic, OpenAI, Azure, Ollama)
- Auto-detection of provider-specific credentials
- Sensible defaults with override capability
- Configuration validation and logging

### Key Functions

```python
# Load all configuration from environment
config = load_agent_config()
agent = Agent(tools=[...], **config)

# Get provider from environment
provider = get_provider_from_env()

# Check if provider has credentials
if is_provider_configured("google"):
    # Use Gemini

# Auto-detect configured provider
provider = get_configured_provider()
```

### Environment Variables

#### Core Configuration
- `DCAF_PROVIDER` - Provider name (bedrock, google, anthropic, etc.)
- `DCAF_MODEL` - Model identifier (auto-detected if not set)
- `DCAF_TEMPERATURE` - Sampling temperature (0.0-1.0)
- `DCAF_MAX_TOKENS` - Maximum output tokens
- `DCAF_FRAMEWORK` - LLM framework (default: agno)

#### Provider Credentials
- **Bedrock**: `AWS_PROFILE`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- **Gemini**: `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- **Anthropic**: `ANTHROPIC_API_KEY`
- **OpenAI**: `OPENAI_API_KEY`
- **Azure**: `AZURE_OPENAI_API_KEY`

#### A2A Identity
- `DCAF_AGENT_NAME` - Agent name for A2A protocol
- `DCAF_AGENT_DESCRIPTION` - Agent description

#### Behavior Flags
- `DCAF_TOOL_CALL_LIMIT` - Max concurrent tool calls
- `DCAF_DISABLE_HISTORY` - Disable message history
- `DCAF_DISABLE_TOOL_FILTERING` - Disable tool filtering

## Updated Files

### Core Code (3 files)

1. **`dcaf/core/config.py`** (NEW - 489 lines)
   - Configuration loading and management
   - Environment variable handling
   - Provider detection and validation

2. **`dcaf/core/__init__.py`** (UPDATED)
   - Added config functions to public API
   - Exported `load_agent_config`, `get_provider_from_env`, etc.

3. **`env.example`** (UPDATED)
   - Added all DCAF configuration variables
   - Documented each provider's requirements
   - Example configurations for each provider

### Documentation (2 files)

1. **`docs/guides/environment-configuration.md`** (NEW - ~600 lines)
   - Complete guide to environment configuration
   - All environment variables documented
   - Configuration patterns and best practices
   - Docker, Kubernetes, and deployment examples
   - Troubleshooting guide

2. **`README.md`** (UPDATED)
   - Added "Environment Setup" section
   - Shows environment-driven configuration
   - Demonstrates switching providers without code changes

### Examples (1 file)

**`examples/config_driven_agent.py`** (NEW - executable)
- 5 comprehensive examples:
  1. Basic environment configuration
  2. Configuration with overrides
  3. Explicit provider selection
  4. Multi-environment setup
  5. Production pattern with error handling
- Configuration guide display
- Prerequisites checking

### Build System (1 file)

**`mkdocs.yml`** (UPDATED)
- Added "Environment Configuration" to Guides navigation

## Usage

### Basic Usage

```bash
# Set environment
export DCAF_PROVIDER=google
export DCAF_MODEL=gemini-3-flash
export GEMINI_API_KEY=your-key
```

```python
from dcaf.core import Agent, load_agent_config

# Load from environment
config = load_agent_config()
agent = Agent(tools=[my_tool], **config)
```

### Switch Providers

```bash
# Development - Gemini (fast, cheap)
export DCAF_PROVIDER=google
export GEMINI_API_KEY=dev-key

# Production - Bedrock (enterprise)
export DCAF_PROVIDER=bedrock
export AWS_PROFILE=production
```

**No code changes needed!**

### With Overrides

```python
# Load from env, override specific values
config = load_agent_config(
    temperature=0.9,
    name="my-agent"
)

agent = Agent(
    tools=[...],
    system_prompt="Custom prompt",
    **config
)
```

## Configuration Patterns

### Pattern 1: Pure Environment

```python
from dcaf.core import Agent, load_agent_config

config = load_agent_config()
agent = Agent(tools=[...], **config)
```

### Pattern 2: Environment with Overrides

```python
config = load_agent_config(temperature=0.9)
agent = Agent(tools=[...], **config)
```

### Pattern 3: Multi-Environment

```python
import os
from dcaf.core import load_agent_config

env = os.getenv("ENV", "development")

if env == "production":
    config = load_agent_config(provider="bedrock")
else:
    config = load_agent_config(provider="google")

agent = Agent(tools=[...], **config)
```

### Pattern 4: Auto-Detection

```python
from dcaf.core.config import get_configured_provider

provider = get_configured_provider()
config = load_agent_config(provider=provider)
agent = Agent(tools=[...], **config)
```

## Example .env Files

### Development

```bash
DCAF_PROVIDER=google
DCAF_MODEL=gemini-3-flash
GEMINI_API_KEY=your-dev-key
DCAF_TEMPERATURE=0.1
```

### Production

```bash
DCAF_PROVIDER=bedrock
DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
AWS_PROFILE=production
AWS_REGION=us-east-1
DCAF_AGENT_NAME=prod-agent
DCAF_TOOL_CALL_LIMIT=1
```

## Docker Integration

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
# Config loaded from environment at runtime
CMD ["python", "main.py"]
```

### Docker Compose

```yaml
services:
  agent-dev:
    build: .
    environment:
      - DCAF_PROVIDER=google
      - GEMINI_API_KEY=${GEMINI_API_KEY}
  
  agent-prod:
    build: .
    environment:
      - DCAF_PROVIDER=bedrock
      - AWS_PROFILE=production
    volumes:
      - ~/.aws:/root/.aws:ro
```

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-config
data:
  DCAF_PROVIDER: "bedrock"
  AWS_REGION: "us-west-2"
---
apiVersion: v1
kind: Secret
metadata:
  name: agent-secrets
stringData:
  AWS_ACCESS_KEY_ID: "..."
---
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: agent
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
```

## Benefits

### 1. Environment Separation

Different configurations for dev/staging/prod without code changes:

```bash
# Development
export $(cat .env.development | xargs)

# Production
export $(cat .env.production | xargs)
```

### 2. Provider Flexibility

Switch providers easily:

```bash
# Try Gemini in dev (fast/cheap)
DCAF_PROVIDER=google

# Use Bedrock in prod (enterprise)
DCAF_PROVIDER=bedrock
```

### 3. Security

Credentials in environment, not committed to git:

```gitignore
.env
.env.*
!.env.example
```

### 4. 12-Factor Compliance

Configuration separate from code, as recommended by [12-Factor App](https://12factor.net/config).

### 5. Cloud-Native

Works seamlessly with Docker, Kubernetes, AWS ECS, etc.

## API Reference

### load_agent_config()

```python
def load_agent_config(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    **overrides: Any
) -> Dict[str, Any]:
    """
    Load agent configuration from environment variables.
    
    Returns:
        Dictionary suitable for Agent(**config)
    """
```

### get_provider_from_env()

```python
def get_provider_from_env() -> str:
    """
    Get the provider from DCAF_PROVIDER environment variable.
    
    Returns:
        Provider name (bedrock, google, etc.)
    """
```

### is_provider_configured()

```python
def is_provider_configured(provider: str) -> bool:
    """
    Check if a provider has required credentials configured.
    
    Returns:
        True if provider can be used
    """
```

### get_configured_provider()

```python
def get_configured_provider() -> Optional[str]:
    """
    Get the first configured provider with credentials.
    
    Returns:
        Provider name or None
    """
```

## File Structure

```
dcaf/
├── core/
│   ├── config.py                          # NEW: Configuration module
│   └── __init__.py                        # UPDATED: Export config functions
├── docs/guides/
│   └── environment-configuration.md        # NEW: Complete guide
├── examples/
│   └── config_driven_agent.py             # NEW: Configuration examples
├── env.example                             # UPDATED: All variables
├── README.md                               # UPDATED: Environment setup
├── mkdocs.yml                              # UPDATED: Navigation
└── CONFIGURATION_FEATURE.md               # NEW: This file
```

## Testing

```bash
# Test with Gemini
export DCAF_PROVIDER=google
export GEMINI_API_KEY=your-key
python examples/config_driven_agent.py

# Test with Bedrock
export DCAF_PROVIDER=bedrock
export AWS_PROFILE=my-profile
python examples/config_driven_agent.py
```

## Migration Guide

### Before (Hardcoded)

```python
agent = Agent(
    provider="bedrock",
    model="anthropic.claude-3-sonnet-20240229-v1:0",
    aws_profile="my-profile",
    tools=[...]
)
```

### After (Environment-Driven)

```bash
# .env
DCAF_PROVIDER=bedrock
DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
AWS_PROFILE=my-profile
```

```python
from dcaf.core import Agent, load_agent_config

config = load_agent_config()
agent = Agent(tools=[...], **config)
```

## Best Practices

1. **Use `.env` files** for different environments
2. **Never commit** credentials (add `.env` to `.gitignore`)
3. **Use secrets management** in production (AWS Secrets Manager, etc.)
4. **Validate configuration** at startup
5. **Document required variables** in `.env.example`

## Resources

- **Documentation**: `docs/guides/environment-configuration.md`
- **Example**: `examples/config_driven_agent.py`
- **Example env**: `env.example`

## Next Steps

1. Set up `.env` files for your environments
2. Use `load_agent_config()` in your code
3. Deploy with Docker/K8s using environment config
4. Implement secrets management for production

---

**Status**: ✅ Feature complete and documented  
**Date Added**: January 9, 2026  
**Backward Compatible**: Yes (existing code still works)
