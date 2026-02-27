"""DCAF async job queue — NATS JetStream backbone.

Usage (server side)
-------------------
Pass ``queue_nats_url`` and ``queue_agent_name`` to :func:`dcaf.core.serve`
or :func:`dcaf.core.create_app`.  When a client sends a request with
``"queue": true``, the server publishes a
:class:`~dcaf.core.queue.models.JobRequest` to NATS and returns
``{"job_id": "...", "status": "queued"}`` immediately.

The worker then subscribes to ``dcaf.jobs.in.<agent_name>``, runs the job,
and publishes :class:`~dcaf.core.queue.models.JobEvent` messages to
``dcaf.jobs.out.<job_id>``.  The server's background listener buffers
these events so clients can poll ``GET /api/jobs/{job_id}/events``.

Usage (worker side)
-------------------
::

    from dcaf.core.queue.nats_js import NatsJobQueue, jobs_in_subject, jobs_out_subject

    queue = NatsJobQueue(nats_url=..., agent_name="my-agent")
    await queue.connect()

    # Subscribe and process jobs
    async for request in worker.subscribe():
        ...

Subject naming
--------------
Subjects embed the agent name so each agent has a fully isolated channel
within the shared NATS streams:

- ``dcaf.jobs.in.<agent_name>.start``    — job request  (publisher: dcaf server)
- ``dcaf.jobs.in.<agent_name>.answers``  — answers to a paused job (iac-ai-agent)
- ``dcaf.jobs.out.<agent_name>.<job_id>`` — job event   (publisher: agent worker)

HelpDesk subscribes to ``dcaf.jobs.out.<agent_name>.>`` to receive only one
agent's events and SSE them to the browser.

Stream names
------------
- ``DCAF_JOBS_IN``  — work queue, retention=WORK_QUEUE
- ``DCAF_JOBS_OUT`` — event log,  retention=LIMITS (7-day TTL)
"""

from .interface import JobQueue
from .models import JobEvent, JobRequest, JobStatus
from .router import create_queue_router

__all__ = [
    "JobQueue",
    "JobRequest",
    "JobStatus",
    "JobEvent",
    "NatsJobQueue",
    "jobs_in_subject",
    "jobs_out_subject",
    "create_queue_router",
]

# NatsJobQueue is an optional dependency (requires nats-py).
# Import lazily so that dcaf can be imported without nats-py installed.
try:
    from .nats_js import NatsJobQueue, jobs_in_subject, jobs_out_subject
except ImportError:
    pass  # nats-py not installed; use `pip install dcaf[queue]`
