# Raw LLM Request/Response Logging

## Overview

DCAF now includes comprehensive logging at multiple layers of the LLM invocation pipeline. This gives you complete visibility from high-level runtime parameters down to the raw Bedrock API calls.

## What Gets Logged

DCAF logs at **two levels**:

### Level 1: Agent Runtime Parameters (AgnoAdapter) - DEBUG Level
Logs what DCAF's agent runtime passes to the Agno adapter:

- **Messages**: Count and content of conversation messages
  - Role (user/assistant)
  - Text content
- **Tools**: List of available tools by name
- **System Prompts**:
  - `system_prompt`: Combined prompt
  - `static_system`: Cached static portion
  - `dynamic_system`: Non-cached dynamic portion
- **Platform Context**: Tenant, session, and other contextual data

**Log Level:** DEBUG (requires explicit DEBUG logging to see)
**Location:** `dcaf/core/adapters/outbound/agno/adapter.py` (lines 447-460)

### Level 2: Raw Bedrock API Calls (CachingAwsBedrock) - INFO Level
Logs the exact request sent to and response received from AWS Bedrock:

**Request (Sent to Bedrock):**
- **Model ID**: The Bedrock model identifier (e.g., `anthropic.claude-3-5-sonnet-20241022-v2:0`)
- **Messages**: The complete formatted message array in Bedrock's format
- **Request Body**: Including:
  - `system`: System prompt with cache checkpoints (if enabled)
  - `toolConfig`: Tool definitions
  - `inferenceConfig`: Temperature, max_tokens, etc.

**Response (Received from Bedrock):**
- **Complete JSON response** from Bedrock, including:
  - Response content (text, tool calls)
  - Token usage metrics
  - Cache metrics (if caching enabled)
  - Stop reason
  - Model metadata

**Log Level:** INFO (enabled by default)
**Location:** `dcaf/core/adapters/outbound/agno/caching_bedrock.py` (lines 299-319)

## How to Enable

DCAF uses **unified logging control** - one `LOG_LEVEL` environment variable controls both DCAF and Agno logging.

### Level 2 Only (Raw Bedrock API - Recommended for most users)

The raw Bedrock API logging is **automatically enabled** at INFO level:

```bash
# Via environment variable
export LOG_LEVEL=INFO
python your_script.py

# Or in your code
import logging
logging.basicConfig(level=logging.INFO)
```

That's it! You'll see the raw Bedrock requests/responses by default.

**What happens behind the scenes:**
- DCAF loggers show INFO level messages
- Agno SDK is automatically set to INFO level (no debug logs)

### Level 1 + Level 2 (Full Pipeline Visibility)

To see BOTH the agent runtime parameters AND raw Bedrock API calls:

```bash
# Via environment variable
export LOG_LEVEL=DEBUG
python your_script.py

# Or in your code
import logging
logging.basicConfig(level=logging.DEBUG)
```

This shows the complete flow from DCAF → Agno → Bedrock.

**What happens behind the scenes:**
- DCAF loggers show DEBUG + INFO level messages
- Agno SDK is automatically set to DEBUG mode with level=2 (verbose)
  - This includes Agno's internal debug logs showing request parameters, tool calls, etc.
  - You'll see messages like "Calling bedrock with request parameters: {...}"

## Unified Logging Control

DCAF automatically syncs Agno's logging with Python's standard logging level. This means **one environment variable controls everything**:

| `LOG_LEVEL` | DCAF Behavior | Agno Behavior |
|-------------|---------------|---------------|
| `WARNING` (30) | Shows WARNING+ messages | INFO level only (no debug) |
| `INFO` (20) | Shows INFO+ messages | INFO level only (no debug) |
| `DEBUG` (10) | Shows DEBUG+ messages | DEBUG mode with level=2 (verbose) |

### How It Works

When you initialize `AgnoAdapter`, it automatically:
1. Checks Python's root logger level
2. Calls Agno's `set_log_level_to_debug(level=2)` if DEBUG
3. Calls Agno's `set_log_level_to_info()` otherwise

This happens transparently - you don't need to configure Agno separately.

### Environment Variable Support

DCAF respects the standard `LOG_LEVEL` environment variable:

```bash
# Maximum verbosity (DCAF DEBUG + Agno DEBUG level=2)
export LOG_LEVEL=DEBUG

# Standard verbosity (DCAF INFO + Agno INFO)
export LOG_LEVEL=INFO

# Quiet mode (DCAF WARNING+ only)
export LOG_LEVEL=WARNING
```

**Note:** You can still use Agno's native `AGNO_DEBUG=true` if needed, but it's not necessary since DCAF controls it automatically.

### Disable Raw Logging (If Needed)

**Disable Level 2 (Raw Bedrock API) only:**
```python
import logging

# Set root logger to INFO
logging.basicConfig(level=logging.INFO)

# Disable raw Bedrock logging
bedrock_logger = logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock')
bedrock_logger.setLevel(logging.WARNING)
```

**Disable Both Levels:**
```python
import logging

# Set root logger to WARNING (disables INFO and DEBUG)
logging.basicConfig(level=logging.WARNING)
```

## Example Output

### Level 1: Agent Runtime Parameters (DEBUG level)
```
DEBUG:dcaf.core.adapters.outbound.agno.adapter:🔍 AGENT RUNTIME INVOKE PARAMETERS:
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Messages: 2 total
DEBUG:dcaf.core.adapters.outbound.agno.adapter:    [0] user: What is the capital of France?
DEBUG:dcaf.core.adapters.outbound.agno.adapter:    [1] assistant: The capital of France is Paris.
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Tools: 1 total
DEBUG:dcaf.core.adapters.outbound.agno.adapter:    - get_weather
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  System Prompt: You are a helpful assistant with access to weather data.
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Static System: None
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Dynamic System: None
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Platform Context: {'tenant': 'acme-corp', 'session_id': '123'}
```

### Level 2: Raw Bedrock Request (INFO level)
```
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:🔍 RAW LLM REQUEST TO BEDROCK:
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:  Model ID: anthropic.claude-3-5-sonnet-20241022-v2:0
DEBUG:dcaf.core.adapters.outbound.agno.caching_bedrock:  Messages (2 total):
DEBUG:dcaf.core.adapters.outbound.agno.caching_bedrock:[
    {
        "role": "user",
        "content": [
            {
                "text": "What is the capital of France?"
            }
        ]
    }
]
DEBUG:dcaf.core.adapters.outbound.agno.caching_bedrock:  Request Body:
DEBUG:dcaf.core.adapters.outbound.agno.caching_bedrock:{
    "system": [
        {
            "text": "You are a helpful assistant."
        },
        {
            "cachePoint": {
                "type": "default"
            }
        }
    ],
    "inferenceConfig": {
        "maxTokens": 4096,
        "temperature": 0.1
    }
}
```

### Level 2: Raw Bedrock Response (INFO level)
```
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:🔍 RAW LLM RESPONSE FROM BEDROCK:
DEBUG:dcaf.core.adapters.outbound.agno.caching_bedrock:{
    "output": {
        "message": {
            "role": "assistant",
            "content": [
                {
                    "text": "The capital of France is Paris."
                }
            ]
        }
    },
    "stopReason": "end_turn",
    "usage": {
        "inputTokens": 23,
        "outputTokens": 12,
        "totalTokens": 35,
        "cacheReadInputTokens": 15,
        "cacheCreationInputTokens": 0
    }
}
```

## Use Cases

### 1. Debugging LLM Issues
With two-level logging, you can trace issues from top to bottom:

**Level 1 (Runtime Parameters):**
- Are the right messages being passed from the application?
- Are tools being registered correctly?
- Is the system prompt structure correct (static vs dynamic)?
- Is platform context being injected?

**Level 2 (Raw Bedrock):**
- Did Agno format the messages correctly?
- Are tools being passed in Bedrock's format?
- Are cache checkpoints in the right place?

### 2. Performance Analysis
Examine token usage and cache performance:
- How many tokens are in each request?
- Is prompt caching working (check `cacheReadInputTokens`)?
- What's the cache hit rate?

### 3. Cost Tracking
Audit exact API calls for billing purposes:
- Count total requests
- Sum input/output tokens
- Calculate cache savings

### 4. Compliance & Auditing
Maintain a record of all LLM interactions:
- What data was sent to the LLM?
- What did the LLM return?
- When did each call happen?

## Streaming vs Non-Streaming

### Non-Streaming (`ainvoke`)
Logs the complete request and complete response.

### Streaming (`ainvoke_stream`)
- Logs the complete request before streaming starts
- Logs each chunk as it arrives (very verbose)
- Logs total chunk count when streaming completes

**Note:** Streaming chunk logs can be very verbose. Consider filtering or reducing log level for production streaming use.

## Implementation Details

The logging is implemented in `dcaf/core/adapters/outbound/agno/caching_bedrock.py` by overriding:
- `ainvoke()` - Async non-streaming invocation
- `ainvoke_stream()` - Async streaming invocation

The logging happens **after** message formatting but **before** the boto3 `converse()` call, capturing the exact parameters sent to Bedrock.

## Security Considerations

⚠️ **WARNING**: Raw request/response logs may contain:
- User input (potentially sensitive)
- System prompts (proprietary instructions)
- Tool definitions (business logic)
- API responses (potentially sensitive data)

**Best Practices:**
- Only enable DEBUG logging in development/staging environments
- Sanitize logs before sharing
- Use appropriate log retention policies
- Consider GDPR/privacy regulations when logging user data
- Rotate logs regularly

## Performance Impact

The logging overhead is minimal:
- `json.dumps()` serialization: ~1-5ms per call
- File I/O: Handled by Python's logging framework (buffered)
- **Overall impact**: < 0.1% of total LLM call time

If you need to disable it in production for performance reasons, set the logger level to WARNING (see "Disable Raw Logging" above).

## Troubleshooting

### Logs Not Appearing

1. **Check log level**: Ensure INFO is enabled (it should be by default)
   ```python
   import logging
   print(logging.getLogger().level)  # Should be 20 (INFO) or lower
   ```

2. **Check logger configuration**: Verify the logger is configured
   ```python
   logger = logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock')
   print(logger.level)
   print(logger.handlers)
   ```

3. **Check if CachingAwsBedrock is being used**: Verify your adapter is using the caching model
   ```python
   # In adapter.py
   print(type(model))  # Should be CachingAwsBedrock
   ```

### Too Much Output

If streaming logs are too verbose, you can filter them:

```python
import logging

class NoStreamChunkFilter(logging.Filter):
    def filter(self, record):
        # Skip individual stream chunk logs
        return 'Stream chunk #' not in record.getMessage()

logger = logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock')
logger.addFilter(NoStreamChunkFilter())
```

## Future Enhancements

Potential improvements for the future:
- [ ] Configurable log formatting (JSON, plain text, etc.)
- [ ] Sanitization hooks to redact sensitive data
- [ ] Token cost calculation in logs
- [ ] Structured logging (e.g., JSON logs for parsing)
- [ ] Export to observability platforms (DataDog, Splunk, etc.)

## Related Documentation

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
