# BedrockLLM API Reference (Legacy)

!!! warning "Legacy API"
    This documents the **v1 API**. For new projects, use the [Core API](../core/index.md) which handles LLM configuration internally.
    
    See [Migration Guide](../guides/migration.md) to upgrade existing code.

The `BedrockLLM` class provides a unified interface for interacting with AWS Bedrock models using the Converse API. It handles message formatting, tool configuration, and response processing.

---

## Table of Contents

1. [Overview](#overview)
2. [Class: BedrockLLM](#class-bedrockllm)
3. [Methods](#methods)
4. [Message Formats](#message-formats)
5. [Tool Configuration](#tool-configuration)
6. [Configuration Options](#configuration-options)
7. [Examples](#examples)
8. [Error Handling](#error-handling)

---

## Overview

`BedrockLLM` wraps the AWS Bedrock Converse API, providing:

- Consistent interface across all Bedrock-supported models
- Automatic message normalization (role alternation)
- Tool schema formatting
- Streaming support
- Configurable timeouts and retries

### Import

```python
from dcaf.llm import BedrockLLM

# Or from the base module
from dcaf import BedrockLLM
```

---

## Class: BedrockLLM

```python
class BedrockLLM(LLM):
    """
    A class for interacting with AWS Bedrock LLMs using the Converse API.
    Provides consistent interface across all Bedrock models.
    """
```

### Constructor

```python
def __init__(
    self,
    region_name: str = 'us-east-1',
    boto3_config: Optional[Config] = None
)
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `region_name` | `str` | `'us-east-1'` | AWS region for Bedrock service |
| `boto3_config` | `Optional[Config]` | `None` | Custom boto3 configuration |

#### Configuration Priority

1. **Explicit `boto3_config`** - Full control, overrides everything
2. **Environment Variables** - Deployment-time configuration
3. **Defaults** - Sensible out-of-the-box settings

#### Environment Variables

When `boto3_config=None`, these environment variables are used:

| Variable | Default | Description |
|----------|---------|-------------|
| `BOTO3_READ_TIMEOUT` | `20` | Read timeout in seconds |
| `BOTO3_CONNECT_TIMEOUT` | `10` | Connect timeout in seconds |
| `BOTO3_MAX_ATTEMPTS` | `3` | Maximum retry attempts |
| `BOTO3_RETRY_MODE` | `standard` | Retry mode (`standard`, `adaptive`, `legacy`) |

#### Examples

```python
# 1. Using defaults
llm = BedrockLLM()

# 2. Specify region
llm = BedrockLLM(region_name="us-west-2")

# 3. Using environment variables
# export BOTO3_READ_TIMEOUT=30
# export BOTO3_MAX_ATTEMPTS=5
llm = BedrockLLM()  # Picks up env vars

# 4. Custom boto3 config (takes precedence)
from botocore.config import Config

custom_config = Config(
    read_timeout=60,
    connect_timeout=15,
    retries={
        'max_attempts': 5,
        'mode': 'adaptive'
    }
)
llm = BedrockLLM(boto3_config=custom_config)
```

---

## Methods

### invoke()

Invoke the LLM and get a complete response.

```python
def invoke(
    self,
    messages: List[Dict[str, Any]],
    model_id: str,
    max_tokens: int = 1000,
    temperature: float = 0.0,
    top_p: float = 0.9,
    system_prompt: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    additional_model_request_fields: Optional[Dict[str, Any]] = None,
    performance_config: Optional[Dict[str, str]] = None,
    **kwargs
) -> Dict[str, Any]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `messages` | `List[Dict]` | Yes | Conversation messages |
| `model_id` | `str` | Yes | Bedrock model ID |
| `max_tokens` | `int` | No | Maximum tokens to generate (default: 1000) |
| `temperature` | `float` | No | Sampling temperature 0-1 (default: 0.0) |
| `top_p` | `float` | No | Nucleus sampling parameter (default: 0.9) |
| `system_prompt` | `str` | No | System prompt for model behavior |
| `tools` | `List[Dict]` | No | Tool specifications |
| `tool_choice` | `str|Dict` | No | Tool choice strategy |
| `additional_model_request_fields` | `Dict` | No | Model-specific parameters |
| `performance_config` | `Dict` | No | Performance settings |

#### Returns

Returns the raw Converse API response:

```python
{
    "output": {
        "message": {
            "role": "assistant",
            "content": [
                {"text": "Response text..."},
                # Or tool use blocks
                {
                    "toolUse": {
                        "toolUseId": "unique-id",
                        "name": "tool_name",
                        "input": {...}
                    }
                }
            ]
        }
    },
    "stopReason": "end_turn|tool_use|max_tokens",
    "usage": {
        "inputTokens": 100,
        "outputTokens": 50
    }
}
```

#### Example

```python
# Simple invocation
response = llm.invoke(
    messages=[
        {"role": "user", "content": "Explain quantum computing in simple terms"}
    ],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=500,
    temperature=0.7
)

# Extract text response
text = response['output']['message']['content'][0]['text']
print(text)
```

---

### invoke_stream()

Stream responses from the LLM.

```python
def invoke_stream(
    self,
    messages: list,
    model_id: str,
    system_prompt: Optional[str] = None,
    tools: Optional[list] = None,
    max_tokens: int = 1000,
    temperature: float = 0.0,
    additional_params: Optional[Dict[str, Any]] = None
) -> Generator[Dict, None, None]
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `messages` | `list` | Yes | Messages in Converse format |
| `model_id` | `str` | Yes | Bedrock model ID |
| `system_prompt` | `str` | No | System prompt |
| `tools` | `list` | No | Tool configurations |
| `max_tokens` | `int` | No | Maximum tokens (default: 1000) |
| `temperature` | `float` | No | Temperature (default: 0.0) |
| `additional_params` | `Dict` | No | Additional inference config |

#### Yields

Raw event dictionaries from the Bedrock stream:

```python
# Text delta event
{"contentBlockDelta": {"delta": {"text": "Hello"}}}

# Content block start
{"contentBlockStart": {...}}

# Message complete
{"messageStop": {"stopReason": "end_turn"}}
```

#### Example

```python
# Streaming response
for event in llm.invoke_stream(
    messages=[{"role": "user", "content": "Tell me a story"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=500
):
    if "contentBlockDelta" in event:
        delta = event["contentBlockDelta"].get("delta", {})
        if "text" in delta:
            print(delta["text"], end="", flush=True)
```

---

### normalize_message_roles()

Normalize messages to ensure proper role alternation.

```python
def normalize_message_roles(
    self,
    messages: List[Dict[str, Any]]
) -> List[Dict[str, Any]]
```

#### Purpose

Bedrock's Converse API requires strict role alternation between 'user' and 'assistant'. This method:

- Merges consecutive messages with the same role
- Removes empty messages
- Handles both string and list content formats

#### Example

```python
# Input: Consecutive user messages
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "user", "content": "How are you?"},  # Same role!
    {"role": "assistant", "content": "Hi there!"},
    {"role": "user", "content": "Great!"}
]

# After normalization
normalized = llm.normalize_message_roles(messages)
# [
#     {"role": "user", "content": "Hello\nHow are you?"},  # Merged
#     {"role": "assistant", "content": "Hi there!"},
#     {"role": "user", "content": "Great!"}
# ]
```

---

## Message Formats

### Simple String Content

```python
messages = [
    {"role": "user", "content": "Hello, how are you?"},
    {"role": "assistant", "content": "I'm doing well, thanks!"},
    {"role": "user", "content": "Great to hear!"}
]
```

### List Content (Multiple Blocks)

```python
messages = [
    {
        "role": "user",
        "content": [
            {"text": "Look at this image:"},
            {"image": {"format": "png", "source": {"bytes": b"..."}}}
        ]
    }
]
```

### Tool Results

```python
messages = [
    {"role": "user", "content": "What's the weather in NYC?"},
    {
        "role": "assistant",
        "content": [
            {
                "toolUse": {
                    "toolUseId": "tool123",
                    "name": "get_weather",
                    "input": {"location": "New York, NY"}
                }
            }
        ]
    },
    {
        "role": "user",
        "content": [
            {
                "toolResult": {
                    "toolUseId": "tool123",
                    "content": [{"text": "72°F, sunny"}]
                }
            }
        ]
    }
]
```

---

## Tool Configuration

### Tool Schema Format

```python
tools = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and state, e.g., San Francisco, CA"
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "Temperature unit"
                }
            },
            "required": ["location"]
        }
    }
]
```

### Tool Choice Options

```python
# Auto (default) - Model decides whether to use tools
response = llm.invoke(messages=..., tools=tools, tool_choice="auto")

# Any - Model must use at least one tool
response = llm.invoke(messages=..., tools=tools, tool_choice="any")

# Specific tool - Force use of a specific tool
response = llm.invoke(
    messages=..., 
    tools=tools, 
    tool_choice={"type": "tool", "name": "get_weather"}
)
```

### Complete Tool Example

```python
from dcaf.llm import BedrockLLM

llm = BedrockLLM()

# Define tools
tools = [
    {
        "name": "get_stock_price",
        "description": "Get the current stock price for a ticker symbol",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL)"
                }
            },
            "required": ["ticker"]
        }
    }
]

# Invoke with tools
response = llm.invoke(
    messages=[{"role": "user", "content": "What's Apple's stock price?"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    system_prompt="You are a financial assistant.",
    tools=tools
)

# Check if model wants to use a tool
content = response['output']['message']['content']
for block in content:
    if 'toolUse' in block:
        tool_use = block['toolUse']
        print(f"Tool: {tool_use['name']}")
        print(f"Input: {tool_use['input']}")
```

---

## Configuration Options

### Performance Configuration

```python
# Optimize for latency
response = llm.invoke(
    messages=...,
    model_id=...,
    performance_config={"latency": "optimized"}
)
```

### Additional Model Fields

For model-specific parameters:

```python
# Anthropic-specific parameters
response = llm.invoke(
    messages=...,
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    additional_model_request_fields={
        "anthropic_version": "bedrock-2023-05-31"
    }
)
```

---

## Examples

### Basic Chat

```python
from dcaf.llm import BedrockLLM

llm = BedrockLLM(region_name="us-east-1")

response = llm.invoke(
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=200,
    temperature=0
)

# Extract response text
text = response['output']['message']['content'][0]['text']
print(text)  # "The capital of France is Paris."
```

### Multi-Turn Conversation

```python
conversation = [
    {"role": "user", "content": "My name is Alice."},
    {"role": "assistant", "content": "Nice to meet you, Alice!"},
    {"role": "user", "content": "What is my name?"}
]

response = llm.invoke(
    messages=conversation,
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    system_prompt="You are a helpful assistant with a good memory."
)

# "Your name is Alice!"
```

### With System Prompt

```python
response = llm.invoke(
    messages=[{"role": "user", "content": "Explain photosynthesis"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    system_prompt="""You are a biology teacher for 5th graders. 
    Explain concepts using simple language and fun analogies.""",
    max_tokens=500
)
```

### Streaming Chat

```python
import sys

# Stream a long response
for event in llm.invoke_stream(
    messages=[{"role": "user", "content": "Write a haiku about coding"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=100
):
    if "contentBlockDelta" in event:
        text = event["contentBlockDelta"].get("delta", {}).get("text", "")
        sys.stdout.write(text)
        sys.stdout.flush()
```

---

## Error Handling

### Common Exceptions

```python
from botocore.exceptions import ClientError

try:
    response = llm.invoke(
        messages=[{"role": "user", "content": "Hello"}],
        model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0"
    )
except ClientError as e:
    error_code = e.response['Error']['Code']
    
    if error_code == 'ExpiredTokenException':
        print("AWS credentials expired. Refresh them.")
    elif error_code == 'ResourceNotFoundException':
        print("Model not found. Check model ID and region.")
    elif error_code == 'ThrottlingException':
        print("Rate limited. Implement backoff.")
    elif error_code == 'ValidationException':
        print("Invalid request. Check message format.")
    else:
        print(f"Error: {e}")
```

### Retry Configuration

```python
from botocore.config import Config

# Aggressive retry for production
config = Config(
    retries={
        'max_attempts': 10,
        'mode': 'adaptive'  # Smart backoff
    }
)

llm = BedrockLLM(boto3_config=config)
```

---

## Model IDs

### Common Bedrock Model IDs

| Model | ID |
|-------|-----|
| Claude 3.5 Sonnet | `us.anthropic.claude-3-5-sonnet-20240620-v1:0` |
| Claude 3 Sonnet | `us.anthropic.claude-3-sonnet-20240229-v1:0` |
| Claude 3 Haiku | `us.anthropic.claude-3-5-haiku-20241022-v1:0` |
| Claude 3 Opus | `us.anthropic.claude-opus-4-20250514-v1:0` |

### Cross-Region Inference

Use the `us.` prefix for cross-region inference profiles:

```python
# Cross-region (recommended)
model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"

# Single region
model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
```

---

## See Also

- [Tools API Reference](./tools.md)
- [Agents API Reference](./agents.md)
- [Working with AWS Bedrock Guide](../guides/working-with-bedrock.md)
- [AWS Bedrock Converse API Documentation](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)

