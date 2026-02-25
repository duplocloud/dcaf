# Emitting Events from Agent Code

DCAF's `emit()` function lets you push any stream event into the active stream from anywhere in your agent code — tools, event handlers, or interceptors. This gives you real-time control over what the client UI sees while your agent is working.

---

## The Core Idea

The DCAF stream is a typed message channel. Every event you see in the client — `text_delta`, `intermittent_update`, `tool_calls`, `done` — is a JSON object that the UI reads to decide what to render. The `type` field is the discriminator.

`emit()` is nothing more than **"push a typed message into that channel from wherever you are in the code"**.

```
tool code ─────┐
interceptor ───┼──► emit(event) ──► stream ──► client UI
@agent.on() ───┘
```

This means you can send any event type — not just status messages — from deep within your tool logic or event handlers.

---

## Quick Start

```python
from dcaf.core import Agent, emit, tool
from dcaf.core.schemas.events import IntermittentUpdateEvent

@tool(description="Search the web for information")
def web_search(query: str) -> str:
    emit(IntermittentUpdateEvent(text=f"Searching for: {query}"))
    results = _do_search(query)
    return format_results(results)

agent = Agent(tools=[web_search])
```

---

## The `emit()` Function

```python
from dcaf.core import emit
```

```python
def emit(event: StreamEvent) -> None: ...
```

**Behavior:**

- Queues the event for delivery before the next framework-generated event in the same stream turn
- **No-op** when called outside an active `run_stream()` invocation — safe to call from code that also runs in non-streaming contexts
- Thread-safe: works correctly when tools run in a thread pool executor

---

## Use Cases by Location

### 1. From a `@tool` Function

The most common use case. Emit status messages before and after long-running work.

```python
from dcaf.core import emit, tool
from dcaf.core.schemas.events import IntermittentUpdateEvent

@tool(description="Fetch and summarize a web page")
def fetch_page(url: str) -> str:
    emit(IntermittentUpdateEvent(text=f"Fetching {url}..."))
    html = requests.get(url).text

    emit(IntermittentUpdateEvent(text="Summarizing content..."))
    summary = summarize(html)

    return summary
```

#### With Structured Content

Use the `content` field to send structured data alongside the status text. The client UI can use this to display richer information — links found, file names, step counts, etc.

```python
@tool(description="Search and return results")
def search(query: str) -> str:
    emit(IntermittentUpdateEvent(text=f"Searching: {query}"))
    results = _search(query)

    emit(IntermittentUpdateEvent(
        text=f"Found {len(results)} results",
        content={
            "count": len(results),
            "sources": [r["url"] for r in results],
        },
    ))
    return format_results(results)
```

#### Streaming Content Directly from a Tool

Tools can emit `TextDeltaEvent` to stream text directly into the response — for example, showing work-in-progress code before the final tool result is returned.

```python
from dcaf.core.schemas.events import IntermittentUpdateEvent, TextDeltaEvent

@tool(description="Generate a Python script")
def generate_script(description: str) -> str:
    emit(IntermittentUpdateEvent(text="Generating script..."))
    code = _llm_generate(description)

    # Stream the WIP code to the UI immediately
    emit(TextDeltaEvent(text=f"\n```python\n{code}\n```\n"))

    # The return value becomes the tool result in the LLM context
    return code
```

!!! note
    `TextDeltaEvent` text is accumulated by clients into the displayed response. Use it
    for content you want visible in the conversation. Use `IntermittentUpdateEvent` for
    transient status that the UI should show and then clear.

#### Multi-Step Progress

Long-running tools with multiple phases can emit a sequence of updates:

```python
@tool(description="Run a full data pipeline")
def run_pipeline(dataset: str) -> str:
    steps = [
        ("Loading data", load_data),
        ("Cleaning", clean),
        ("Running analysis", analyze),
        ("Building report", build_report),
    ]
    result = dataset
    for label, fn in steps:
        emit(IntermittentUpdateEvent(text=label + "..."))
        result = fn(result)

    emit(IntermittentUpdateEvent(text="Pipeline complete"))
    return result
```

---

### 2. From an `@agent.on()` Event Handler

The existing event subscription system fires internal events during agent execution. You can combine it with `emit()` to translate internal events into client-visible stream events.

```python
from dcaf.core import Agent, emit, TOOL_CALL_STARTED, TOOL_CALL_COMPLETED
from dcaf.core.schemas.events import IntermittentUpdateEvent

agent = Agent(tools=[...])

@agent.on(TOOL_CALL_STARTED)
async def on_tool_start(event):
    emit(IntermittentUpdateEvent(
        text=f"Running {event.tool_name}...",
        content={"tool": event.tool_name},
    ))

@agent.on(TOOL_CALL_COMPLETED)
async def on_tool_done(event):
    emit(IntermittentUpdateEvent(
        text=f"{event.tool_name} complete",
        content={"tool": event.tool_name, "result": str(event.result)[:200]},
    ))
```

This is useful for **cross-cutting concerns** — you write the update logic once and it applies to every tool, without modifying individual tool functions.

#### Combining with Tool-Level Emits

Tool-level `emit()` calls and `@agent.on()` emits can coexist. The order of delivery depends on when `emit()` is called relative to the internal event that triggers the handler:

```
TOOL_CALL_STARTED fires
  → @agent.on handler emit() → queued
  → tool body runs
      → tool emit() calls → queued
TOOL_CALL_COMPLETED fires
  → @agent.on handler emit() → queued
```

All queued events are delivered before the next framework event.

---

### 3. From an Interceptor

Request and response interceptors run as part of the `run_stream()` call stack, so `emit()` works here too.

```python
from dcaf.core import LLMRequest, emit
from dcaf.core.schemas.events import IntermittentUpdateEvent

def enrich_context(request: LLMRequest) -> LLMRequest:
    tenant = request.context.get("tenant_name", "unknown")

    emit(IntermittentUpdateEvent(
        text=f"Loading context for tenant: {tenant}",
        content={"tenant": tenant},
    ))

    # ... add context to request ...
    return request

agent = Agent(
    tools=[...],
    request_interceptors=[enrich_context],
)
```

!!! warning
    Interceptors run **before the LLM call**, so events emitted here will appear
    at the very start of the stream — before any `text_delta` or tool events.

---

### 4. From a Helper Function

Because `emit()` reads from a `ContextVar`, it works in any function in the call chain — including deeply nested helpers. You don't need to thread an emitter through your call stack.

```python
def _fetch_with_retry(url: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        emit(IntermittentUpdateEvent(
            text=f"Fetching {url} (attempt {attempt}/{retries})",
        ))
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

## What Events Can You Emit?

Any `StreamEvent` subclass. The most useful ones:

| Event | When to use |
|---|---|
| `IntermittentUpdateEvent` | WIP status — "Searching...", "Generating code...", progress steps |
| `TextDeltaEvent` | Stream content directly — WIP code, partial results you want visible in the response |

Events you generally should **not** emit from user code:

| Event | Why to avoid |
|---|---|
| `DoneEvent` | Terminates the stream; framework emits this automatically |
| `ErrorEvent` | Raises an error state; let exceptions propagate naturally |
| `ToolCallsEvent` | Managed by the approval workflow; emitting manually bypasses approval logic |

---

## Event Delivery Ordering

User-emitted events are drained **before each framework-generated event**. The delivery sequence for a typical tool call looks like this:

```
[user emit] IntermittentUpdateEvent("Thinking...")     ← from @agent.on(REASONING_STARTED)
[framework] IntermittentUpdateEvent("Thinking...")     ← system event (auto)
[framework] IntermittentUpdateEvent("Calling tool: X") ← system event (auto)
[user emit] IntermittentUpdateEvent("Fetching URL...")  ← from tool body
[user emit] IntermittentUpdateEvent("Parsing results") ← from tool body
[framework] TextDeltaEvent(...)                        ← LLM response text
[framework] DoneEvent()
```

The interleaving happens naturally: tool code runs synchronously, filling the queue, then the async framework loop drains it before the next event.

---

## Safe Use Outside Streaming

`emit()` is always safe to call, even when no stream is active:

```python
@tool(description="Analyze data")
def analyze(data: str) -> str:
    emit(IntermittentUpdateEvent(text="Analyzing..."))  # no-op if not streaming
    return _analyze(data)

# Works in both contexts:
result = agent.run(messages=[...])        # emit() is a no-op
async for e in agent.run_stream(msgs):    # emit() pushes to stream
    ...
```

This means you don't need to guard `emit()` calls or maintain two versions of your tools.

---

## Testing

When testing tools in isolation, `emit()` is a no-op since there's no active stream. If you want to assert on emitted events in tests, activate a queue manually:

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
```

---

## Complete Example

An agent that uses all three emit locations — tool, event handler, and interceptor:

```python
from dcaf.core import Agent, emit, serve, tool, TOOL_CALL_STARTED
from dcaf.core import LLMRequest
from dcaf.core.schemas.events import IntermittentUpdateEvent, TextDeltaEvent

# ── Interceptor ────────────────────────────────────────────────────────────
def add_tenant_context(request: LLMRequest) -> LLMRequest:
    tenant = request.context.get("tenant_name", "default")
    emit(IntermittentUpdateEvent(
        text=f"Loading context for: {tenant}",
        content={"tenant": tenant},
    ))
    request.add_system_context(f"Tenant: {tenant}")
    return request


# ── Tools ──────────────────────────────────────────────────────────────────
@tool(description="Search Kubernetes pods")
def list_pods(namespace: str = "default") -> str:
    emit(IntermittentUpdateEvent(
        text=f"Querying namespace: {namespace}",
        content={"namespace": namespace},
    ))
    output = kubectl(f"get pods -n {namespace}")

    emit(IntermittentUpdateEvent(
        text="Query complete",
        content={"namespace": namespace, "lines": len(output.splitlines())},
    ))
    return output


@tool(description="Generate a kubectl command")
def generate_command(description: str) -> str:
    emit(IntermittentUpdateEvent(text="Generating command..."))
    cmd = _generate_cmd(description)

    # Stream the generated command directly so the user sees it immediately
    emit(TextDeltaEvent(text=f"\n```bash\n{cmd}\n```\n"))
    return cmd


# ── Agent setup ────────────────────────────────────────────────────────────
agent = Agent(
    tools=[list_pods, generate_command],
    request_interceptors=[add_tenant_context],
)


# ── Cross-cutting event handler ────────────────────────────────────────────
@agent.on(TOOL_CALL_STARTED)
async def log_tool_start(event):
    # Supplemental update from the event system (in addition to tool-level emits)
    emit(IntermittentUpdateEvent(
        text=f"▶ {event.tool_name}",
        content={"tool": event.tool_name, "source": "event_handler"},
    ))


serve(agent)
```

---

## See Also

- [Streaming Responses](./streaming.md) — full event type reference
- [Building Tools](./building-tools.md) — `@tool` decorator reference
- [Interceptors](./interceptors.md) — request/response pipeline
- [Event Subscriptions](./event-subscriptions.md) — `@agent.on()` reference
