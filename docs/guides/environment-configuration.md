## Environment-Driven Configuration

DCAF supports full configuration through environment variables, making it easy to deploy agents across different environments (development, staging, production) and switch between LLM providers without code changes.

## Overview

Instead of hardcoding provider and model settings in your code, you can configure DCAF through environment variables:

```python
from dcaf.core import Agent, load_agent_config

# Load all configuration from environment
config = load_agent_config()
agent = Agent(tools=[my_tool], **config)
```

This approach offers several benefits:

- **Environment-specific settings**: Different providers for dev/staging/prod
- **No code changes**: Switch from Bedrock to Gemini via environment
- **Secure credentials**: API keys in environment, not committed to git
- **12-Factor App compliance**: Configuration separate from code

## Quick Start

### 1. Set Environment Variables

```bash
# Choose your provider
export DCAF_PROVIDER=google
export DCAF_MODEL=gemini-3-flash
export GEMINI_API_KEY=your-api-key
```

### 2. Load Configuration

```python
from dcaf.core import Agent, load_agent_config
from dcaf.tools import tool

@tool(description="Get weather")
def get_weather(city: str) -> str:
    return f"Weather in {city}: Sunny, 72°F"

# Load from environment
config = load_agent_config()

# Create agent
agent = Agent(tools=[get_weather], **config)
```

That's it! Your agent now uses Gemini.

### 3. Switch Providers

To switch to a different provider, just change the environment variables:

```bash
# Switch to Bedrock
export DCAF_PROVIDER=bedrock
export DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
export AWS_PROFILE=my-profile
export AWS_REGION=us-west-2
```

No code changes needed!

## Environment Variables

### Core Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `DCAF_PROVIDER` | Provider name | `bedrock` | `google`, `anthropic`, `openai` |
| `DCAF_MODEL` | Model identifier | Auto-detected | `gemini-3-flash`, `claude-3-sonnet` |
| `DCAF_FRAMEWORK` | LLM framework | `agno` | `agno` (only option currently) |
| `DCAF_TEMPERATURE` | Sampling temperature | `0.1` | `0.0` to `1.0` |
| `DCAF_MAX_TOKENS` | Maximum output tokens | `4096` | `2048`, `8192` |

### Provider Credentials

#### AWS Bedrock (`DCAF_PROVIDER=bedrock`)

```bash
# Option 1: AWS Profile (recommended)
AWS_PROFILE=my-profile
AWS_REGION=us-west-2

# Option 2: Direct credentials
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxx
AWS_REGION=us-west-2
```

#### Google Gemini (`DCAF_PROVIDER=google`)

```bash
GEMINI_API_KEY=your-gemini-api-key
# Or
GOOGLE_API_KEY=your-google-api-key
```

#### Anthropic Direct (`DCAF_PROVIDER=anthropic`)

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx
```

#### OpenAI (`DCAF_PROVIDER=openai`)

```bash
OPENAI_API_KEY=sk-xxxxx
```

#### Azure OpenAI (`DCAF_PROVIDER=azure`)

```bash
AZURE_OPENAI_API_KEY=xxxxx
```

#### Ollama (`DCAF_PROVIDER=ollama`)

```bash
# No credentials needed, runs locally
```

### A2A Identity

For Agent-to-Agent protocol:

```bash
DCAF_AGENT_NAME=my-agent
DCAF_AGENT_DESCRIPTION="My helpful agent"
```

### Behavior Flags

Advanced configuration:

```bash
DCAF_TOOL_CALL_LIMIT=1              # Max concurrent tool calls
DCAF_DISABLE_HISTORY=false          # Disable message history
DCAF_DISABLE_TOOL_FILTERING=false   # Disable tool filtering
```

## Configuration Patterns

### Pattern 1: Pure Environment

Everything from environment variables:

```python
from dcaf.core import Agent, load_agent_config

config = load_agent_config()
agent = Agent(tools=[...], **config)
```

### Pattern 2: Environment with Overrides

Load from environment, override specific values:

```python
from dcaf.core import Agent, load_agent_config

# Load base config from env
config = load_agent_config(
    temperature=0.9,  # Override temperature
    name="custom-agent"  # Override name
)

agent = Agent(
    tools=[...],
    system_prompt="Custom prompt",  # Add system prompt
    **config
)
```

### Pattern 3: Conditional Provider

Different providers for different environments:

```python
import os
from dcaf.core import Agent, load_agent_config

# Load config based on environment
env = os.getenv("ENV", "development")

if env == "production":
    # Production uses Bedrock
    config = load_agent_config(provider="bedrock")
elif env == "development":
    # Development uses Gemini (cheaper/faster)
    config = load_agent_config(provider="google", model="gemini-3-flash")
else:
    # Staging uses environment default
    config = load_agent_config()

agent = Agent(tools=[...], **config)
```

### Pattern 4: Provider Detection

Auto-detect which provider has credentials:

```python
from dcaf.core import Agent, load_agent_config
from dcaf.core.config import get_configured_provider

# Find first provider with credentials
provider = get_configured_provider()

if provider:
    config = load_agent_config(provider=provider)
    agent = Agent(tools=[...], **config)
else:
    raise RuntimeError("No provider configured!")
```

## Example .env Files

### Development (.env.development)

```bash
# Development - Use Gemini (fast, cheap)
DCAF_PROVIDER=google
DCAF_MODEL=gemini-3-flash
DCAF_TEMPERATURE=0.1
GEMINI_API_KEY=your-dev-key

# Agent identity
DCAF_AGENT_NAME=dev-agent
DCAF_AGENT_DESCRIPTION="Development agent"
```

### Staging (.env.staging)

```bash
# Staging - Use Claude on Bedrock
DCAF_PROVIDER=bedrock
DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
AWS_PROFILE=staging
AWS_REGION=us-west-2

# Agent identity
DCAF_AGENT_NAME=staging-agent
```

### Production (.env.production)

```bash
# Production - Use Claude on Bedrock with specific profile
DCAF_PROVIDER=bedrock
DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
AWS_PROFILE=production
AWS_REGION=us-east-1
DCAF_TEMPERATURE=0.1
DCAF_MAX_TOKENS=4096

# Agent identity
DCAF_AGENT_NAME=prod-agent
DCAF_AGENT_DESCRIPTION="Production help desk agent"

# Behavior
DCAF_TOOL_CALL_LIMIT=1
```

## Docker Integration

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY . .

# Agent will load config from environment
CMD ["python", "main.py"]
```

### Docker Compose

```yaml
version: '3.8'

services:
  # Development agent
  agent-dev:
    build: .
    environment:
      - DCAF_PROVIDER=google
      - DCAF_MODEL=gemini-3-flash
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    ports:
      - "8000:8000"
  
  # Production agent
  agent-prod:
    build: .
    environment:
      - DCAF_PROVIDER=bedrock
      - DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0
      - AWS_PROFILE=production
    volumes:
      - ~/.aws:/root/.aws:ro
    ports:
      - "8001:8000"
```

### Kubernetes

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-config
data:
  DCAF_PROVIDER: "bedrock"
  DCAF_MODEL: "anthropic.claude-3-sonnet-20240229-v1:0"
  AWS_REGION: "us-west-2"
---
apiVersion: v1
kind: Secret
metadata:
  name: agent-secrets
type: Opaque
stringData:
  AWS_ACCESS_KEY_ID: "AKIA..."
  AWS_SECRET_ACCESS_KEY: "..."
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: agent
        image: my-agent:latest
        envFrom:
        - configMapRef:
            name: agent-config
        - secretRef:
            name: agent-secrets
```

## Configuration API

### load_agent_config()

Load all configuration from environment:

```python
from dcaf.core import load_agent_config

# Load everything
config = load_agent_config()

# Load with overrides
config = load_agent_config(
    provider="google",
    model="gemini-3-flash",
    temperature=0.9
)

# Use config
agent = Agent(**config)
```

### get_provider_from_env()

Get the configured provider:

```python
from dcaf.core import get_provider_from_env

provider = get_provider_from_env()
print(f"Using provider: {provider}")  # "bedrock", "google", etc.
```

### get_model_from_env()

Get the configured model:

```python
from dcaf.core import get_model_from_env

model = get_model_from_env()
print(f"Using model: {model}")
```

### is_provider_configured()

Check if a provider has credentials:

```python
from dcaf.core.config import is_provider_configured

if is_provider_configured("google"):
    print("✓ Gemini credentials configured")
else:
    print("✗ Gemini credentials missing")
```

### get_configured_provider()

Find first provider with credentials:

```python
from dcaf.core.config import get_configured_provider

provider = get_configured_provider()
if provider:
    print(f"Using {provider}")
else:
    print("No provider configured")
```

## Best Practices

### 1. Use .env Files

Create separate `.env` files for each environment:

```bash
.env.development
.env.staging
.env.production
```

Load the appropriate file:

```bash
# Development
export $(cat .env.development | xargs)

# Production
export $(cat .env.production | xargs)
```

Or use python-dotenv:

```python
from dotenv import load_dotenv
import os

env = os.getenv("ENV", "development")
load_dotenv(f".env.{env}")

from dcaf.core import Agent, load_agent_config
agent = Agent(**load_agent_config())
```

### 2. Never Commit Credentials

Add to `.gitignore`:

```gitignore
.env
.env.*
!.env.example
```

### 3. Use Secrets Management

For production, use a secrets manager:

```python
import boto3
from dcaf.core import Agent

# Load from AWS Secrets Manager
secrets = boto3.client('secretsmanager')
secret = secrets.get_secret_value(SecretId='prod/agent-config')
config = json.loads(secret['SecretString'])

agent = Agent(
    provider=config['provider'],
    model=config['model'],
    api_key=config['api_key'],
    tools=[...]
)
```

### 4. Validate Configuration

Check configuration at startup:

```python
from dcaf.core import load_agent_config
from dcaf.core.config import is_provider_configured, get_provider_from_env

provider = get_provider_from_env()

if not is_provider_configured(provider):
    raise RuntimeError(
        f"Provider '{provider}' not configured. "
        f"Set required environment variables."
    )

config = load_agent_config()
agent = Agent(**config)
```

### 5. Document Required Variables

Create a README or `.env.example`:

```bash
# Copy to .env and fill in values
cp .env.example .env

# Edit .env with your credentials
vim .env
```

## Troubleshooting

### Provider Not Configured

**Error**: `No provider configured` or `Provider 'xxx' not configured`

**Solution**: Set required environment variables for your provider:

```bash
# For Bedrock
export AWS_PROFILE=my-profile

# For Gemini
export GEMINI_API_KEY=your-key

# Check what's configured
python -c "from dcaf.core.config import get_configured_provider; print(get_configured_provider())"
```

### Wrong Model for Provider

**Error**: Model not found or invalid model

**Solution**: Use provider-appropriate model IDs:

```bash
# Bedrock models
DCAF_MODEL=anthropic.claude-3-sonnet-20240229-v1:0

# Gemini models
DCAF_MODEL=gemini-3-flash

# Anthropic direct
DCAF_MODEL=claude-3-sonnet-20240229
```

### Environment Variables Not Loading

**Error**: Agent uses defaults instead of environment values

**Solution**: Check that variables are exported:

```bash
# Check if set
echo $DCAF_PROVIDER

# Export if needed
export DCAF_PROVIDER=google

# Or load from file
export $(cat .env | xargs)
```

### Missing API Key

**Error**: `ImportError` or authentication errors

**Solution**: Set the correct API key variable:

```bash
# Gemini
export GEMINI_API_KEY=your-key

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-xxx

# OpenAI
export OPENAI_API_KEY=sk-xxx
```

## Examples

Complete examples in the repository:

- `examples/config_driven_agent.py` - Environment-driven configuration
- `examples/multi_environment.py` - Switching environments
- `examples/docker_deployment/` - Docker with environment config

## Resources

- [12-Factor App Methodology](https://12factor.net/config)

## Next Steps

- Set up `.env` files for your environments
- Use `load_agent_config()` in your agents
- Deploy with Docker/Kubernetes using environment config
- Implement secrets management for production
