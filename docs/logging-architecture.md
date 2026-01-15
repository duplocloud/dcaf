# DCAF Logging Architecture

## Overview

DCAF implements a comprehensive, multi-layer logging system that provides visibility into the entire LLM invocation pipeline, from high-level application parameters down to raw AWS Bedrock API calls. The system uses **unified logging control** where a single `LOG_LEVEL` environment variable controls both DCAF and Agno SDK logging.

## Architecture

### Three-Layer Logging Model

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Agent Runtime Parameters (DEBUG)                   │
│ Location: dcaf/core/adapters/outbound/agno/adapter.py       │
│ Shows: Messages, Tools, System Prompts, Platform Context    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Raw Bedrock API Calls (INFO)                       │
│ Location: dcaf/core/adapters/outbound/agno/caching_bedrock.py│
│ Shows: Request/Response JSON sent to/from AWS Bedrock       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Agno SDK Internal Debug (DEBUG)                    │
│ Location: Agno SDK (external library)                       │
│ Shows: Agno's internal operations, tool processing, etc.    │
└─────────────────────────────────────────────────────────────┘
```

### Layer Details

#### Layer 1: Agent Runtime Parameters (DEBUG Level)

**Purpose:** Shows what DCAF's application layer passes to the Agno adapter before any SDK processing.

**Log Level:** `DEBUG` (requires explicit DEBUG logging)

**Location:** `dcaf/core/adapters/outbound/agno/adapter.py:450-469` (ainvoke) and `533-552` (ainvoke_stream)

**What's Logged:**
- Message count and full content (role + text)
- Tool names (list of available tools)
- System prompt (combined, truncated to 200 chars)
- Static system prompt (cached portion, truncated)
- Dynamic system prompt (non-cached portion, truncated)
- Platform context (tenant, session, metadata)

**Example Output:**
```
DEBUG:dcaf.core.adapters.outbound.agno.adapter:🔍 AGENT RUNTIME INVOKE PARAMETERS:
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Messages: 2 total
DEBUG:dcaf.core.adapters.outbound.agno.adapter:    [0] user: What is the capital of France?
DEBUG:dcaf.core.adapters.outbound.agno.adapter:    [1] assistant: The capital of France is Paris.
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Tools: 1 total
DEBUG:dcaf.core.adapters.outbound.agno.adapter:    - get_weather
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  System Prompt: You are a helpful assistant...
DEBUG:dcaf.core.adapters.outbound.agno.adapter:  Platform Context: {'tenant': 'acme-corp'}
```

#### Layer 2: Raw Bedrock API Calls (INFO Level)

**Purpose:** Shows the exact request sent to AWS Bedrock and the exact response received, capturing the real API interaction.

**Log Level:** `INFO` (enabled by default)

**Location:** `dcaf/core/adapters/outbound/agno/caching_bedrock.py:299-327` (ainvoke) and `375-411` (ainvoke_stream)

**What's Logged:**

**Request:**
- Model ID (e.g., `anthropic.claude-3-5-sonnet-20241022-v2:0`)
- Complete formatted message array in Bedrock's format
- Request body including:
  - `system`: System prompt with cache checkpoints
  - `toolConfig`: Tool definitions in Bedrock format
  - `inferenceConfig`: Temperature, max_tokens, etc.

**Response:**
- Complete JSON response from Bedrock including:
  - Response content (text, tool calls)
  - Token usage metrics (`inputTokens`, `outputTokens`, `totalTokens`)
  - Cache metrics (`cacheReadInputTokens`, `cacheCreationInputTokens`)
  - Stop reason
  - Model metadata

**Example Output:**
```
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:🔍 RAW LLM REQUEST TO BEDROCK:
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:  Model ID: anthropic.claude-3-5-sonnet-20241022-v2:0
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:  Messages (1 total):
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:[
    {
        "role": "user",
        "content": [{"text": "What is the capital of France?"}]
    }
]
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:  Request Body:
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:{
    "system": [
        {"text": "You are a helpful assistant."},
        {"cachePoint": {"type": "default"}}
    ],
    "inferenceConfig": {
        "maxTokens": 4096,
        "temperature": 0.1
    }
}

INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:🔍 RAW LLM RESPONSE FROM BEDROCK:
INFO:dcaf.core.adapters.outbound.agno.caching_bedrock:{
    "output": {
        "message": {
            "role": "assistant",
            "content": [{"text": "The capital of France is Paris."}]
        }
    },
    "stopReason": "end_turn",
    "usage": {
        "inputTokens": 23,
        "outputTokens": 12,
        "totalTokens": 35,
        "cacheReadInputTokens": 15
    }
}
```

#### Layer 3: Agno SDK Internal Debug (DEBUG Level)

**Purpose:** Shows Agno SDK's internal operations, controlled automatically by DCAF's log level.

**Log Level:** `DEBUG` (enabled when DCAF is at DEBUG level)

**Location:** Agno SDK library (external)

**What's Logged:**
- Agno's internal debug messages (when `debug_level=2`)
- Messages like "Calling bedrock with request parameters: {...}"
- Tool processing details
- Agent state transitions

**Controlled By:** `_sync_agno_log_level()` function in adapter.py

## Unified Logging Control

### Design Philosophy

**One Environment Variable to Rule Them All**

Instead of requiring separate configuration for DCAF and Agno logging, the system uses a single `LOG_LEVEL` environment variable (Python standard) that automatically controls both frameworks.

### How It Works

#### 1. Initialization

When `AgnoAdapter` is initialized, it calls `_sync_agno_log_level()`:

```python
def _sync_agno_log_level() -> None:
    """
    Sync Agno's debug mode with DCAF's logging level.

    Maps Python logging levels to Agno debug modes:
    - DEBUG (10): Enable Agno debug mode with level=2 (verbose)
    - INFO (20) or higher: Disable Agno debug mode (INFO level only)
    """
    root_logger = logging.getLogger()
    current_level = root_logger.level

    if current_level <= logging.DEBUG:
        # Enable Agno debug mode with maximum verbosity
        set_log_level_to_debug(level=2)
        logger.debug("Agno debug mode enabled (level=2)")
    else:
        # Disable Agno debug mode (INFO level)
        set_log_level_to_info()
        logger.debug("Agno debug mode disabled (INFO only)")
```

**Location:** `dcaf/core/adapters/outbound/agno/adapter.py:42-68`

**Called From:** `AgnoAdapter.__init__()` at line 351

#### 2. Log Level Mapping

| `LOG_LEVEL` | Python Level | DCAF Layers | Agno SDK Behavior |
|-------------|--------------|-------------|-------------------|
| `DEBUG` | 10 | Layer 1 + Layer 2 | `set_log_level_to_debug(level=2)` - Verbose debug |
| `INFO` | 20 | Layer 2 only | `set_log_level_to_info()` - No debug logs |
| `WARNING` | 30 | Warnings only | `set_log_level_to_info()` - No debug logs |
| `ERROR` | 40 | Errors only | `set_log_level_to_info()` - No debug logs |

#### 3. Agno Debug Levels Explained

Agno SDK uses a **verbosity filter** on top of Python's logging levels:

- **`log_level=1`** (default): Basic debug messages
  - Example: "Connection already established", "Getting video data"
  - Most `log_debug()` calls without explicit `log_level` parameter

- **`log_level=2`** (verbose): Detailed request parameters
  - Example: "Calling bedrock with request parameters: {...}"
  - Used by all LLM provider models to log raw request data

When DCAF calls `set_log_level_to_debug(level=2)`, it enables **all** Agno debug logs (level 1 and 2).

**Agno's Implementation:**
```python
def log_debug(msg, log_level: Literal[1, 2] = 1, ...):
    global debug_on, debug_level

    if debug_on:
        if debug_level >= log_level:  # Show if global level >= message level
            logger.debug(msg)
```

### Usage Examples

#### Standard Usage (INFO - Shows Raw Bedrock API Only)

```python
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

# Or via environment variable
# export LOG_LEVEL=INFO

# Create adapter - automatically syncs Agno to INFO level
adapter = AgnoAdapter(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    provider="bedrock"
)

# You'll see Layer 2 logs (raw Bedrock API calls)
```

#### Debug Mode (DEBUG - Shows Everything)

```python
import logging

# Setup logging at DEBUG level
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)

# Or via environment variable
# export LOG_LEVEL=DEBUG

# Create adapter - automatically syncs Agno to DEBUG level=2
adapter = AgnoAdapter(
    model_id="anthropic.claude-3-5-sonnet-20241022-v2:0",
    provider="bedrock"
)

# You'll see:
# - Layer 1: Agent Runtime Parameters (DCAF)
# - Layer 2: Raw Bedrock API Calls (DCAF)
# - Layer 3: Agno SDK Internal Debug (Agno)
```

#### Quiet Mode (WARNING - Minimal Logging)

```python
import logging

logging.basicConfig(level=logging.WARNING)

# Or via environment variable
# export LOG_LEVEL=WARNING

# Only warnings and errors will be shown
```

## Implementation Details

### File Structure

```
dcaf/core/adapters/outbound/agno/
├── adapter.py              # Layer 1 logging + unified control
├── caching_bedrock.py      # Layer 2 logging
├── message_converter.py    # (no logging)
├── tool_converter.py       # (no logging)
└── types.py               # (no logging)
```

### Key Functions

#### 1. `_sync_agno_log_level()` (adapter.py:42-68)

- **Purpose:** Sync Agno's debug mode with DCAF's log level
- **Called:** Once during `AgnoAdapter.__init__()`
- **Imports:** `from agno.utils.log import set_log_level_to_debug, set_log_level_to_info`
- **Logic:** Checks root logger level, maps to Agno

#### 2. Layer 1 Logging (adapter.py:450-469, 533-552)

- **Purpose:** Log runtime parameters before Agno processing
- **Methods:** `ainvoke()` and `ainvoke_stream()`
- **Level:** `logger.debug()` - DEBUG level
- **Truncation:** System prompts truncated to 200 chars to reduce noise

#### 3. Layer 2 Logging (caching_bedrock.py:299-327, 375-411)

- **Purpose:** Log raw Bedrock API request/response
- **Methods:** `ainvoke()` and `ainvoke_stream()` overrides
- **Level:** `logger.info()` - INFO level
- **Format:** Full JSON with `json.dumps(indent=4, default=str)`
- **No Truncation:** Complete messages and responses logged

### Logger Names

Each module uses `logging.getLogger(__name__)`:

- **Layer 1:** `dcaf.core.adapters.outbound.agno.adapter`
- **Layer 2:** `dcaf.core.adapters.outbound.agno.caching_bedrock`
- **Layer 3 (Agno):** `agno` (controlled by Agno SDK)

You can selectively disable loggers if needed:

```python
import logging

# Disable only Layer 2 (raw Bedrock logs)
bedrock_logger = logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock')
bedrock_logger.setLevel(logging.WARNING)

# Disable only Layer 1 (runtime parameters)
adapter_logger = logging.getLogger('dcaf.core.adapters.outbound.agno.adapter')
adapter_logger.setLevel(logging.INFO)

# Disable Agno SDK logs
agno_logger = logging.getLogger('agno')
agno_logger.setLevel(logging.WARNING)
```

## Performance Considerations

### Overhead

The logging system has minimal performance impact:

- **JSON serialization:** ~1-5ms per call (using `json.dumps()`)
- **File I/O:** Buffered by Python's logging framework
- **Overall impact:** < 0.1% of total LLM call time (typically 1-5 seconds)

### When to Disable

Consider disabling verbose logging in production:

```python
import logging
import os

# Use environment variable for production control
log_level = os.getenv("LOG_LEVEL", "WARNING")
logging.basicConfig(level=getattr(logging, log_level))
```

Or disable specific layers:

```python
# Keep Layer 2 (raw API) but disable Layer 1 (runtime params)
logging.basicConfig(level=logging.INFO)

# This disables Layer 1 since it requires DEBUG
```

## Use Cases

### 1. Development & Debugging

**Problem:** LLM not responding as expected

**Solution:** Enable DEBUG logging to see:
- Layer 1: Are the right messages being passed? Is the system prompt correct?
- Layer 2: What exactly was sent to Bedrock? What did it return?
- Layer 3: How did Agno process the messages and tools?

```bash
export LOG_LEVEL=DEBUG
python my_app.py
```

### 2. Production Monitoring

**Problem:** Need to audit LLM API calls for billing/compliance

**Solution:** Enable INFO logging to capture raw API calls:

```bash
export LOG_LEVEL=INFO
python my_app.py 2>&1 | tee llm_audit.log
```

Parse `llm_audit.log` to extract:
- Request/response pairs (search for "🔍 RAW LLM")
- Token usage from responses (`inputTokens`, `outputTokens`)
- Cache performance (`cacheReadInputTokens`)

### 3. Performance Analysis

**Problem:** LLM calls are slow or expensive

**Solution:** Analyze Layer 2 logs for:
- Token counts per request (optimize prompt length)
- Cache hit rates (improve caching strategy)
- Response sizes (adjust `max_tokens`)

Example script:
```python
import json
import re

# Parse logs
with open('llm_audit.log') as f:
    logs = f.read()

# Extract token usage
usage_pattern = r'"usage": \{[^}]+\}'
for match in re.finditer(usage_pattern, logs):
    usage = json.loads('{' + match.group() + '}')
    print(f"Tokens: {usage['totalTokens']}, Cache hits: {usage.get('cacheReadInputTokens', 0)}")
```

### 4. Troubleshooting Caching

**Problem:** Prompt caching not working as expected

**Solution:** Check Layer 2 logs for:
- Cache checkpoint placement in request body
- Cache metrics in response (`cacheReadInputTokens`, `cacheCreationInputTokens`)
- Warnings about prompts being too short

Look for:
```json
{
    "system": [
        {"text": "Your static prompt..."},
        {"cachePoint": {"type": "default"}},  // ← Should be present
        {"text": "Dynamic context..."}
    ]
}
```

And in response:
```json
{
    "usage": {
        "cacheReadInputTokens": 1500,  // ← Cache HIT
        "cacheCreationInputTokens": 0
    }
}
```

## Environment Variables

### Primary Control

- **`LOG_LEVEL`**: Controls both DCAF and Agno logging
  - Values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
  - Default: `INFO` (if not set)
  - Example: `export LOG_LEVEL=DEBUG`

### Legacy Agno Variables (Not Recommended)

These still work but are **not necessary** since DCAF controls Agno automatically:

- **`AGNO_DEBUG`**: Enable Agno debug mode
  - Values: `true`, `false`
  - Overridden by DCAF's `_sync_agno_log_level()`

- **`AGNO_DEBUG_LEVEL`**: Set Agno debug verbosity
  - Values: `1` (basic), `2` (verbose)
  - DCAF always uses `2` when DEBUG is enabled

**Recommendation:** Use `LOG_LEVEL` only for unified control.

## Testing & Validation

### Verify Logging Setup

```python
import logging

# Check root logger level
root = logging.getLogger()
print(f"Root logger level: {logging.getLevelName(root.level)}")

# Check DCAF loggers
adapter_logger = logging.getLogger('dcaf.core.adapters.outbound.agno.adapter')
print(f"Adapter logger level: {logging.getLevelName(adapter_logger.level)}")

bedrock_logger = logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock')
print(f"Bedrock logger level: {logging.getLevelName(bedrock_logger.level)}")

# Check Agno logger
agno_logger = logging.getLogger('agno')
print(f"Agno logger level: {logging.getLevelName(agno_logger.level)}")
```

### Verify Agno Sync

After creating `AgnoAdapter`, check if Agno was synced:

```python
from agno.utils.log import debug_on, debug_level

adapter = AgnoAdapter(...)

print(f"Agno debug_on: {debug_on}")      # Should be True if LOG_LEVEL=DEBUG
print(f"Agno debug_level: {debug_level}") # Should be 2 if LOG_LEVEL=DEBUG
```

## Best Practices

### Development

1. **Use DEBUG level** during development:
   ```bash
   export LOG_LEVEL=DEBUG
   ```

2. **Use structured logging** for parsing:
   ```python
   logging.basicConfig(
       level=logging.DEBUG,
       format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
   )
   ```

3. **Filter verbose logs** if needed:
   ```python
   # Disable Agno's verbose tool logging
   logging.getLogger('agno.tools').setLevel(logging.WARNING)
   ```

### Production

1. **Use INFO level** for audit logs:
   ```bash
   export LOG_LEVEL=INFO
   ```

2. **Pipe to log aggregation** (DataDog, Splunk, CloudWatch):
   ```bash
   python app.py 2>&1 | logger -t dcaf-app
   ```

3. **Rotate logs** to prevent disk space issues:
   ```python
   from logging.handlers import RotatingFileHandler

   handler = RotatingFileHandler(
       'dcaf.log',
       maxBytes=10_000_000,  # 10MB
       backupCount=5
   )
   logging.getLogger().addHandler(handler)
   ```

4. **Sanitize sensitive data** if needed:
   ```python
   import logging
   import re

   class SanitizingFilter(logging.Filter):
       def filter(self, record):
           # Redact API keys, tokens, etc.
           record.msg = re.sub(r'(api[_-]?key["\s:]+)[^"]+', r'\1***REDACTED***', record.msg)
           return True

   logging.getLogger().addFilter(SanitizingFilter())
   ```

### Compliance & Security

1. **Be aware of PII in logs:**
   - User messages may contain sensitive information
   - System prompts may contain proprietary instructions
   - Consider GDPR/privacy regulations

2. **Use appropriate retention policies:**
   - Delete old logs after X days
   - Encrypt logs at rest
   - Restrict access to log files

3. **Monitor log volume:**
   - DEBUG level can generate significant data
   - Estimate: ~10-50KB per LLM call at DEBUG level
   - Use INFO level in production to reduce volume

## Troubleshooting

### Logs Not Appearing

**Problem:** No logs are showing up

**Solutions:**

1. Check root logger level:
   ```python
   print(logging.getLogger().level)  # Should be <= 20 for INFO
   ```

2. Ensure handlers are configured:
   ```python
   logging.basicConfig(level=logging.INFO)  # Sets up default handler
   ```

3. Check if loggers are disabled:
   ```python
   logger = logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock')
   print(logger.disabled)  # Should be False
   ```

### Too Much Output

**Problem:** Logs are overwhelming

**Solutions:**

1. Increase log level:
   ```bash
   export LOG_LEVEL=WARNING  # Only show warnings and errors
   ```

2. Disable specific loggers:
   ```python
   logging.getLogger('agno').setLevel(logging.WARNING)
   ```

3. Filter streaming chunk logs:
   ```python
   class NoStreamChunkFilter(logging.Filter):
       def filter(self, record):
           return 'Stream chunk #' not in record.getMessage()

   logging.getLogger('dcaf.core.adapters.outbound.agno.caching_bedrock').addFilter(NoStreamChunkFilter())
   ```

### Agno Debug Not Working

**Problem:** Agno debug logs not appearing even at DEBUG level

**Solutions:**

1. Verify `_sync_agno_log_level()` was called:
   - It's called automatically in `AgnoAdapter.__init__()`
   - Check logs for "Agno debug mode enabled"

2. Check Agno's global state:
   ```python
   from agno.utils.log import debug_on, debug_level
   print(f"debug_on={debug_on}, debug_level={debug_level}")
   ```

3. Manually enable if needed:
   ```python
   from agno.utils.log import set_log_level_to_debug
   set_log_level_to_debug(level=2)
   ```

## Related Documentation

- [raw-llm-logging.md](./raw-llm-logging.md) - User guide for enabling and using raw LLM logging
- [prompt-caching.md](./prompt-caching.md) - How DCAF's prompt caching works
- [examples/raw_llm_logging_example.py](../examples/raw_llm_logging_example.py) - Working examples

## Future Enhancements

Potential improvements for the logging system:

- [ ] Structured logging (JSON format) for easier parsing
- [ ] Sanitization hooks to automatically redact sensitive data
- [ ] Token cost calculation in logs (based on model pricing)
- [ ] Integration with observability platforms (DataDog, Splunk)
- [ ] Log filtering by conversation session or tenant
- [ ] Automatic log rotation and compression
- [ ] Performance metrics (latency, throughput)
- [ ] Configurable log levels per layer (via environment variables)
