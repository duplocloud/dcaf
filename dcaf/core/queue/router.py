"""FastAPI router for DCAF job queue endpoints."""

from __future__ import annotations

import logging
from typing import Any

from .interface import JobQueue

logger = logging.getLogger(__name__)


def create_queue_router(queue: JobQueue) -> Any:
    """Return a FastAPI APIRouter that exposes job status and event endpoints.

    Endpoints
    ---------
    GET /api/jobs/{job_id}/events/stream?after=0
        Stream events as Server-Sent Events (SSE).  The connection stays
        open until a terminal event (``done`` or ``error``) is delivered.
        Supports ``Last-Event-ID`` header for transparent reconnection.

    Args:
        queue: A connected :class:`~dcaf.core.queue.interface.JobQueue`
               instance.  Typically a
               :class:`~dcaf.core.queue.nats_js.NatsJobQueue`.
    """
    import asyncio
    import json

    from fastapi import APIRouter, HTTPException, Query, Request
    from fastapi.responses import StreamingResponse

    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    _TERMINAL_EVENTS = frozenset({"done", "error"})

    @router.get("/{job_id}/events/stream")
    async def stream_job_events(
        job_id: str,
        request: Request,
        after: int = Query(0, ge=0),
    ) -> StreamingResponse:
        """Stream job events as Server-Sent Events (SSE).

        Keeps the HTTP connection open and pushes each
        :class:`~dcaf.core.queue.models.JobEvent` as it arrives.
        The stream closes automatically when a terminal event
        (``event_type`` of ``"done"`` or ``"error"``) is delivered.

        Reconnection support: on reconnect the browser sends the
        ``Last-Event-ID`` header automatically; callers may also pass
        ``?after=N`` explicitly to resume from a known sequence number.
        """
        if await queue.get_status(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # Honour Last-Event-ID header for transparent browser reconnection
        last_event_id = request.headers.get("last-event-id", "")
        if last_event_id.isdigit():
            after = max(after, int(last_event_id))

        from collections.abc import AsyncGenerator

        async def event_generator() -> AsyncGenerator[str, None]:
            cursor = after
            while True:
                events = await queue.get_events(job_id, cursor)
                for evt in events:
                    data_str = json.dumps(evt.model_dump(mode="json"))
                    yield f"id: {evt.seq}\ndata: {data_str}\n\n"
                    cursor = evt.seq + 1
                    if evt.event_type in _TERMINAL_EVENTS:
                        return

                if not events:
                    # SSE comment — keeps the HTTP connection alive
                    yield ": keepalive\n\n"

                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
