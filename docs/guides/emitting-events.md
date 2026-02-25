# Emitting Events from Agent Code

DCAF provides two functions for pushing stream events to the client UI from
anywhere in your agent code — tools, event handlers, or interceptors.

| Function | What it does |
|---|---|
| `emit_update(text, content={})` | Send a transient status message — the common case |
| `emit(event)` | Send any stream event type — the general form |

`emit_update` is the starting point for most use cases. `emit` unlocks the
full power when you need to send different event types.

---

## The Mental Model

The DCAF stream is a **typed message channel**. Every event the client receives
— `text_delta`, `intermittent_update`, `tool_calls`, `done` — is a JSON object
where the `type` field tells the UI how to handle it.

`emit_update()` and `emit()` are mechanisms to push messages into that channel
from anywhere in your code while a stream is active.

```
tool code ──────┐
interceptor ────┼──► emit_update() / emit() ──► stream ──► client UI
@agent.on() ────┘
```

---

## `emit_update()` — The Simple Case

```python
from dcaf.core import emit_update
```

```python
def emit_update(text: str, content: dict | None = None) -> None: ...
```

Send a transient status message to the UI. The UI shows it while the agent
is working, then clears it when new content arrives.

**This is exactly equivalent to:**

```python
from dcaf.core import emit
from dcaf.core.schemas.events import IntermittentUpdateEvent

emit(IntermittentUpdateEvent(text=text, content=content or {}))
```

Use `emit_update` when you just need to show status text. Use `emit` directly
when you need to send a different event type (see [The General Form](#emit-the-general-form)).

### Basic Usage

```python
from dcaf.core import emit_update, tool

@tool(description="Search the web for information")
def web_search(query: str) -> str:
    emit_update(f"Searching for: {query}")
    results = _do_search(query)
    return format_results(results)
```

The client sees:
```json
{"type": "intermittent_update", "text": "Searching for: kubernetes pods", "content": {}}
```

### With Structured Content

The optional `content` dict carries structured metadata the client UI can
use to display richer information — links found, file names, step counts, etc.

```python
@tool(description="Search the web")
def web_search(query: str) -> str:
    emit_update(f"Searching for: {query}")
    results = _do_search(query)

    emit_update(
        text=f"Found {len(results)} results",
        content={
            "count": len(results),
            "sources": [r["url"] for r in results],
        },
    )
    return format_results(results)
```

The second event the client receives:
```json
{
    "type": "intermittent_update",
    "text": "Found 8 results",
    "content": {
        "count": 8,
        "sources": ["https://kubernetes.io/...", "https://docs.aws.amazon.com/..."]
    }
}
```

### Multi-Step Progress

Show progress through a sequence of phases:

```python
@tool(description="Run a full data pipeline")
def run_pipeline(dataset: str) -> str:
    steps = [
        ("Loading data",    load),
        ("Cleaning",        clean),
        ("Analyzing",       analyze),
        ("Building report", build_report),
    ]
    result = dataset
    for i, (label, fn) in enumerate(steps, start=1):
        emit_update(
            text=f"{label}...",
            content={"step": i, "total": len(steps)},
        )
        result = fn(result)

    emit_update("Pipeline complete", content={"steps": len(steps)})
    return result
```

### Before-and-After Pattern

Show a "started" message, do the work, then a "done" message:

```python
@tool(description="Generate a Python script")
def generate_script(description: str) -> str:
    emit_update("Generating script...")

    code = _llm_generate(description)

    emit_update(
        text="Script ready",
        content={"lines": len(code.splitlines())},
    )
    return code
```

---

## `emit()` — The General Form

```python
from dcaf.core import emit
```

```python
def emit(event: StreamEvent) -> None: ...
```

`emit()` accepts any `StreamEvent` subclass. Use it when `emit_update` is not
enough — for example, to stream content directly into the response body.

### Relationship to `emit_update`

These two statements are **identical**:

```python
# Simple form
emit_update("Generating script...")

# Equivalent general form
from dcaf.core.schemas.events import IntermittentUpdateEvent
emit(IntermittentUpdateEvent(text="Generating script..."))
```

And with content:

```python
# Simple form
emit_update("Search complete", content={"count": 8})

# Equivalent general form
emit(IntermittentUpdateEvent(text="Search complete", content={"count": 8}))
```

### Streaming Content into the Response

Use `TextDeltaEvent` to push text directly into the response body from tool
code. This is useful when a tool generates content you want the user to see
immediately — before the LLM summarizes the tool result.

```python
from dcaf.core import emit, tool
from dcaf.core.schemas.events import IntermittentUpdateEvent, TextDeltaEvent

@tool(description="Generate a Python script")
def generate_script(description: str) -> str:
    emit(IntermittentUpdateEvent(text="Generating script..."))

    code = _llm_generate(description)

    # Stream the generated code directly into the response body
    emit(TextDeltaEvent(text=f"\n```python\n{code}\n```\n"))

    # The return value becomes the tool result for the LLM's context
    return code
```

!!! note "text_delta vs intermittent_update"
    `TextDeltaEvent` text is **accumulated** by clients into the displayed
    response — it becomes part of the conversation content.
    `IntermittentUpdateEvent` is **transient** — clients show it while work
    is in progress and clear it when the next content arrives.
    Choose based on whether you want the output to persist in the response.

---

## Use Cases by Location

Both functions work from any of these call sites within an active stream:

### From a `@tool` Function

```python
from dcaf.core import emit_update, tool

@tool(description="Fetch and summarize a web page")
def fetch_page(url: str) -> str:
    emit_update(f"Fetching {url}...")
    html = requests.get(url).text

    emit_update("Summarizing content...")
    return summarize(html)
```

### From an `@agent.on()` Handler

Apply cross-cutting updates to every tool without modifying individual
tool functions:

```python
from dcaf.core import Agent, emit_update, TOOL_CALL_STARTED, TOOL_CALL_COMPLETED

agent = Agent(tools=[...])

@agent.on(TOOL_CALL_STARTED)
async def on_tool_start(event):
    emit_update(
        text=f"Running {event.tool_name}...",
        content={"tool": event.tool_name},
    )

@agent.on(TOOL_CALL_COMPLETED)
async def on_tool_done(event):
    emit_update(
        text=f"{event.tool_name} complete",
        content={"tool": event.tool_name},
    )
```

### From an Interceptor

Interceptors run before the LLM call, so events emitted here appear at the
very start of the stream:

```python
from dcaf.core import LLMRequest, emit_update

def add_tenant_context(request: LLMRequest) -> LLMRequest:
    tenant = request.context.get("tenant_name", "default")
    emit_update(
        text=f"Loading context for: {tenant}",
        content={"tenant": tenant},
    )
    request.add_system_context(f"Tenant: {tenant}")
    return request

agent = Agent(tools=[...], request_interceptors=[add_tenant_context])
```

### From a Helper Function

Both functions work in any nested helper — no need to pass an emitter through
your call stack:

```python
def _fetch_with_retry(url: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        emit_update(
            text=f"Fetching {url} (attempt {attempt}/{retries})",
            content={"url": url, "attempt": attempt},
        )
        try:
            return requests.get(url, timeout=10).text
        except requests.Timeout:
            if attempt == retries:
                raise

@tool(description="Fetch page with retries")
def fetch_page(url: str) -> str:
    content = _fetch_with_retry(url)
    return summarize(content)
```

---

## Safe Outside Streaming

Both functions are always safe to call — they are no-ops when no stream is active:

```python
@tool(description="Analyze data")
def analyze(data: str) -> str:
    emit_update("Analyzing...")  # no-op when called via agent.run()
    return _analyze(data)

# Works in both contexts — no guards needed:
result = agent.run(messages=[...])        # emit_update() is a no-op
async for e in agent.run_stream(msgs):    # emit_update() sends to stream
    ...
```

---

## Testing

When testing tools in isolation, both functions are no-ops since there is no
active stream. To assert on emitted events in tests, activate the queue manually:

```python
from collections import deque
from dcaf.core._context import _active_queue
from dcaf.core.schemas.events import IntermittentUpdateEvent

def test_tool_emits_status():
    queue = deque()
    token = _active_queue.set(queue)
    try:
        result = web_search("kubernetes pods")
    finally:
        _active_queue.reset(token)

    updates = [e for e in queue if isinstance(e, IntermittentUpdateEvent)]
    assert updates[0].text == "Searching for: kubernetes pods"
    assert updates[1].text == "Search complete"
    assert updates[1].content["count"] > 0
```

---

## Complete Example

An agent that uses all three emit locations — tool, event handler, and interceptor:

```python
from dcaf.core import (
    Agent, serve, tool,
    emit, emit_update,
    LLMRequest,
    TOOL_CALL_STARTED,
)
from dcaf.core.schemas.events import TextDeltaEvent

# ── Interceptor ────────────────────────────────────────────────────────────
def add_tenant_context(request: LLMRequest) -> LLMRequest:
    tenant = request.context.get("tenant_name", "default")
    emit_update(f"Loading context for: {tenant}", content={"tenant": tenant})
    request.add_system_context(f"Tenant: {tenant}")
    return request


# ── Tools ──────────────────────────────────────────────────────────────────
@tool(description="Search Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    emit_update(f"Querying namespace: {namespace}", content={"namespace": namespace})
    output = kubectl(f"get pods -n {namespace}")
    emit_update("Query complete", content={"lines": len(output.splitlines())})
    return output


@tool(description="Generate a kubectl command")
def generate_command(description: str) -> str:
    emit_update("Generating command...")
    cmd = _generate_cmd(description)

    # Stream the generated command directly so the user sees it immediately
    emit(TextDeltaEvent(text=f"\n```bash\n{cmd}\n```\n"))
    return cmd


# ── Agent setup ────────────────────────────────────────────────────────────
agent = Agent(
    tools=[list_pods, generate_command],
    request_interceptors=[add_tenant_context],
)


# ── Cross-cutting update for every tool ───────────────────────────────────
@agent.on(TOOL_CALL_STARTED)
async def log_tool_start(event):
    emit_update(
        text=f"▶ {event.tool_name}",
        content={"tool": event.tool_name},
    )


serve(agent)
```

---

## Quick Reference

| Goal | Use |
|---|---|
| Show a status message | `emit_update("Searching...")` |
| Show status with metadata | `emit_update("Found 8 results", content={"count": 8})` |
| Stream content into response body | `emit(TextDeltaEvent(text="..."))` |
| Send an `IntermittentUpdateEvent` explicitly | `emit(IntermittentUpdateEvent(text="..."))` |

---

## See Also

- [Streaming Responses](./streaming.md) — full event type reference and client examples
- [Building Tools](./building-tools.md) — `@tool` decorator reference
- [Interceptors](./interceptors.md) — request/response pipeline
- [Event Subscriptions](./event-subscriptions.md) — `@agent.on()` reference
