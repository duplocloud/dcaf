"""NATS JetStream agent channel for DCAF.

Provides a two-queue communication channel between an external system
(e.g. a UI, HelpDesk, CLI) and an agent worker.  Neither side talks to
the other directly — both communicate through persistent NATS streams:

- External system publishes task messages → ``DCAF_CHANNEL_IN``
- Agent subscribes, processes, and publishes events → ``DCAF_CHANNEL_OUT``
- External system subscribes to ``DCAF_CHANNEL_OUT`` to receive events

Stream layout
-------------
- IN:  ``DCAF_CHANNEL_IN``  — ``dcaf.channel.in.>``  (WORK_QUEUE, 7d TTL)
- OUT: ``DCAF_CHANNEL_OUT`` — ``dcaf.channel.out.>`` (LIMITS, 7d TTL, 10k/subject)

Subject helpers
---------------
- :func:`channel_in_subject`  — ``dcaf.channel.in.<agent_name>``
- :func:`channel_out_subject` — ``dcaf.channel.out.<agent_name>.<thread_id>``

IN message types (``type`` discriminator)
------------------------------------------
- ``"task"``               — start a new agent run
- ``"answer"``             — clarification answer for a PAUSED run
- ``"checkpoint_approve"`` — approve a checkpoint gate
- ``"checkpoint_feedback"``— re-run checkpoint step with feedback
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ─── Stream / subject constants ───────────────────────────────────────────────

CHANNEL_IN_STREAM = "DCAF_CHANNEL_IN"
CHANNEL_IN_SUBJECT_PATTERN = "dcaf.channel.in.>"

CHANNEL_OUT_STREAM = "DCAF_CHANNEL_OUT"
CHANNEL_OUT_SUBJECT_PATTERN = "dcaf.channel.out.>"


def channel_in_subject(agent_name: str) -> str:
    """Return the IN subject for *agent_name*.

    Pattern: ``dcaf.channel.in.<agent_name>``
    """
    return f"dcaf.channel.in.{agent_name}"


def channel_out_subject(agent_name: str, thread_id: str) -> str:
    """Return the OUT subject for a specific conversation thread.

    Pattern: ``dcaf.channel.out.<agent_name>.<thread_id>``
    """
    return f"dcaf.channel.out.{agent_name}.{thread_id}"


# ─── Models ───────────────────────────────────────────────────────────────────


class AgentEvent(BaseModel):
    """Event published to the OUT stream by the agent worker."""

    thread_id: str
    event_type: str  # "status"|"log"|"question"|"artifact"|"error"|"complete"|"checkpoint"
    message: str = ""
    data: dict[str, Any] | None = None
    seq: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ─── AgentMessageHandle ───────────────────────────────────────────────────────


class AgentMessageHandle:
    """Wraps a raw NATS JetStream message for acknowledgement."""

    def __init__(self, raw_msg: object) -> None:
        self._msg = raw_msg

    async def ack(self) -> None:
        await self._msg.ack()  # type: ignore[attr-defined]

    async def nak(self) -> None:
        await self._msg.nak()  # type: ignore[attr-defined]

    async def in_progress(self) -> None:
        await self._msg.in_progress()  # type: ignore[attr-defined]


# ─── AgentChannel ─────────────────────────────────────────────────────────────


class AgentChannel:
    """NATS JetStream channel connecting an external system to an agent worker.

    External systems publish task messages to ``DCAF_CHANNEL_IN``; the agent
    subscribes, processes, and emits events back to ``DCAF_CHANNEL_OUT``.
    The external system subscribes to ``DCAF_CHANNEL_OUT`` to receive progress
    events and questions.  Neither side communicates with the other directly.

    Lifecycle
    ---------
    Call ``await channel.connect()`` on startup, ``await channel.close()`` on
    shutdown.

    Worker usage
    ------------
    ::

        # nats_url is optional — reads NATS_URL env var when omitted
        channel = AgentChannel("iac-ai-agent")
        await channel.connect()

        async def dispatch(msg: dict, handle: AgentMessageHandle) -> None:
            # route by msg["type"]
            await handle.ack()

        await channel.subscribe(dispatch, stop_event=stop)

    Emitting events (agent → HelpDesk)
    -----------------------------------
    ::

        await channel.emit(thread_id, "status", message="Running iac.plan_changes")
        await channel.emit(thread_id, "complete", data={"pr_url": "..."})

    Publishing tasks (external system → IN)
    ----------------------------------------
    ::

        await channel.publish({"type": "task", "thread_id": "t-1", "messages": [...]})
    """

    def __init__(self, agent_name: str, nats_url: str | None = None) -> None:
        import os

        # nats_url is optional: callers (HelpDesk, simulator) should not need
        # to configure the NATS address.  It is infrastructure config, set via
        # the NATS_URL environment variable by the deployment team.
        self._url = nats_url or os.environ.get("NATS_URL", "nats://localhost:4222")
        self._agent_name = agent_name
        self._nc = None
        self._js = None
        # per-thread sequence counter for OUT events
        self._seqs: dict[str, int] = {}

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to NATS and ensure both channel streams exist."""
        import nats  # optional dep — imported lazily

        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()  # type: ignore[attr-defined]
        await self._ensure_in_stream()
        await self._ensure_out_stream()
        logger.info("AgentChannel connected to %s (agent=%s)", self._url, self._agent_name)

    async def close(self) -> None:
        if self._nc:
            with contextlib.suppress(Exception):
                await self._nc.drain()
            await self._nc.close()
        logger.info("AgentChannel closed")

    # ── stream provisioning ───────────────────────────────────────────────────

    async def _ensure_in_stream(self) -> None:
        """Create DCAF_CHANNEL_IN if it does not already exist."""
        import nats.js.errors
        from nats.js.api import RetentionPolicy, StorageType, StreamConfig

        cfg = StreamConfig(
            name=CHANNEL_IN_STREAM,
            subjects=[CHANNEL_IN_SUBJECT_PATTERN],
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.FILE,
            max_age=7 * 24 * 3600,
        )
        try:
            await self._js.stream_info(CHANNEL_IN_STREAM)  # type: ignore[attr-defined]
            logger.debug("NATS stream %s already exists", CHANNEL_IN_STREAM)
        except nats.js.errors.NotFoundError:
            await self._js.add_stream(cfg)  # type: ignore[attr-defined]
            logger.info("Created NATS stream %s", CHANNEL_IN_STREAM)

    async def _ensure_out_stream(self) -> None:
        """Create DCAF_CHANNEL_OUT if it does not already exist."""
        import nats.js.errors
        from nats.js.api import RetentionPolicy, StorageType, StreamConfig

        cfg = StreamConfig(
            name=CHANNEL_OUT_STREAM,
            subjects=[CHANNEL_OUT_SUBJECT_PATTERN],
            retention=RetentionPolicy.LIMITS,
            storage=StorageType.FILE,
            max_age=7 * 24 * 3600,
            max_msgs_per_subject=10_000,
        )
        try:
            await self._js.stream_info(CHANNEL_OUT_STREAM)  # type: ignore[attr-defined]
            logger.debug("NATS stream %s already exists", CHANNEL_OUT_STREAM)
        except nats.js.errors.NotFoundError:
            await self._js.add_stream(cfg)  # type: ignore[attr-defined]
            logger.info("Created NATS stream %s", CHANNEL_OUT_STREAM)

    async def _ensure_consumer(self, durable: str, filter_subject: str) -> None:
        """Create a durable pull consumer on DCAF_CHANNEL_IN if absent."""
        import nats.js.errors
        from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

        cfg = ConsumerConfig(
            durable_name=durable,
            filter_subject=filter_subject,
            deliver_policy=DeliverPolicy.ALL,
            ack_policy=AckPolicy.EXPLICIT,
            ack_wait=3600,
            max_deliver=3,
            max_ack_pending=100,
        )
        try:
            await self._js.consumer_info(CHANNEL_IN_STREAM, durable)  # type: ignore[attr-defined]
        except nats.js.errors.NotFoundError:
            await self._js.add_consumer(CHANNEL_IN_STREAM, cfg)  # type: ignore[attr-defined]
            logger.info("Created NATS consumer durable=%s filter=%s", durable, filter_subject)

    # ── worker: subscribe ─────────────────────────────────────────────────────

    async def subscribe(
        self,
        handler: Callable[[dict, AgentMessageHandle], Awaitable[None]],
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Pull all IN messages and invoke *handler* for each one.

        *handler* receives ``(raw_dict, AgentMessageHandle)`` and must call
        ``ack()`` or ``nak()``.  The message is delivered as a raw ``dict`` so
        the agent can apply its own type-based routing.

        Creates a durable pull consumer named ``{agent_name}-channel`` on
        ``DCAF_CHANNEL_IN``, filtered to ``dcaf.channel.in.<agent_name>``.
        """
        subject = channel_in_subject(self._agent_name)
        durable = f"{self._agent_name}-channel"
        await self._ensure_consumer(durable=durable, filter_subject=subject)

        sub = await self._js.pull_subscribe(  # type: ignore[attr-defined]
            subject, durable=durable, stream=CHANNEL_IN_STREAM
        )
        logger.info("AgentChannel subscribe listening on %s (durable=%s)", subject, durable)

        while not (stop_event and stop_event.is_set()):
            try:
                msgs = await sub.fetch(10, timeout=1.0)
            except TimeoutError:
                continue
            except Exception:
                logger.exception("AgentChannel subscribe fetch failed durable=%s", durable)
                await asyncio.sleep(0.5)
                continue

            for msg in msgs:
                if stop_event and stop_event.is_set():
                    with contextlib.suppress(Exception):
                        await msg.nak()
                    continue
                try:
                    import json

                    raw = json.loads(msg.data.decode("utf-8"))
                    await handler(raw, AgentMessageHandle(msg))
                except Exception:
                    logger.exception("AgentChannel handler failed durable=%s", durable)
                    with contextlib.suppress(Exception):
                        await msg.nak()

        logger.info("AgentChannel subscribe exiting (stop_event set) durable=%s", durable)

    # ── worker: emit ──────────────────────────────────────────────────────────

    async def emit(
        self,
        thread_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        """Publish an :class:`AgentEvent` to the OUT stream for *thread_id*.

        Tracks a per-thread sequence counter (``seq``) so consumers can detect
        gaps.  Non-fatal: a publish failure is logged as a warning and never
        propagated to the caller.
        """
        seq = self._seqs.get(thread_id, 0)
        self._seqs[thread_id] = seq + 1

        evt = AgentEvent(
            thread_id=thread_id,
            event_type=event_type,
            message=message,
            data=data,
            seq=seq,
        )
        subject = channel_out_subject(self._agent_name, thread_id)
        try:
            await self._js.publish(subject, evt.model_dump_json().encode())  # type: ignore[attr-defined]
        except Exception:
            logger.warning(
                "AgentChannel.emit: NATS OUT publish failed for thread_id=%s", thread_id
            )

    # ── external system: publish task/answer/checkpoint to IN ────────────────

    async def publish(self, body: dict[str, Any]) -> None:
        """Publish a raw dict to the IN stream.

        Used by the external system (HelpDesk, simulator) to submit a task or
        follow-up message.  The ``thread_id`` field must be present in *body*.
        """
        import json

        subject = channel_in_subject(self._agent_name)
        await self._js.publish(subject, json.dumps(body).encode())  # type: ignore[attr-defined]
        logger.debug("AgentChannel.publish → %s type=%s", subject, body.get("type"))
