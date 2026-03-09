# LLM Layer

The LLM layer provides a unified, provider-agnostic interface for making direct LLM calls. It is the **single source of truth** for model creation and configuration in DCAF.

---

## Overview

The LLM layer sits between callers and the underlying model providers:

```
┌──────────────────┐     ┌──────────────────┐
│  Agent / Agno    │     │  Direct callers   │
│  (orchestration) │     │  (e.g. routing)   │
└────────┬─────────┘     └────────┬──────────┘
         │                        │
         │  get_model()           │  invoke()
         │                        │
         ▼                        ▼
    ┌─────────────────────────────────────┐
    │          LLM Layer                  │
    │  (dcaf.core.llm)                    │
    │                                     │
    │  - Provider detection               │
    │  - Credential resolution            │
    │  - Model instantiation              │
    │  - Direct LLM calls                 │
    └──────────────────┬──────────────────┘
                       │
                       ▼
    ┌─────────────────────────────────────┐
    │       AgnoModelFactory              │
    │  Bedrock│Anthropic│OpenAI│Google│...│
    └─────────────────────────────────────┘
```

**Two consumers, one layer:**

1. **Agent orchestration** — calls `llm.get_model()` to get an Agno model instance for the agent loop.
2. **Direct callers** — call `llm.invoke()` / `llm.ainvoke()` for single-shot LLM calls without agent machinery.

---

## Quick Start

```python
from dcaf.core import LLM, create_llm

# Create from environment variables (DCAF_PROVIDER, DCAF_MODEL, etc.)
llm = create_llm()

# Or with explicit configuration
llm = create_llm(provider="google", model="gemini-2.0-flash")

# Make a direct call (sync)
response = llm.invoke(
    messages=[{"role": "user", "content": "Hello"}],
    system_prompt="You are helpful.",
)
print(response.text)
print(response.tool_calls)
print(response.usage)

# Async call
response = await llm.ainvoke(
    messages=[{"role": "user", "content": "Hello"}],
)
```

---

## API Reference

### `create_llm()`

Factory function that creates an `LLM` instance from environment variables.

```python
def create_llm(
    provider: str | None = None,
    model: str | None = None,
    **overrides,
) -> LLM
```

#### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | `str \| None` | `DCAF_PROVIDER` env var, or `"bedrock"` | Provider name |
| `model` | `str \| None` | `DCAF_MODEL` env var, or provider default | Model identifier |
| `**overrides` | | | Additional kwargs: `temperature`, `max_tokens`, `aws_profile`, `aws_region`, `api_key`, `google_project_id`, `google_location` |

#### Environment Variables

| Variable | Description |
|----------|-------------|
| `DCAF_PROVIDER` | Provider name (`bedrock`, `anthropic`, `openai`, `azure`, `google`, `ollama`) |
| `DCAF_MODEL` | Model identifier |
| `DCAF_TEMPERATURE` | Sampling temperature (0.0–1.0) |
| `DCAF_MAX_TOKENS` | Maximum response tokens |
| `AWS_PROFILE` | AWS profile (for Bedrock) |
| `AWS_REGION` | AWS region (for Bedrock) |
| `ANTHROPIC_API_KEY` | API key (for Anthropic) |
| `OPENAI_API_KEY` | API key (for OpenAI) |
| `GOOGLE_PROJECT_ID` | Project ID (for Google) |

#### Examples

```python
# Everything from environment
llm = create_llm()

# Override provider and model
llm = create_llm(provider="google", model="gemini-2.0-flash")

# Override temperature
llm = create_llm(temperature=0.0, max_tokens=200)

# Bedrock with specific AWS config
llm = create_llm(provider="bedrock", aws_region="us-west-2", aws_profile="prod")
```

---

### `LLM`

The main class for direct LLM interaction.

```python
class LLM:
    def __init__(
        self,
        provider: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        **provider_kwargs,
    )
```

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `model_id` | `str` | The model identifier |
| `provider` | `str` | The provider name (lowercased) |

#### Methods

##### `invoke()` — Synchronous direct call

```python
def invoke(
    self,
    messages: list[dict[str, Any]],
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> LLMResponse
```

Single-shot LLM call. No tool execution loop, no agent orchestration.

```python
response = llm.invoke(
    messages=[{"role": "user", "content": "What is 2+2?"}],
    system_prompt="Answer concisely.",
    max_tokens=100,
    temperature=0.0,
)
print(response.text)  # "4"
```

##### `ainvoke()` — Async direct call

```python
async def ainvoke(
    self,
    messages: list[dict[str, Any]],
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> LLMResponse
```

Same as `invoke()` but async.

```python
response = await llm.ainvoke(
    messages=[{"role": "user", "content": "Hello"}],
)
```

##### `get_model()` — Get underlying Agno model

```python
async def get_model(self) -> Any
```

Returns the Agno model instance (e.g., `AwsBedrock`, `Gemini`). Used by the agent orchestration layer to feed the model into `AgnoAgent`.

```python
model = await llm.get_model()
# Pass to AgnoAgent for full orchestration
```

##### `cleanup()`

```python
async def cleanup(self) -> None
```

Release resources held by the underlying model factory.

---

### `LLMResponse`

Response from a direct LLM call. This is the **base class** for `AgentResponse`.

```python
@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw: ModelResponse | None = field(default=None, repr=False)
```

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str \| None` | The model's text response, or `None` if only tool calls were returned |
| `tool_calls` | `list[dict]` | Normalized tool calls. Each entry has `name` and `input` keys |
| `usage` | `dict[str, int]` | Token usage: `input_tokens`, `output_tokens`, `total_tokens` |
| `raw` | `ModelResponse \| None` | The underlying Agno `ModelResponse` for advanced use |

#### Relationship to AgentResponse

`AgentResponse` extends `LLMResponse`:

```python
@dataclass
class AgentResponse(LLMResponse):
    # Inherits: text, tool_calls, usage, raw
    needs_approval: bool = False
    pending_tools: list[PendingToolCall] = field(default_factory=list)
    conversation_id: str = ""
    is_complete: bool = True
    session: dict[str, Any] = field(default_factory=dict)
```

This means every `AgentResponse` is also an `LLMResponse`, and code that works with `LLMResponse` will also work with `AgentResponse`.

---

## Tool Calling

The LLM layer supports tool calling via the standard tool schema format:

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
                    "description": "City and state",
                }
            },
            "required": ["location"],
        },
    }
]

response = llm.invoke(
    messages=[{"role": "user", "content": "What's the weather in NYC?"}],
    tools=tools,
    tool_choice={"name": "get_weather"},  # Force this tool
)

if response.tool_calls:
    tool_call = response.tool_calls[0]
    print(tool_call["name"])   # "get_weather"
    print(tool_call["input"])  # {"location": "NYC"}
```

---

## Supported Providers

| Provider | `DCAF_PROVIDER` value | Default model |
|----------|----------------------|---------------|
| AWS Bedrock | `bedrock` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` |
| Anthropic | `anthropic` | `claude-sonnet-4-20250514` |
| OpenAI | `openai` | `gpt-4o` |
| Azure OpenAI | `azure` | `gpt-4o` |
| Google Vertex AI | `google` | `gemini-2.0-flash` |
| Ollama | `ollama` | `llama3` |

---

## Usage in Channel Routing

The `SlackResponseRouter` uses the LLM layer for direct calls without any agent overhead:

```python
from dcaf.core.llm import create_llm

llm = create_llm()  # Reads DCAF_PROVIDER, DCAF_MODEL from env

response = llm.invoke(
    messages=[{"role": "user", "content": thread_text}],
    system_prompt=routing_prompt,
    tools=[routing_tool_schema],
    tool_choice={"name": "slack_routing_decision"},
    max_tokens=200,
    temperature=0.0,
)

should_respond = response.tool_calls[0]["input"]["should_respond"]
```

---

## See Also

- [Environment Configuration](../guides/environment-configuration.md) — Full list of env vars
- [Custom Agents](../guides/custom-agents.md) — Agent orchestration layer
- [Channel Routing](../api-reference/channel-routing.md) — SlackResponseRouter usage
- [Working with Bedrock](../guides/working-with-bedrock.md)
- [Working with Google Vertex AI](../guides/working-with-gemini.md)
