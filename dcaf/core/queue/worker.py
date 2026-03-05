"""AgentWorker — base class for DCAF agent workers.

Encapsulates all queue boilerplate so concrete agents only implement
business-logic handlers.  Boilerplate provided:

- Concurrency control (asyncio semaphore)
- Deduplication of in-flight runs by thread_id
- Graceful shutdown on SIGTERM/SIGINT
- NATS heartbeat keep-alive during long-running handlers
- Message dispatch by ``type`` field
- Extensible type inference (override ``resolve_message_type``)

Usage
-----
::

    from dcaf.core.queue import AgentWorker, AgentMessageHandle

    class MyWorker(AgentWorker):
        async def handle_task(self, msg: dict, handle: AgentMessageHandle) -> None:
            heartbeat = asyncio.create_task(self.heartbeat_loop(handle))
            try:
                ...
                await handle.ack()
            finally:
                heartbeat.cancel()

    if __name__ == "__main__":
        asyncio.run(MyWorker("my-agent").run())
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from abc import ABC, abstractmethod
from typing import Any

from .channel import AgentChannel, AgentMessageHandle

logger = logging.getLogger(__name__)


class AgentWorker(ABC):
    """Abstract base class for DCAF agent workers.

    Subclasses must implement :meth:`handle_task`.  The other three handler
    methods (``handle_answer``, ``handle_checkpoint_approve``,
    ``handle_checkpoint_feedback``) default to nak-ing the message, which is
    correct for agents that do not support those flows.

    Override :meth:`resolve_message_type` to implement type inference — for
    example, reclassifying an incoming ``"task"`` as ``"answer"`` when the
    thread already has a PAUSED run.
    """

    def __init__(
        self,
        agent_name: str,
        nats_url: str | None = None,
        max_concurrent: int = 3,
        shutdown_timeout: int = 300,
    ) -> None:
        self._agent_name = agent_name
        self._channel = AgentChannel(agent_name, nats_url)
        self._max_concurrent = max_concurrent
        self._shutdown_timeout = shutdown_timeout
        self._log = logging.getLogger(f"dcaf.worker.{agent_name}")

        # Initialised in run() so they bind to the correct event loop.
        self._semaphore: asyncio.Semaphore | None = None
        self._active_runs: dict[str, asyncio.Task] = {}
        self._active_runs_lock: asyncio.Lock | None = None
        self._shutdown_event: asyncio.Event | None = None

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def channel(self) -> AgentChannel:
        """The underlying :class:`AgentChannel` (connected after ``run()`` starts)."""
        return self._channel

    # ── Abstract / overridable handlers ───────────────────────────────────────

    @abstractmethod
    async def handle_task(self, msg: dict, handle: AgentMessageHandle) -> None:
        """Process a new task.  Must call ``handle.ack()`` or ``handle.nak()``."""

    async def handle_answer(self, msg: dict, handle: AgentMessageHandle) -> None:
        """Process a clarification answer for a PAUSED run.

        Default implementation nak-s the message.  Override if the agent
        supports pause/resume.
        """
        self._log.warning(
            "handle_answer not implemented — nak-ing thread_id=%s", msg.get("thread_id", "?")
        )
        await handle.nak()

    async def handle_checkpoint_approve(self, msg: dict, handle: AgentMessageHandle) -> None:
        """Process a checkpoint approval.

        Default implementation nak-s the message.
        """
        self._log.warning(
            "handle_checkpoint_approve not implemented — nak-ing thread_id=%s",
            msg.get("thread_id", "?"),
        )
        await handle.nak()

    async def handle_checkpoint_feedback(self, msg: dict, handle: AgentMessageHandle) -> None:
        """Process checkpoint feedback (re-run step with corrections).

        Default implementation nak-s the message.
        """
        self._log.warning(
            "handle_checkpoint_feedback not implemented — nak-ing thread_id=%s",
            msg.get("thread_id", "?"),
        )
        await handle.nak()

    # ── Type inference hook ────────────────────────────────────────────────────

    async def resolve_message_type(self, msg: dict, msg_type: str) -> str:  # noqa: ARG002
        """Optionally reclassify *msg_type* before dispatch.

        Called once per message, before the semaphore is acquired.
        The default implementation returns *msg_type* unchanged.

        Override to implement type inference — for example, reclassify a
        ``"task"`` as ``"answer"`` when the sender (HelpDesk) does not track
        run state and always sends ``"task"`` regardless of whether a run is
        already PAUSED::

            async def resolve_message_type(self, msg, msg_type):
                if msg_type == "task":
                    thread_id = msg.get("thread_id", "")
                    run_id = await asyncio.to_thread(self._store.find_by_thread_id, thread_id)
                    if run_id:
                        run = await asyncio.to_thread(self._store.get, run_id)
                        if (run or {}).get("status") == "PAUSED":
                            return "answer"
                return msg_type
        """
        return msg_type

    # ── Utilities for handler implementations ─────────────────────────────────

    async def heartbeat_loop(
        self,
        handle: AgentMessageHandle,
        interval: int = 30,
    ) -> None:
        """Send periodic ``in_progress()`` signals to NATS to prevent redelivery.

        Intended to be run as a background task inside a handler::

            heartbeat = asyncio.create_task(self.heartbeat_loop(handle))
            try:
                ...  # long-running work
            finally:
                heartbeat.cancel()
        """
        while True:
            await asyncio.sleep(interval)
            try:
                await handle.in_progress()
            except Exception:
                self._log.warning("heartbeat in_progress() failed — message may be redelivered")
                break

    async def emit(
        self,
        thread_id: str,
        event_type: str,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Publish an event to ``DCAF_CHANNEL_OUT`` for *thread_id*."""
        await self._channel.emit(
            thread_id=thread_id,
            event_type=event_type,
            message=message,
            data=data,
        )

    # ── Internal dispatch ──────────────────────────────────────────────────────

    _HANDLER_NAMES = {
        "task": "handle_task",
        "answer": "handle_answer",
        "checkpoint_approve": "handle_checkpoint_approve",
        "checkpoint_feedback": "handle_checkpoint_feedback",
    }

    async def _dispatch(self, msg: dict, handle: AgentMessageHandle) -> None:
        assert self._semaphore is not None
        assert self._active_runs_lock is not None

        msg_type = msg.get("type", "")
        handler_name = self._HANDLER_NAMES.get(msg_type)
        if handler_name is None:
            self._log.warning("Unknown message type=%r — nak-ing", msg_type)
            await handle.nak()
            return

        # Allow subclass to reclassify (e.g. task → answer for PAUSED runs)
        resolved_type = await self.resolve_message_type(msg, msg_type)
        if resolved_type != msg_type:
            self._log.info(
                "Reclassified message type %r → %r (thread_id=%s)",
                msg_type,
                resolved_type,
                msg.get("thread_id", "?"),
            )
            msg_type = resolved_type
            handler_name = self._HANDLER_NAMES.get(msg_type)
            if handler_name is None:
                self._log.warning(
                    "resolve_message_type returned unknown type=%r — nak-ing", msg_type
                )
                await handle.nak()
                return

        handler = getattr(self, handler_name)

        # Deduplicate concurrent task runs by thread_id
        if msg_type == "task":
            thread_id = msg.get("thread_id", "")
            if thread_id:
                async with self._active_runs_lock:
                    if thread_id in self._active_runs:
                        self._log.info("thread_id=%s already active — nak-ing duplicate", thread_id)
                        await handle.nak()
                        return

        await self._semaphore.acquire()
        track_key = msg.get("thread_id") or str(id(msg))
        task = asyncio.create_task(self._run_handler(handler, msg, handle, track_key))
        async with self._active_runs_lock:
            self._active_runs[track_key] = task

    async def _run_handler(
        self,
        handler: Any,
        msg: dict,
        handle: AgentMessageHandle,
        track_key: str,
    ) -> None:
        """Wrap a handler invocation: release semaphore and deregister on exit."""
        assert self._semaphore is not None
        assert self._active_runs_lock is not None
        try:
            await handler(msg, handle)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await handle.nak()
            raise
        except Exception:
            self._log.exception("Unhandled exception in handler for track_key=%s", track_key)
            with contextlib.suppress(Exception):
                await handle.nak()
        finally:
            self._semaphore.release()
            async with self._active_runs_lock:
                self._active_runs.pop(track_key, None)

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Connect to NATS, subscribe to the IN channel, and run until shutdown.

        Registers SIGTERM/SIGINT handlers for graceful shutdown.  Waits for
        in-flight handlers to complete (up to *shutdown_timeout* seconds) before
        closing the NATS connection.
        """
        # Initialise event-loop-bound primitives here, not in __init__
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        self._active_runs = {}
        self._active_runs_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

        shutdown_event = self._shutdown_event

        def _signal_handler(sig: int, frame: Any = None) -> None:
            sig_name = signal.Signals(sig).name
            self._log.info("Received %s — initiating graceful shutdown", sig_name)
            shutdown_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _signal_handler)

        self._log.info("Connecting to NATS (agent=%s)...", self._agent_name)
        try:
            await self._channel.connect()
            self._log.info("Connected to NATS")
        except Exception:
            self._log.exception("Failed to connect to NATS")
            raise

        try:
            self._log.info("Subscribing to DCAF_CHANNEL_IN (agent=%s)", self._agent_name)
            sub_task = asyncio.create_task(
                self._channel.subscribe(self._dispatch, stop_event=shutdown_event)
            )

            await shutdown_event.wait()
            self._log.info("Shutdown event — waiting for subscribe loop to exit...")

            sub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sub_task

            async with self._active_runs_lock:
                active_tasks = list(self._active_runs.values())

            if active_tasks:
                self._log.info(
                    "Waiting for %d active run(s) to finish (timeout=%ds)...",
                    len(active_tasks),
                    self._shutdown_timeout,
                )
                done, pending = await asyncio.wait(active_tasks, timeout=self._shutdown_timeout)
                if pending:
                    self._log.warning(
                        "Cancelling %d run(s) that did not finish in time", len(pending)
                    )
                    for t in pending:
                        t.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

        finally:
            self._log.info("Closing NATS connection...")
            with contextlib.suppress(Exception):
                await self._channel.close()
            self._log.info("Worker shutdown complete")
