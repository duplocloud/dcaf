"""Tests for AgentWorker dispatch, deduplication, and type inference."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from dcaf.core.queue.channel import AgentChannel, AgentMessageHandle
from dcaf.core.queue.worker import AgentWorker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle() -> AgentMessageHandle:
    """Return a mock AgentMessageHandle."""
    raw = MagicMock()
    raw.ack = AsyncMock()
    raw.nak = AsyncMock()
    raw.in_progress = AsyncMock()
    return AgentMessageHandle(raw)


class _SimpleWorker(AgentWorker):
    """Minimal concrete worker for testing — records calls."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__("test-agent", **kwargs)
        self.handled: list[tuple[str, dict]] = []

    async def handle_task(self, msg: dict, handle: AgentMessageHandle) -> None:
        self.handled.append(("task", msg))
        await handle.ack()

    async def handle_answer(self, msg: dict, handle: AgentMessageHandle) -> None:
        self.handled.append(("answer", msg))
        await handle.ack()

    async def handle_checkpoint_approve(self, msg: dict, handle: AgentMessageHandle) -> None:
        self.handled.append(("checkpoint_approve", msg))
        await handle.ack()

    async def handle_checkpoint_feedback(self, msg: dict, handle: AgentMessageHandle) -> None:
        self.handled.append(("checkpoint_feedback", msg))
        await handle.ack()


class _InferringWorker(_SimpleWorker):
    """Worker that reclassifies task→answer for a fixed thread_id."""

    PAUSED_THREAD = "thread-paused"

    async def resolve_message_type(self, msg: dict, msg_type: str) -> str:
        if msg_type == "task" and msg.get("thread_id") == self.PAUSED_THREAD:
            return "answer"
        return msg_type


def _init_worker(worker: AgentWorker) -> None:
    """Initialise event-loop-bound primitives (normally done inside run())."""
    worker._semaphore = asyncio.Semaphore(worker._max_concurrent)
    worker._active_runs = {}
    worker._active_runs_lock = asyncio.Lock()
    worker._shutdown_event = asyncio.Event()


# ---------------------------------------------------------------------------
# Dispatch — basic routing
# ---------------------------------------------------------------------------


async def test_dispatch_routes_task() -> None:
    worker = _SimpleWorker()
    _init_worker(worker)
    handle = _make_handle()

    await worker._dispatch({"type": "task", "thread_id": "t-1"}, handle)
    await asyncio.sleep(0)  # let the spawned task run

    assert len(worker.handled) == 1
    assert worker.handled[0][0] == "task"


async def test_dispatch_routes_all_types() -> None:
    for msg_type in ("task", "answer", "checkpoint_approve", "checkpoint_feedback"):
        worker = _SimpleWorker()
        _init_worker(worker)
        handle = _make_handle()
        await worker._dispatch({"type": msg_type, "thread_id": f"t-{msg_type}"}, handle)
        await asyncio.sleep(0)
        assert worker.handled[0][0] == msg_type


async def test_dispatch_naks_unknown_type() -> None:
    worker = _SimpleWorker()
    _init_worker(worker)
    handle = _make_handle()

    await worker._dispatch({"type": "bogus"}, handle)

    handle._msg.nak.assert_awaited_once()
    assert worker.handled == []


# ---------------------------------------------------------------------------
# Dispatch — type inference via resolve_message_type
# ---------------------------------------------------------------------------


async def test_resolve_message_type_reclassifies_task_as_answer() -> None:
    worker = _InferringWorker()
    _init_worker(worker)
    handle = _make_handle()

    await worker._dispatch({"type": "task", "thread_id": _InferringWorker.PAUSED_THREAD}, handle)
    await asyncio.sleep(0)

    assert worker.handled[0][0] == "answer"


async def test_resolve_message_type_unchanged_for_new_thread() -> None:
    worker = _InferringWorker()
    _init_worker(worker)
    handle = _make_handle()

    await worker._dispatch({"type": "task", "thread_id": "thread-new"}, handle)
    await asyncio.sleep(0)

    assert worker.handled[0][0] == "task"


# ---------------------------------------------------------------------------
# Dispatch — deduplication
# ---------------------------------------------------------------------------


async def test_duplicate_task_is_nakked() -> None:
    worker = _SimpleWorker()
    _init_worker(worker)

    # Simulate an already-active run for the same thread_id
    async with worker._active_runs_lock:
        worker._active_runs["t-dup"] = asyncio.create_task(asyncio.sleep(0))

    handle = _make_handle()
    await worker._dispatch({"type": "task", "thread_id": "t-dup"}, handle)

    handle._msg.nak.assert_awaited_once()
    assert worker.handled == []


async def test_deduplication_does_not_apply_to_answer() -> None:
    """Deduplication only applies to 'task' — answers should always go through."""
    worker = _SimpleWorker()
    _init_worker(worker)

    async with worker._active_runs_lock:
        worker._active_runs["t-1"] = asyncio.create_task(asyncio.sleep(0))

    handle = _make_handle()
    await worker._dispatch({"type": "answer", "thread_id": "t-1"}, handle)
    await asyncio.sleep(0)

    assert worker.handled[0][0] == "answer"


# ---------------------------------------------------------------------------
# Dispatch — before run() is called
# ---------------------------------------------------------------------------


async def test_dispatch_raises_before_run() -> None:
    worker = _SimpleWorker()
    # Do NOT call _init_worker — primitives are None

    handle = _make_handle()
    with pytest.raises(RuntimeError, match="before run\\(\\)"):
        await worker._dispatch({"type": "task"}, handle)


# ---------------------------------------------------------------------------
# Semaphore — concurrency limit
# ---------------------------------------------------------------------------


async def test_semaphore_limits_concurrency() -> None:
    """With max_concurrent=1, a second task must wait until the first releases."""
    order: list[int] = []
    task1_started = asyncio.Event()
    task1_release = asyncio.Event()

    class _SlowWorker(AgentWorker):
        async def handle_task(self, msg: dict, handle: AgentMessageHandle) -> None:
            if msg["n"] == 1:
                task1_started.set()
                await task1_release.wait()
            order.append(msg["n"])
            await handle.ack()

    worker = _SlowWorker("slow-agent", max_concurrent=1)
    _init_worker(worker)

    h1, h2 = _make_handle(), _make_handle()

    # Dispatch task-1; it will hold the semaphore until task1_release is set
    await worker._dispatch({"type": "task", "thread_id": "t-1", "n": 1}, h1)
    await task1_started.wait()  # ensure task-1 is running

    # Dispatch task-2 as a background task — it will block on the semaphore
    # until task-1 finishes (awaiting it directly would deadlock the test loop)
    dispatch2 = asyncio.create_task(
        worker._dispatch({"type": "task", "thread_id": "t-2", "n": 2}, h2)
    )
    await asyncio.sleep(0.01)  # let dispatch2 reach the semaphore.acquire()

    task1_release.set()   # unblock task-1 → semaphore released → task-2 runs
    await dispatch2
    await asyncio.sleep(0.02)  # let task-2 finish

    assert order == [1, 2]


# ---------------------------------------------------------------------------
# heartbeat_loop
# ---------------------------------------------------------------------------


async def test_heartbeat_loop_calls_in_progress() -> None:
    worker = _SimpleWorker()
    handle = _make_handle()

    task = asyncio.create_task(worker.heartbeat_loop(handle, interval=0.02))
    await asyncio.sleep(0.07)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert handle._msg.in_progress.await_count >= 2


async def test_heartbeat_loop_exits_on_in_progress_failure() -> None:
    worker = _SimpleWorker()
    handle = _make_handle()
    handle._msg.in_progress = AsyncMock(side_effect=Exception("NATS gone"))

    task = asyncio.create_task(worker.heartbeat_loop(handle, interval=0.01))
    await asyncio.sleep(0.05)

    assert task.done() and not task.cancelled()


# ---------------------------------------------------------------------------
# channel property
# ---------------------------------------------------------------------------


def test_channel_property_returns_agent_channel() -> None:
    worker = _SimpleWorker()
    assert isinstance(worker.channel, AgentChannel)
