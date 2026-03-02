"""DCAF async job queue — NATS JetStream backbone.

Usage (server side)
-------------------
Pass ``queue_nats_url`` and ``queue_agent_name`` to :func:`dcaf.core.serve`
or :func:`dcaf.core.create_app`.  When a client sends a request with
``"queue": true``, the server publishes a
:class:`~dcaf.core.queue.models.JobRequest` to NATS and returns
``{"job_id": "...", "status": "queued"}`` immediately.

Workers subscribe to ``dcaf.jobs.in.<agent_name>.start`` via
:meth:`~dcaf.core.queue.NatsJobQueue.subscribe_jobs`, run the job, and emit
progress via :meth:`~dcaf.core.queue.NatsJobQueue.emit_event`.  The events are
buffered in memory and served by the HTTP queue router.

Usage (worker side)
-------------------
::

    from dcaf.core.queue.nats_js import NatsJobQueue

    queue = NatsJobQueue(nats_url=..., agent_name="my-agent")
    await queue.connect()

    async def handle(request, handle):
        ...
        await handle.ack()

    await queue.subscribe_jobs(handle, stop_event=stop)

Subject naming
--------------
Subjects embed the agent name so each agent has a fully isolated channel
within the shared NATS stream:

- ``dcaf.jobs.in.<agent_name>.start`` — job request (publisher: dcaf server)

Stream names
------------
- ``DCAF_JOBS_IN`` — work queue, retention=WORK_QUEUE (acked messages removed)

Events
------
Workers emit events via :meth:`~NatsJobQueue.emit_event`.  Events are buffered
in memory and exposed over HTTP via the queue router
(``GET /api/jobs/{job_id}/events`` and ``GET /api/jobs/{job_id}/events/stream``).
"""

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
    "create_queue_router",
]

# NatsJobQueue is an optional dependency (requires nats-py).
# Import lazily so that dcaf can be imported without nats-py installed.
try:
    from .nats_js import NatsJobQueue, jobs_in_subject
except ImportError:
    pass  # nats-py not installed; use `pip install dcaf[queue]`
