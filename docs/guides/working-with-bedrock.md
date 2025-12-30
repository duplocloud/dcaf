# Working with AWS Bedrock Guide

This guide covers how to effectively use AWS Bedrock with DCAF, including configuration, model selection, tool integration, and best practices.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Setup and Configuration](#setup-and-configuration)
3. [Model Selection](#model-selection)
4. [Using the BedrockLLM Client](#using-the-bedrockllm-client)
5. [Tool Integration](#tool-integration)
6. [Streaming](#streaming)
7. [Performance Optimization](#performance-optimization)
8. [Error Handling](#error-handling)
9. [Best Practices](#best-practices)

---

## Introduction

DCAF uses AWS Bedrock's Converse API to interact with foundation models. The Converse API provides:

- **Unified interface** across all Bedrock models
- **Tool calling** (function calling) support
- **Streaming** responses
- **Multi-turn conversations**
- **Consistent message format**

### Key Concepts

- **Model ID**: Identifies the model to use (e.g., `us.anthropic.claude-3-5-sonnet-20240620-v1:0`)
- **Converse API**: AWS Bedrock's unified API for all models
- **Tool Config**: How tools are defined for LLM consumption
- **Inference Config**: Parameters like temperature, max tokens

---

## Setup and Configuration

### Prerequisites

1. **AWS Account** with Bedrock access
2. **IAM permissions** for Bedrock
3. **Model access** enabled in AWS console

### Required IAM Permissions

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/anthropic.*",
                "arn:aws:bedrock:*::foundation-model/amazon.*"
            ]
        }
    ]
}
```

### Environment Setup

```bash
# .env file
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_SESSION_TOKEN=your_session_token  # If using temporary credentials
AWS_REGION=us-east-1

# Optional: Boto3 configuration
BOTO3_READ_TIMEOUT=20
BOTO3_CONNECT_TIMEOUT=10
BOTO3_MAX_ATTEMPTS=3
BOTO3_RETRY_MODE=standard
```

### Creating the LLM Client

```python
from dcaf.llm import BedrockLLM
import dotenv

# Load environment
dotenv.load_dotenv(override=True)

# Option 1: Defaults (recommended for most cases)
llm = BedrockLLM(region_name="us-east-1")

# Option 2: Custom boto3 config
from botocore.config import Config

custom_config = Config(
    read_timeout=60,
    connect_timeout=15,
    retries={
        'max_attempts': 5,
        'mode': 'adaptive'
    }
)
llm = BedrockLLM(region_name="us-east-1", boto3_config=custom_config)
```

---

## Model Selection

### Available Models

| Model | ID | Best For |
|-------|-----|----------|
| Claude 3.5 Sonnet | `us.anthropic.claude-3-5-sonnet-20240620-v1:0` | General purpose, balanced |
| Claude 3 Sonnet | `us.anthropic.claude-3-sonnet-20240229-v1:0` | Cost-effective general |
| Claude 3.5 Haiku | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Fast, simple tasks |
| Claude 4 Opus | `us.anthropic.claude-opus-4-20250514-v1:0` | Complex reasoning |

### Cross-Region Inference

Use the `us.` prefix for cross-region inference profiles:

```python
# Cross-region (recommended for availability)
model_id = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"

# Single region
model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
```

### Choosing the Right Model

```python
# For fast, simple operations (routing, classification)
fast_model = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

# For general purpose (most agents)
general_model = "us.anthropic.claude-3-5-sonnet-20240620-v1:0"

# For complex reasoning (advanced analysis)
complex_model = "us.anthropic.claude-opus-4-20250514-v1:0"
```

---

## Using the BedrockLLM Client

### Basic Invocation

```python
from dcaf.llm import BedrockLLM

llm = BedrockLLM()

response = llm.invoke(
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=100
)

# Extract text
text = response['output']['message']['content'][0]['text']
print(text)  # "The capital of France is Paris."
```

### With System Prompt

```python
response = llm.invoke(
    messages=[
        {"role": "user", "content": "Explain quantum computing"}
    ],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    system_prompt="""You are a physics teacher for high school students.
    Use simple language and helpful analogies.
    Keep explanations under 3 paragraphs.""",
    max_tokens=500
)
```

### Multi-Turn Conversation

```python
conversation = [
    {"role": "user", "content": "My name is Alice"},
    {"role": "assistant", "content": "Nice to meet you, Alice!"},
    {"role": "user", "content": "What did I just tell you?"}
]

response = llm.invoke(
    messages=conversation,
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=100
)

# "You told me your name is Alice."
```

### Inference Parameters

```python
response = llm.invoke(
    messages=[{"role": "user", "content": "Write a creative story"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=1000,      # Maximum output tokens
    temperature=0.8,      # Higher = more creative (0-1)
    top_p=0.9             # Nucleus sampling parameter
)
```

| Parameter | Range | Description |
|-----------|-------|-------------|
| `max_tokens` | 1-4096+ | Maximum tokens to generate |
| `temperature` | 0-1 | Randomness (0=deterministic) |
| `top_p` | 0-1 | Nucleus sampling threshold |

---

## Tool Integration

### Defining Tools

```python
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
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

### Invoking with Tools

```python
response = llm.invoke(
    messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    tools=tools
)

# Check for tool use
content = response['output']['message']['content']
for block in content:
    if 'toolUse' in block:
        tool_use = block['toolUse']
        print(f"Tool: {tool_use['name']}")
        print(f"Input: {tool_use['input']}")
```

### Tool Choice Strategies

```python
# Auto (default) - Model decides
response = llm.invoke(
    messages=...,
    tools=tools,
    tool_choice="auto"
)

# Any - Must use a tool
response = llm.invoke(
    messages=...,
    tools=tools,
    tool_choice="any"
)

# Specific - Must use this tool
response = llm.invoke(
    messages=...,
    tools=tools,
    tool_choice={"type": "tool", "name": "get_weather"}
)
```

### Complete Tool Loop

```python
def process_with_tools(user_message: str, tools: list, tool_functions: dict):
    """Complete tool execution loop."""
    messages = [{"role": "user", "content": user_message}]
    
    while True:
        # Call LLM
        response = llm.invoke(
            messages=messages,
            model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
            tools=tools
        )
        
        content = response['output']['message']['content']
        stop_reason = response.get('stopReason', '')
        
        # Check for tool use
        tool_uses = [b for b in content if 'toolUse' in b]
        
        if not tool_uses:
            # No tools, return text response
            text = next((b['text'] for b in content if 'text' in b), "")
            return text
        
        # Execute tools
        tool_results = []
        for block in tool_uses:
            tool_use = block['toolUse']
            tool_name = tool_use['name']
            tool_input = tool_use['input']
            tool_id = tool_use['toolUseId']
            
            # Execute the tool
            if tool_name in tool_functions:
                result = tool_functions[tool_name](**tool_input)
            else:
                result = f"Unknown tool: {tool_name}"
            
            tool_results.append({
                "toolResult": {
                    "toolUseId": tool_id,
                    "content": [{"text": str(result)}]
                }
            })
        
        # Add assistant message with tool use
        messages.append({
            "role": "assistant",
            "content": content
        })
        
        # Add tool results
        messages.append({
            "role": "user",
            "content": tool_results
        })

# Usage
def get_weather(location: str, unit: str = "celsius"):
    return f"Weather in {location}: 72°F, sunny"

result = process_with_tools(
    "What's the weather in NYC?",
    tools=tools,
    tool_functions={"get_weather": get_weather}
)
```

---

## Streaming

### Basic Streaming

```python
import sys

for event in llm.invoke_stream(
    messages=[{"role": "user", "content": "Tell me a story"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    max_tokens=500
):
    if "contentBlockDelta" in event:
        delta = event["contentBlockDelta"].get("delta", {})
        if "text" in delta:
            sys.stdout.write(delta["text"])
            sys.stdout.flush()
```

### Event Types

```python
for event in llm.invoke_stream(...):
    if "messageStart" in event:
        print("Stream started")
    
    elif "contentBlockStart" in event:
        # New content block (text or tool use)
        start = event["contentBlockStart"]
        if "toolUse" in start.get("start", {}):
            print(f"Tool: {start['start']['toolUse']['name']}")
    
    elif "contentBlockDelta" in event:
        delta = event["contentBlockDelta"]["delta"]
        if "text" in delta:
            print(delta["text"], end="")
        elif "toolUse" in delta:
            # Tool input streaming
            pass
    
    elif "contentBlockStop" in event:
        print()  # End of block
    
    elif "messageStop" in event:
        print(f"\nStop reason: {event['messageStop']['stopReason']}")
```

### Streaming with Tools

```python
accumulated_text = ""
current_tool = None

for event in llm.invoke_stream(
    messages=[{"role": "user", "content": "What's the weather?"}],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    tools=tools
):
    if "contentBlockStart" in event:
        start = event["contentBlockStart"].get("start", {})
        if "toolUse" in start:
            current_tool = {
                "name": start["toolUse"]["name"],
                "id": start["toolUse"]["toolUseId"],
                "input": ""
            }
    
    elif "contentBlockDelta" in event:
        delta = event["contentBlockDelta"]["delta"]
        
        if "text" in delta:
            accumulated_text += delta["text"]
            print(delta["text"], end="", flush=True)
        
        elif "toolUse" in delta and current_tool:
            current_tool["input"] += delta["toolUse"].get("input", "")
    
    elif "contentBlockStop" in event:
        if current_tool:
            print(f"\nTool call: {current_tool['name']}")
            current_tool = None
```

---

## Performance Optimization

### Timeout Configuration

```python
from botocore.config import Config

# For fast, short responses
fast_config = Config(
    read_timeout=10,
    connect_timeout=5
)

# For long, complex responses
slow_config = Config(
    read_timeout=120,
    connect_timeout=30
)

llm_fast = BedrockLLM(boto3_config=fast_config)
llm_slow = BedrockLLM(boto3_config=slow_config)
```

### Retry Configuration

```python
# Aggressive retry for production
production_config = Config(
    retries={
        'max_attempts': 10,
        'mode': 'adaptive'  # Smart exponential backoff
    }
)

# Light retry for development
dev_config = Config(
    retries={
        'max_attempts': 2,
        'mode': 'standard'
    }
)
```

### Latency Optimization

```python
# Use latency-optimized mode
response = llm.invoke(
    messages=[...],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",
    performance_config={"latency": "optimized"}
)
```

### Message Optimization

```python
# Let BedrockLLM normalize messages automatically
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "user", "content": "How are you?"},  # Will be merged
]

# Messages are automatically normalized:
# [{"role": "user", "content": "Hello\nHow are you?"}]
```

---

## Error Handling

### Common Errors

```python
from botocore.exceptions import ClientError

try:
    response = llm.invoke(messages=..., model_id=...)
except ClientError as e:
    error_code = e.response['Error']['Code']
    
    if error_code == 'ExpiredTokenException':
        # Refresh credentials
        print("Credentials expired - refresh with dcaf env-update-aws-creds")
        
    elif error_code == 'ResourceNotFoundException':
        # Model not found
        print("Model not found - check model ID and region")
        
    elif error_code == 'ThrottlingException':
        # Rate limited
        import time
        time.sleep(5)  # Wait and retry
        
    elif error_code == 'ValidationException':
        # Invalid request
        print("Invalid request - check message format")
        
    elif error_code == 'ServiceUnavailableException':
        # Service issue
        print("Bedrock temporarily unavailable")
        
    else:
        print(f"Unexpected error: {e}")
```

### Retry Wrapper

```python
import time
from botocore.exceptions import ClientError

def invoke_with_retry(llm, max_retries=3, **kwargs):
    """Invoke LLM with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return llm.invoke(**kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            
            # Don't retry validation errors
            if error_code == 'ValidationException':
                raise
            
            # Don't retry expired tokens
            if error_code == 'ExpiredTokenException':
                raise
            
            # Retry throttling and service errors
            if error_code in ['ThrottlingException', 'ServiceUnavailableException']:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
            else:
                raise
    
    raise Exception("Max retries exceeded")
```

---

## Best Practices

### 1. Use Appropriate Model for Task

```python
# Routing/classification - use fast model
routing_response = llm.invoke(
    messages=[...],
    model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",  # Fast
    max_tokens=10
)

# Main task - use capable model
main_response = llm.invoke(
    messages=[...],
    model_id="us.anthropic.claude-3-5-sonnet-20240620-v1:0",  # Capable
    max_tokens=1000
)
```

### 2. Set Appropriate Limits

```python
# Short responses
response = llm.invoke(
    messages=[{"role": "user", "content": "Yes or no: Is 2+2=4?"}],
    max_tokens=10,
    temperature=0  # Deterministic
)

# Creative tasks
response = llm.invoke(
    messages=[{"role": "user", "content": "Write a poem"}],
    max_tokens=500,
    temperature=0.8  # Creative
)
```

### 3. Use System Prompts Effectively

```python
system_prompt = """
Role: You are a Kubernetes expert assistant.

Guidelines:
- Always specify namespaces in commands
- Prefer kubectl over direct API calls
- Explain what each command does
- Warn about destructive operations

Format:
- Use code blocks for commands
- Keep explanations concise
"""

response = llm.invoke(
    messages=[...],
    system_prompt=system_prompt
)
```

### 4. Handle Empty Responses

```python
response = llm.invoke(messages=..., model_id=...)

content = response.get('output', {}).get('message', {}).get('content', [])

if not content:
    print("No content in response")
else:
    for block in content:
        if 'text' in block:
            print(block['text'])
```

### 5. Monitor Usage

```python
response = llm.invoke(messages=..., model_id=...)

# Check token usage
usage = response.get('usage', {})
print(f"Input tokens: {usage.get('inputTokens', 0)}")
print(f"Output tokens: {usage.get('outputTokens', 0)}")
```

---

## See Also

- [BedrockLLM API Reference](../api-reference/llm.md)
- [Agents API Reference](../api-reference/agents.md)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)

