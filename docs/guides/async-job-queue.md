# Async Job Queue (NATS JetStream)

The async job queue lets a DCAF server accept requests immediately (returning a
`job_id`) and execute them in the background while clients stream progress via
Server-Sent Events.

---

## When to use it

Long-running agent tasks (e.g. IaC runs, data pipelines) that take more than a
few seconds to complete should use the queue.  Synchronous `/api/chat` blocks
until the agent finishes and is unsuitable for tasks over ~30 s.

---

## Requirements

Install the NATS extra:

```bash
pip install dcaf[queue]
# or, with all extras:
pip install dcaf[all]
```

A running NATS server with JetStream enabled:

```bash
docker run -p 4222:4222 nats:2.10 -js
```

---

## Enabling the queue

There are two ways to attach a queue, depending on whether you need a
background worker in the same process.

### URL-only (no in-process worker)

Pass `queue_nats_url` when you only need the server to enqueue jobs and expose
the SSE endpoint, and workers run out-of-process:

```python
from dcaf.core import Agent, serve

agent = Agent(tools=[...])

serve(
    agent,
    port=8000,
    queue_nats_url="nats://localhost:4222",
    queue_agent_name="my-agent",
)
```

### Shared instance (in-process worker, recommended)

Pass a `NatsJobQueue` instance via `queue=` so the HTTP server and the background
worker share the same in-memory event buffer:

```python
from dcaf.core import Agent, create_app
from dcaf.core.queue.nats_js import NatsJobQueue

queue = NatsJobQueue(nats_url="nats://localhost:4222", agent_name="my-agent")
agent = Agent(tools=[...])
app = create_app(agent, queue=queue)
```

See [Wiring a worker in the same process](#wiring-a-worker-in-the-same-process)
for the full lifespan example.

---

## Wiring a worker in the same process

The SSE endpoint reads from an **in-memory buffer** that is only populated when
the worker and HTTP server share the **same** `NatsJobQueue` instance.  Pass
the instance directly to `create_app()` using the `queue=` parameter:

```python
import asyncio
import contextlib

from dcaf.core import Agent, create_app
from dcaf.core.queue.nats_js import NatsJobQueue
from dcaf.core.queue.models import JobRequest, JobMessageHandle


async def my_handler(job: JobRequest, handle: JobMessageHandle) -> None:
    await handle.ack()
    # ... run agent logic, emit events via queue.emit_event(...)


@contextlib.asynccontextmanager
async def lifespan(app):
    await queue.connect()
    task = asyncio.create_task(queue.subscribe_jobs(my_handler))
    yield
    task.cancel()
    await queue.close()


# One instance shared between the HTTP server and the background worker.
queue = NatsJobQueue(nats_url="nats://localhost:4222", agent_name="my-agent")
agent = Agent(tools=[...])
app = create_app(agent, queue=queue)   # same instance — not queue_nats_url
app.router.lifespan_context = lifespan
```

> **Important**: passing `queue_nats_url=` instead of `queue=` creates a second
> internal instance.  That instance's `_events` buffer will never be populated
> by the worker, so the SSE endpoint will always return empty.  Always use
> `queue=` when wiring a background worker in the same process.
>
> For multi-process deployments replace the in-memory buffer with a persistent
> backend (e.g. NATS KV, Redis).

---

## Submitting a job

Add `"queue": true` to any `/api/chat` request body:

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "queue": true,
    "messages": [{"role": "user", "content": "Run my long task"}]
  }'
```

Response:

```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000", "status": "queued"}
```

---

## Streaming events (SSE)

Open an SSE connection using the `job_id` from the submit response:

```bash
curl -N http://localhost:8000/api/jobs/550e8400-e29b-41d4-a716-446655440000/events/stream
```

Each event is a JSON object on a `data:` line:

```
id: 0
data: {"job_id": "550e...", "event_type": "status", "data": {"status": "running"}, "seq": 0}

id: 1
data: {"job_id": "550e...", "event_type": "log", "data": {"message": "Step 1 done"}, "seq": 1}

id: 2
data: {"job_id": "550e...", "event_type": "done", "data": {}, "seq": 2}
```

The stream closes automatically after a terminal event (`done` or `error`).

### Resuming after disconnect

Pass `?after=N` (or send a `Last-Event-ID` header) to skip events already
received:

```bash
curl -N "http://localhost:8000/api/jobs/<job_id>/events/stream?after=5"
```

---

## Emitting events from a worker

Call `queue.emit_event()` inside your handler to push progress to clients:

```python
from dcaf.core.queue.models import JobEvent

await queue.emit_event(JobEvent(
    job_id=job.job_id,
    event_type="log",
    data={"message": "Cloning repository…"},
))

await queue.emit_event(JobEvent(
    job_id=job.job_id,
    event_type="done",
    data={},
))
```

---

## NATS streams created automatically

| Stream | Retention | Subject pattern | Purpose |
|---|---|---|---|
| `DCAF_JOBS_IN` | WORK_QUEUE | `dcaf.jobs.in.>` | Deliver jobs to workers |
| `DCAF_JOBS_OUT` | LIMITS (7 days) | `dcaf.jobs.out.>` | Persist emitted events |

Both streams are created on first `queue.connect()` if they do not already exist.
