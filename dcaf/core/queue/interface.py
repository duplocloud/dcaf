"""Abstract interface for the DCAF job queue."""

from abc import ABC, abstractmethod

from .models import JobEvent, JobRequest, JobStatus


class JobQueue(ABC):
    """Abstract async job queue.

    Concrete implementations publish job requests to a broker and
    provide read access to job status and events.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Open connections and ensure broker resources exist."""
        ...

    @abstractmethod
    async def enqueue(self, request: JobRequest) -> str:
        """Publish a job to the queue.

        Returns:
            The job_id (same as request.job_id).
        """
        ...

    @abstractmethod
    async def get_status(self, job_id: str) -> JobStatus | None:
        """Return the current status of a job, or None if not found."""
        ...

    @abstractmethod
    async def get_events(self, job_id: str, after: int = 0) -> list[JobEvent]:
        """Return all events for a job with seq > after."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release connections and resources."""
        ...
