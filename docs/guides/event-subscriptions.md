# Event Subscriptions

Subscribe to real-time events during agent execution for UI updates, logging, or triggering side effects.

---

## Quick Start

```python
from dcaf.core import Agent, tool

@tool
def weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Weather in {city}: 72°F, sunny"

agent = Agent(tools=[weather])

@agent.on("tool_call_started")
async def notify_ui(event):
    print(f"🔧 Calling {event.tool_name}...")

@agent.on("text_delta")
async def stream_text(event):
    print(event.text, end="", flush=True)

# Events fire automatically during execution
response = await agent.invoke("What's the weather in NYC?")
```

Output:
```
🔧 Calling weather...
The weather in NYC is 72°F and sunny.
```

---

## How It Works

1. **Declare subscriptions** with `@agent.on("event_type")`
2. **Events fire automatically** during `agent.invoke()` or `agent.stream()`
3. **Only subscribed events are created** (lazy creation for performance)

---

## Available Events

### Tool Events

| Event | Fired When | Data Fields |
|-------|-----------|-------------|
| `tool_call_started` | Tool begins execution | `tool_name`, `tool_call_id`, `arguments` |
| `tool_call_completed` | Tool finishes successfully | `tool_name`, `tool_call_id`, `result` |
| `tool_call_failed` | Tool execution fails | `tool_name`, `tool_call_id`, `error` |

### Streaming Events

| Event | Fired When | Data Fields |
|-------|-----------|-------------|
| `text_delta` | Each chunk of streamed text | `text` |
| `message_start` | New message begins | (empty) |
| `message_end` | Message completes | `response` |

### Reasoning Events (Model-Dependent)

| Event | Fired When | Data Fields |
|-------|-----------|-------------|
| `reasoning_started` | Model begins reasoning | (empty) |
| `reasoning_step` | Each reasoning step | `content` |
| `reasoning_completed` | Reasoning finishes | (empty) |

### Error Events

| Event | Fired When | Data Fields |
|-------|-----------|-------------|
| `error` | Error occurs | `error`, `code` (optional) |

---

## Subscribing to Multiple Events

```python
# Single decorator, multiple events
@agent.on("tool_call_started", "tool_call_completed")
async def handle_tools(event):
    print(f"{event.type}: {event.tool_name}")

# Using an array (your own grouping)
UI_EVENTS = ["tool_call_started", "text_delta", "error"]

@agent.on(*UI_EVENTS)
async def push_to_ui(event):
    await websocket.send(event)
```

---

## The Event Object

```python
from dcaf.core import Event

# Events have these fields:
event.type        # str: "tool_call_started", "text_delta", etc.
event.data        # dict: Event-specific payload
event.timestamp   # datetime: When the event occurred

# Convenience accessors (return None if not present):
event.tool_name   # str | None
event.tool_call_id # str | None
event.text        # str | None
event.content     # str | None (for reasoning steps)
event.error       # str | None
event.result      # Any | None (for tool completions)
```

---

## Using Event Type Constants

For autocomplete and typo prevention:

```python
from dcaf.core import (
    Agent,
    TOOL_CALL_STARTED,
    TOOL_CALL_COMPLETED,
    TEXT_DELTA,
)

agent = Agent(tools=[...])

@agent.on(TOOL_CALL_STARTED, TOOL_CALL_COMPLETED)
async def handle(event):
    ...
```

Or just use strings - they're equivalent:

```python
@agent.on("tool_call_started", "tool_call_completed")
async def handle(event):
    ...
```

---

## Example: SSE Streaming to UI

```python
import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from dcaf.core import Agent, tool

app = FastAPI()

@tool
def search(query: str) -> str:
    """Search the web."""
    return f"Results for: {query}"

agent = Agent(tools=[search])

@app.get("/chat")
async def chat(message: str):
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    @agent.on("tool_call_started")
    async def on_tool(event):
        await queue.put(f"data: {json.dumps({'type': 'tool', 'name': event.tool_name})}\n\n")

    @agent.on("text_delta")
    async def on_text(event):
        await queue.put(f"data: {json.dumps({'type': 'text', 'content': event.text})}\n\n")

    async def run_agent():
        await agent.invoke(message)
        await queue.put(f"data: {json.dumps({'type': 'done'})}\n\n")
        await queue.put(None)  # Signal completion

    async def event_stream():
        task = asyncio.create_task(run_agent())
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
        await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## Performance

Events are created **lazily** - if nobody subscribes to `text_delta`, those events are never created. This means:

- Subscribe only to what you need
- No filtering required in your handlers
- Zero overhead for unsubscribed event types

---

## See Also

- [Streaming Guide](./streaming.md) - NDJSON streaming format
- [Building Tools](./building-tools.md) - Creating tools for agents
