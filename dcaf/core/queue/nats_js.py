"""NATS JetStream implementation of the DCAF job queue."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from .interface import JobMessageHandle, JobQueue, JobRequestHandler
from .models import JobEvent, JobRequest, JobStatus

logger = logging.getLogger(__name__)

# ─── NATS stream / subject constants ────────────────────────────────────────

#: Jobs-in stream — published by dcaf server, consumed by agent workers.
JOBS_IN_STREAM = "DCAF_JOBS_IN"

# Subject pattern that covers ALL agents (used when creating the stream).
# Each agent filters with its own prefix on a durable consumer.
JOBS_IN_SUBJECT_PATTERN = "dcaf.jobs.in.>"


def jobs_in_subject(agent_name: str) -> str:
    """Return the per-agent IN subject for generic job submission.

    Pattern: ``dcaf.jobs.in.<agent_name>.start``

    Workers subscribe to ``dcaf.jobs.in.<agent_name>.start`` to receive job
    requests for their agent only.
    """
    return f"dcaf.jobs.in.{agent_name}.start"


#: Jobs-out stream — published by agent workers, consumed by any subscriber.
JOBS_OUT_STREAM = "DCAF_JOBS_OUT"

# Subject pattern that covers ALL agents on the OUT stream.
JOBS_OUT_SUBJECT_PATTERN = "dcaf.jobs.out.>"


def jobs_out_subject(agent_name: str, job_id: str) -> str:
    """Return the per-job OUT subject.

    Pattern: ``dcaf.jobs.out.<agent_name>.<job_id>``
    """
    return f"dcaf.jobs.out.{agent_name}.{job_id}"


# ─── NatsJobMessageHandle ─────────────────────────────────────────────────────


class NatsJobMessageHandle(JobMessageHandle):
    """Wraps a raw NATS JetStream message as a :class:`JobMessageHandle`."""

    def __init__(self, raw_msg: object) -> None:
        self._msg = raw_msg

    async def ack(self) -> None:
        await self._msg.ack()  # type: ignore[attr-defined]

    async def nak(self) -> None:
        await self._msg.nak()  # type: ignore[attr-defined]

    async def in_progress(self) -> None:
        await self._msg.in_progress()  # type: ignore[attr-defined]


# ─── NatsJobQueue ─────────────────────────────────────────────────────────────


class NatsJobQueue(JobQueue):
    """NATS JetStream-backed job queue for DCAF.

    Lifecycle
    ---------
    Call ``await queue.connect()`` on application startup and
    ``await queue.close()`` on shutdown.  The :func:`create_app` helper
    in ``dcaf.core.server`` handles this automatically when
    ``queue_nats_url`` is passed.

    Architecture
    ------------
    NATS is used for the IN direction only (work distribution).  Events
    emitted by workers are buffered in memory via :meth:`emit_event` and
    served over HTTP by the queue router (``GET /api/jobs/{job_id}/events``
    and the SSE stream).

    Notes
    -----
    The in-memory event buffer is lost on process restart.  For production
    deployments consider replacing ``self._events`` and ``self._status``
    with a persistent backend (e.g. NATS KV / Redis).
    """

    def __init__(self, nats_url: str, agent_name: str) -> None:
        self._url = nats_url
        self._agent_name = agent_name
        self._nc = None
        self._js = None
        self._status: dict[str, JobStatus] = {}
        self._events: dict[str, list[JobEvent]] = {}

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to NATS and ensure both DCAF streams exist."""
        import nats  # optional dep — imported lazily

        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()  # type: ignore[attr-defined]
        await self._ensure_in_stream()
        await self._ensure_out_stream()
        logger.info("NatsJobQueue connected to %s", self._url)

    async def close(self) -> None:
        if self._nc:
            await self._nc.close()
        logger.info("NatsJobQueue closed")

    # ── stream / consumer provisioning ───────────────────────────────────────

    async def _ensure_in_stream(self) -> None:
        """Create DCAF_JOBS_IN stream if it does not already exist."""
        import nats.js.errors
        from nats.js.api import RetentionPolicy, StorageType, StreamConfig

        cfg = StreamConfig(
            name=JOBS_IN_STREAM,
            subjects=[JOBS_IN_SUBJECT_PATTERN],
            retention=RetentionPolicy.WORK_QUEUE,  # workers ack to remove
            storage=StorageType.FILE,
            max_age=7 * 24 * 3600,  # 7 days in seconds (nats-py converts to ns)
        )
        try:
            await self._js.stream_info(JOBS_IN_STREAM)  # type: ignore[attr-defined]
            logger.debug("NATS stream %s already exists", JOBS_IN_STREAM)
        except nats.js.errors.NotFoundError:
            await self._js.add_stream(cfg)  # type: ignore[attr-defined]
            logger.info("Created NATS stream %s", JOBS_IN_STREAM)

    async def _ensure_out_stream(self) -> None:
        """Create DCAF_JOBS_OUT stream if it does not already exist."""
        import nats.js.errors
        from nats.js.api import RetentionPolicy, StorageType, StreamConfig

        cfg = StreamConfig(
            name=JOBS_OUT_STREAM,
            subjects=[JOBS_OUT_SUBJECT_PATTERN],
            retention=RetentionPolicy.LIMITS,  # keep until TTL / cap
            storage=StorageType.FILE,
            max_age=7 * 24 * 3600,  # 7 days in seconds (nats-py converts to ns)
            max_msgs_per_subject=10_000,  # cap per job subject
        )
        try:
            await self._js.stream_info(JOBS_OUT_STREAM)  # type: ignore[attr-defined]
            logger.debug("NATS stream %s already exists", JOBS_OUT_STREAM)
        except nats.js.errors.NotFoundError:
            await self._js.add_stream(cfg)  # type: ignore[attr-defined]
            logger.info("Created NATS stream %s", JOBS_OUT_STREAM)

    async def _ensure_consumer(
        self,
        durable: str,
        filter_subject: str,
        ack_wait: int = 3600,
        max_deliver: int = 3,
        max_ack_pending: int = 100,
    ) -> None:
        """Create a durable PULL consumer on DCAF_JOBS_IN if absent."""
        import nats.js.errors
        from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

        cfg = ConsumerConfig(
            durable_name=durable,
            filter_subject=filter_subject,
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=ack_wait,
            max_deliver=max_deliver,
            max_ack_pending=max_ack_pending,
        )
        try:
            await self._js.consumer_info(JOBS_IN_STREAM, durable)  # type: ignore[attr-defined]
        except nats.js.errors.NotFoundError:
            await self._js.add_consumer(JOBS_IN_STREAM, cfg)  # type: ignore[attr-defined]
            logger.info("Created NATS consumer durable=%s filter=%s", durable, filter_subject)

    # ── enqueue ───────────────────────────────────────────────────────────────

    async def enqueue(self, request: JobRequest) -> str:
        """Publish request to DCAF_JOBS_IN and record status as queued.

        Subject: ``dcaf.jobs.in.<agent_name>.start``
        """
        subject = jobs_in_subject(request.agent_name)
        payload = request.model_dump_json().encode()
        await self._js.publish(subject, payload)  # type: ignore[attr-defined]
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
        # Cold-start: buffer empty — try to restore from JetStream once.
        if job_id not in self._events and after == 0:
            await self._replay_from_jetstream(job_id)
        return self._events.get(job_id, [])[after:]

    async def _replay_from_jetstream(self, job_id: str) -> None:
        """Restore job events from DCAF_JOBS_OUT into the in-memory buffer."""
        import uuid

        import nats.js.errors
        from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

        subject = jobs_out_subject(self._agent_name, job_id)
        durable = f"replay-{uuid.uuid4().hex[:12]}"

        cfg = ConsumerConfig(
            durable_name=durable,
            filter_subject=subject,
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=30,
            max_deliver=1,
        )

        events: list[JobEvent] = []
        try:
            await self._js.add_consumer(JOBS_OUT_STREAM, cfg)  # type: ignore[attr-defined]
            sub = await self._js.pull_subscribe(  # type: ignore[attr-defined]
                subject, durable=durable, stream=JOBS_OUT_STREAM
            )
            while True:
                try:
                    msgs = await sub.fetch(100, timeout=1.0)
                    for msg in msgs:
                        try:
                            e = JobEvent.model_validate_json(msg.data.decode("utf-8"))
                            events.append(e)
                            await msg.ack()
                        except Exception:
                            logger.exception("replay: bad event payload for job %s", job_id)
                            with contextlib.suppress(Exception):
                                await msg.nak()
                except TimeoutError:
                    break  # no more messages
        except nats.js.errors.NotFoundError:
            pass  # stream or subject doesn't exist yet — normal for new jobs
        except Exception:
            logger.exception("_replay_from_jetstream failed for job %s", job_id)
            return
        finally:
            with contextlib.suppress(Exception):
                await self._js.delete_consumer(JOBS_OUT_STREAM, durable)  # type: ignore[attr-defined]

        if events:
            self._events.setdefault(job_id, [])
            # Only populate if still empty (avoid overwriting events from a live worker).
            if not self._events[job_id]:
                self._events[job_id] = events
            logger.info(
                "_replay_from_jetstream: restored %d events for job %s", len(events), job_id
            )

    # ── generic publish / subscribe ───────────────────────────────────────────

    async def publish(self, subject: str, message: BaseModel) -> None:
        """Publish any Pydantic message to a NATS subject."""
        await self._js.publish(subject, message.model_dump_json().encode())  # type: ignore[attr-defined]

    async def subscribe(
        self,
        subject: str,
        durable: str,
        model_class: type[BaseModel],
        handler: Callable[[Any, JobMessageHandle], Awaitable[None]],
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Durable pull consumer for any Pydantic message type.

        Parses bytes with ``model_class.model_validate_json``.
        Handler receives ``(parsed_message, JobMessageHandle)`` and must ack/nak.
        """
        await self._ensure_consumer(durable=durable, filter_subject=subject)
        sub = await self._js.pull_subscribe(subject, durable=durable, stream=JOBS_IN_STREAM)  # type: ignore[attr-defined]
        logger.info("subscribe listening on %s (durable=%s)", subject, durable)

        while not (stop_event and stop_event.is_set()):
            try:
                msgs = await sub.fetch(10, timeout=1.0)
            except TimeoutError:
                continue
            except Exception:
                logger.exception("subscribe fetch failed durable=%s", durable)
                await asyncio.sleep(0.5)
                continue

            for msg in msgs:
                if stop_event and stop_event.is_set():
                    with contextlib.suppress(Exception):
                        await msg.nak()
                    continue
                try:
                    obj = model_class.model_validate_json(msg.data.decode("utf-8"))
                    await handler(obj, NatsJobMessageHandle(msg))
                except Exception:
                    logger.exception("subscribe handler failed durable=%s", durable)
                    with contextlib.suppress(Exception):
                        await msg.nak()

        logger.info("subscribe exiting (stop_event set) durable=%s", durable)

    # ── worker: subscribe_jobs ────────────────────────────────────────────────

    async def subscribe_jobs(
        self,
        handler: JobRequestHandler,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Pull jobs from DCAF_JOBS_IN and invoke *handler* for each one.

        Thin wrapper around :meth:`subscribe` scoped to this agent's subject.
        """
        await self.subscribe(
            jobs_in_subject(self._agent_name),
            f"{self._agent_name}-jobs",
            JobRequest,
            handler,
            stop_event,
        )

    # ── worker: emit event ────────────────────────────────────────────────────

    async def emit_event(self, event: JobEvent) -> None:
        """Buffer a job event in memory and publish to NATS OUT stream.

        Called by workers (co-located in the same process) to store progress
        events.  :meth:`get_events` and the SSE endpoint read from this buffer.

        Also mirrors ``status`` event transitions into :attr:`_status`.
        """
        bucket = self._events.setdefault(event.job_id, [])
        event.seq = len(bucket)
        bucket.append(event)

        # Publish to NATS OUT — non-fatal: log warning but never break the worker.
        try:
            subject = jobs_out_subject(self._agent_name, event.job_id)
            await self._js.publish(subject, event.model_dump_json().encode())  # type: ignore[attr-defined]
        except Exception:
            logger.warning(
                "emit_event: NATS OUT publish failed for job %s (buffered in memory only)",
                event.job_id,
            )

        if event.event_type == "status" and event.data and event.job_id in self._status:
            new_status = event.data.get("status")
            if new_status:
                self._status[event.job_id].status = new_status
                self._status[event.job_id].updated_at = event.timestamp
                if new_status == "failed":
                    self._status[event.job_id].error = event.data.get("error")
