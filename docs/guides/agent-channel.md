# Agent Channel & Worker (NATS JetStream)

`AgentChannel` and `AgentWorker` provide a two-stream NATS JetStream backbone
for agents that communicate with an external system (e.g. DuploCloud HelpDesk)
without going through HTTP.  Neither side talks to the other directly — both
communicate through persistent NATS streams.

---

## When to use this

Use `AgentChannel` / `AgentWorker` when:

- The external client (HelpDesk, CLI, UI) connects **directly to NATS** and is
  not a Python process (e.g. a .NET service).
- Tasks are long-running and the client needs progress events in real time.
- You want concurrency control, graceful shutdown, and heartbeat keep-alive
  without writing boilerplate.

For same-process HTTP-fronted workers, see the
[Async Job Queue guide](async-job-queue.md) (`NatsJobQueue`) instead.

---

## Requirements

```bash
pip install dcaf[queue]
```

A running NATS server with JetStream enabled:

```bash
docker run -p 4222:4222 nats:2.10 -js
```

---

## Stream topology

```
External system (HelpDesk / CLI)
  │  publishes task/answer/checkpoint messages
  ▼
DCAF_CHANNEL_IN   (dcaf.channel.in.<agent_name>)
  │  work-queue stream — messages removed after ack
  ▼
Agent worker  ←── subscribes here
  │  processes task, emits progress events
  ▼
DCAF_CHANNEL_OUT  (dcaf.channel.out.<agent_name>.<thread_id>)
  │  limits stream — retained 7 days, 10k msgs/subject
  ▼
External system  ←── subscribes here (its own native NATS client)
```

The agent creates **both streams** on startup.  The external system only needs
the NATS server address and the agreed subject names.

### Subject naming

| Direction | Subject pattern |
|---|---|
| External → Agent | `dcaf.channel.in.<agent_name>` |
| Agent → External | `dcaf.channel.out.<agent_name>.<thread_id>` |

### IN message types

The `type` field in every IN message determines how the agent handles it:

| `type` | Meaning |
|---|---|
| `"task"` | Start a new agent run |
| `"answer"` | User reply to a clarification question (PAUSED run) |
| `"checkpoint_approve"` | Approve a checkpoint gate |
| `"checkpoint_feedback"` | Re-run a checkpoint step with feedback |

---

## Subclassing AgentWorker

Subclass `AgentWorker` and implement `handle_task`.  Everything else —
concurrency control, deduplication, heartbeat, graceful shutdown — is provided
by the base class.

```python
import asyncio
from dcaf.core.queue import AgentWorker, AgentMessageHandle


class MyWorker(AgentWorker):

    async def handle_task(self, msg: dict, handle: AgentMessageHandle) -> None:
        thread_id = msg["thread_id"]

        # Start heartbeat to prevent NATS redelivery during long work
        heartbeat = asyncio.create_task(self.heartbeat_loop(handle))
        try:
            await self.emit(thread_id, "status", message="Starting...")

            # ... do work ...

            await self.emit(thread_id, "complete", message="Done")
            await handle.ack()
        except Exception as exc:
            await self.emit(thread_id, "error", message=str(exc))
            await handle.nak()
        finally:
            heartbeat.cancel()


if __name__ == "__main__":
    asyncio.run(MyWorker("my-agent").run())
```

### Optional handlers

Override any of these if your agent supports the corresponding flow:

```python
async def handle_answer(self, msg: dict, handle: AgentMessageHandle) -> None:
    """Resume a PAUSED run with the user's reply."""
    ...

async def handle_checkpoint_approve(self, msg: dict, handle: AgentMessageHandle) -> None:
    """Resume after a checkpoint gate is approved."""
    ...

async def handle_checkpoint_feedback(self, msg: dict, handle: AgentMessageHandle) -> None:
    """Re-run a checkpoint step with user feedback."""
    ...
```

Unimplemented handlers nak the message and log a warning by default.

---

## Type inference

Some external systems (e.g. HelpDesk) always send `type="task"` regardless of
run state.  Override `resolve_message_type` to reclassify messages before
dispatch:

```python
async def resolve_message_type(self, msg: dict, msg_type: str) -> str:
    if msg_type == "task":
        thread_id = msg.get("thread_id", "")
        run_id = await asyncio.to_thread(self._store.find_by_thread_id, thread_id)
        if run_id:
            run = await asyncio.to_thread(self._store.get, run_id)
            if (run or {}).get("status") == "PAUSED":
                return "answer"
    return msg_type
```

---

## Emitting events

`AgentWorker.emit()` publishes an event to `DCAF_CHANNEL_OUT` for a given
`thread_id`.  The external system's NATS client subscribes to the matching
subject to receive them.

```python
await self.emit(thread_id, "status", message="Running step 3/7")
await self.emit(thread_id, "complete", data={"pr_url": "https://..."})
```

Standard `event_type` values: `"status"`, `"log"`, `"question"`,
`"artifact"`, `"checkpoint"`, `"complete"`, `"error"`.

---

## Concurrency and deduplication

`AgentWorker` enforces:

- **Concurrency limit** — at most `max_concurrent` (default: 3) handlers run
  in parallel.
- **Deduplication** — a second `task` message for the same `thread_id` is
  nak-ed while the first is still active.

```python
worker = MyWorker("my-agent", max_concurrent=5)
```

---

## Graceful shutdown

`AgentWorker.run()` registers SIGTERM and SIGINT handlers.  On signal:

1. The subscribe loop stops accepting new messages.
2. In-flight handlers are given `shutdown_timeout` seconds (default: 300) to
   finish.
3. Any handlers still running after the timeout are cancelled.
4. The NATS connection is drained and closed.

```python
worker = MyWorker("my-agent", shutdown_timeout=120)
```

---

## Heartbeat keep-alive

NATS will redeliver a message if it is not ack-ed within `ack_wait` (1 hour).
For long-running handlers, call `heartbeat_loop` to send periodic
`in_progress()` signals:

```python
heartbeat = asyncio.create_task(self.heartbeat_loop(handle, interval=30))
try:
    ...  # long work
finally:
    heartbeat.cancel()
```

---

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `agent_name` | — | Determines NATS subject names |
| `nats_url` | `$NATS_URL` or `nats://localhost:4222` | NATS server address |
| `max_concurrent` | `3` | Max parallel handlers |
| `shutdown_timeout` | `300` | Seconds to wait for in-flight handlers on shutdown |

---

## Using AgentChannel directly

If you need lower-level access (e.g. to publish from an external system in
Python), use `AgentChannel` directly:

```python
from dcaf.core.queue import AgentChannel

channel = AgentChannel("my-agent")
await channel.connect()

# Publish a task (external system → IN)
await channel.publish({
    "type": "task",
    "thread_id": "thread-123",
    "messages": [{"role": "user", "content": "Add an RDS instance"}],
})

# Emit an event (agent → OUT)
await channel.emit("thread-123", "complete", message="Done")

await channel.close()
```
