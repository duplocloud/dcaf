"""NATS JetStream implementation of the DCAF job queue."""

import asyncio
import json
import logging

from .interface import JobQueue
from .models import JobEvent, JobRequest, JobStatus

logger = logging.getLogger(__name__)

# ─── NATS stream / subject constants ────────────────────────────────────────

#: Jobs-in stream — published by dcaf server, consumed by agent workers.
JOBS_IN_STREAM = "DCAF_JOBS_IN"
#: Jobs-out stream — published by agent workers, consumed by dcaf server.
JOBS_OUT_STREAM = "DCAF_JOBS_OUT"

JOBS_IN_SUBJECT_PATTERN = "dcaf.jobs.in.>"
JOBS_OUT_SUBJECT_PATTERN = "dcaf.jobs.out.>"


def jobs_in_subject(agent_name: str) -> str:
    """Return the per-agent input subject: ``dcaf.jobs.in.<agent_name>``."""
    return f"dcaf.jobs.in.{agent_name}"


def jobs_out_subject(job_id: str) -> str:
    """Return the per-job output subject: ``dcaf.jobs.out.<job_id>``."""
    return f"dcaf.jobs.out.{job_id}"


# ─── NatsJobQueue ─────────────────────────────────────────────────────────────


class NatsJobQueue(JobQueue):
    """NATS JetStream-backed job queue for DCAF.

    Lifecycle
    ---------
    Call ``await queue.connect()`` on application startup and
    ``await queue.close()`` on shutdown.  The :func:`create_app` helper
    in ``dcaf.core.server`` handles this automatically when
    ``queue_nats_url`` is passed.

    Job events published by agent workers to
    ``dcaf.jobs.out.<job_id>`` are buffered in memory so that the
    ``/api/jobs/{job_id}/events`` endpoint can serve them without
    additional NATS round-trips.

    Notes
    -----
    The in-memory event buffer is lost on process restart.  For
    production deployments consider replacing ``self._events`` and
    ``self._status`` with a persistent backend (e.g. NATS KV / Redis).
    """

    def __init__(self, nats_url: str, agent_name: str) -> None:
        self._url = nats_url
        self._agent_name = agent_name
        self._nc = None
        self._js = None
        self._status: dict[str, JobStatus] = {}
        self._events: dict[str, list[JobEvent]] = {}
        self._listener_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to NATS and start the background event listener."""
        import nats  # optional dep — imported lazily

        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()
        await self._ensure_streams()
        self._listener_task = asyncio.create_task(self._listen_events())
        logger.info("NatsJobQueue connected to %s", self._url)

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._nc:
            await self._nc.close()
        logger.info("NatsJobQueue closed")

    # ── stream provisioning ──────────────────────────────────────────────────

    async def _ensure_streams(self) -> None:
        """Create DCAF_JOBS_IN and DCAF_JOBS_OUT streams if absent."""
        import nats.js.errors
        from nats.js.api import RetentionPolicy, StorageType, StreamConfig

        _7_days_ns = 7 * 24 * 3600 * 1_000_000_000  # nanoseconds

        specs = [
            StreamConfig(
                name=JOBS_IN_STREAM,
                subjects=[JOBS_IN_SUBJECT_PATTERN],
                retention=RetentionPolicy.WORK_QUEUE,  # workers ack to remove
                storage=StorageType.FILE,
                max_age=_7_days_ns,
            ),
            StreamConfig(
                name=JOBS_OUT_STREAM,
                subjects=[JOBS_OUT_SUBJECT_PATTERN],
                retention=RetentionPolicy.LIMITS,  # keep all events
                storage=StorageType.FILE,
                max_age=_7_days_ns,
            ),
        ]
        for cfg in specs:
            try:
                await self._js.find_stream(cfg.name)  # type: ignore[union-attr]
                logger.debug("NATS stream %s already exists", cfg.name)
            except nats.js.errors.NotFoundError:
                await self._js.add_stream(cfg)  # type: ignore[union-attr]
                logger.info("Created NATS stream %s", cfg.name)

    # ── enqueue ───────────────────────────────────────────────────────────────

    async def enqueue(self, request: JobRequest) -> str:
        """Publish request to DCAF_JOBS_IN and record status as queued."""
        subject = jobs_in_subject(request.agent_name)
        payload = request.model_dump_json().encode()
        await self._js.publish(subject, payload)  # type: ignore[union-attr]
        self._status[request.job_id] = JobStatus(
            job_id=request.job_id,
            status="queued",
            agent_name=request.agent_name,
            created_at=request.created_at,
        )
        logger.info("Enqueued job %s → %s", request.job_id, subject)
        return request.job_id

    # ── read ──────────────────────────────────────────────────────────────────

    async def get_status(self, job_id: str) -> JobStatus | None:
        return self._status.get(job_id)

    async def get_events(self, job_id: str, after: int = 0) -> list[JobEvent]:
        all_events = self._events.get(job_id, [])
        return all_events[after:]

    # ── background listener ───────────────────────────────────────────────────

    async def _listen_events(self) -> None:
        """Subscribe to dcaf.jobs.out.> and buffer events in memory."""
        import nats.errors

        # Durable consumer so dcaf server can resume after restart
        sub = await self._js.subscribe(  # type: ignore[union-attr]
            JOBS_OUT_SUBJECT_PATTERN,
            durable="dcaf-server",
        )
        logger.info("NatsJobQueue listening on %s", JOBS_OUT_SUBJECT_PATTERN)
        while True:
            try:
                msg = await sub.next_msg(timeout=1.0)
                await self._handle_event_msg(msg)
            except nats.errors.TimeoutError:
                continue
            except asyncio.CancelledError:
                await sub.unsubscribe()
                break
            except Exception:
                logger.exception("Error in NatsJobQueue event listener")
                await asyncio.sleep(1)

    async def _handle_event_msg(self, msg: object) -> None:  # type: ignore[type-arg]
        try:
            data = json.loads(msg.data)  # type: ignore[attr-defined]
            event = JobEvent(**data)
            job_id = event.job_id
            bucket = self._events.setdefault(job_id, [])
            event.seq = len(bucket)
            bucket.append(event)
            # Mirror status transitions emitted by the worker
            if event.event_type == "status" and event.data and job_id in self._status:
                new_status = event.data.get("status")
                if new_status:
                    self._status[job_id].status = new_status  # type: ignore[assignment]
                    self._status[job_id].updated_at = event.timestamp
                    if new_status == "failed":
                        self._status[job_id].error = event.data.get("error")
        except Exception:
            logger.exception("Failed to parse job event")
        finally:
            await msg.ack()  # type: ignore[attr-defined]
