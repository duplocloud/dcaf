"""DCAF async job queue — NATS JetStream backbone.

This package exposes two queue topologies:

AgentChannel / AgentWorker  (recommended for new agents)
---------------------------------------------------------
A two-stream NATS channel between an external system (e.g. HelpDesk) and an
agent worker.  Neither side communicates directly — both talk through
persistent NATS streams:

- External system publishes tasks → ``DCAF_CHANNEL_IN``
- Agent subscribes, processes, and publishes events → ``DCAF_CHANNEL_OUT``
- External system reads events from ``DCAF_CHANNEL_OUT`` using its own client

Subclass :class:`AgentWorker` and implement :meth:`~AgentWorker.handle_task`
to get concurrency control, deduplication, heartbeat keep-alive, and graceful
shutdown for free::

    from dcaf.core.queue import AgentWorker, AgentMessageHandle

    class MyWorker(AgentWorker):
        async def handle_task(self, msg: dict, handle: AgentMessageHandle) -> None:
            heartbeat = asyncio.create_task(self.heartbeat_loop(handle))
            try:
                ...
                await handle.ack()
            finally:
                heartbeat.cancel()

    asyncio.run(MyWorker("my-agent").run())

NatsJobQueue  (HTTP-fronted, same-process workers)
--------------------------------------------------
Pass ``queue_nats_url`` and ``queue_agent_name`` to :func:`dcaf.core.serve`
or :func:`dcaf.core.create_app`.  When a client sends a request with
``"queue": true``, the server publishes a
:class:`~dcaf.core.queue.models.JobRequest` to NATS and returns
``{"job_id": "...", "status": "queued"}`` immediately.

Workers subscribe to ``dcaf.jobs.in.<agent_name>.start`` via
:meth:`~dcaf.core.queue.NatsJobQueue.subscribe_jobs`, run the job, and emit
progress via :meth:`~dcaf.core.queue.NatsJobQueue.emit_event`.  The events are
buffered in memory and served by the HTTP queue router.

Stream names
------------
- ``DCAF_JOBS_IN``      — NatsJobQueue work queue (WORK_QUEUE retention)
- ``DCAF_CHANNEL_IN``   — AgentChannel IN  (WORK_QUEUE, 7d TTL)
- ``DCAF_CHANNEL_OUT``  — AgentChannel OUT (LIMITS, 7d TTL, 10k msgs/subject)
"""

import contextlib

from .interface import JobMessageHandle, JobQueue, JobRequestHandler
from .models import JobEvent, JobRequest, JobStatus
from .router import create_queue_router

__all__ = [
    "JobQueue",
    "JobMessageHandle",
    "JobRequestHandler",
    "JobRequest",
    "JobStatus",
    "JobEvent",
    "NatsJobQueue",
    "jobs_in_subject",
    "jobs_out_subject",
    "create_queue_router",
    "AgentChannel",
    "AgentEvent",
    "AgentMessageHandle",
    "AgentWorker",
    "channel_in_subject",
    "channel_out_subject",
]

# NatsJobQueue / AgentChannel / AgentWorker are optional dependencies (require nats-py).
# Import lazily so that dcaf can be imported without nats-py installed.
with contextlib.suppress(ImportError):
    from .channel import (  # noqa: F401
        AgentChannel,
        AgentEvent,
        AgentMessageHandle,
        channel_in_subject,
        channel_out_subject,
    )
    from .nats_js import NatsJobQueue, jobs_in_subject, jobs_out_subject  # noqa: F401
    from .worker import AgentWorker  # noqa: F401
