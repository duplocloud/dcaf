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
    GET /api/jobs/{job_id}
        Return the current :class:`~dcaf.core.queue.models.JobStatus`.

    GET /api/jobs/{job_id}/events?after=0
        Return all :class:`~dcaf.core.queue.models.JobEvent` objects with
        ``seq > after``.  Poll repeatedly with ``after`` set to the last
        received seq to stream progress updates.

    Args:
        queue: A connected :class:`~dcaf.core.queue.interface.JobQueue`
               instance.  Typically a
               :class:`~dcaf.core.queue.nats_js.NatsJobQueue`.
    """
    from fastapi import APIRouter, HTTPException

    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("/{job_id}")
    async def get_job_status(job_id: str) -> dict[str, Any]:
        """Return the current status of a queued job."""
        status = await queue.get_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return status.model_dump(mode="json")

    @router.get("/{job_id}/events")
    async def get_job_events(job_id: str, after: int = 0) -> list[dict[str, Any]]:
        """Return events for a job with seq > after.

        Poll with ``?after=<last_seq>`` to retrieve only new events
        since your last call.
        """
        events = await queue.get_events(job_id, after)
        return [e.model_dump(mode="json") for e in events]

    return router
