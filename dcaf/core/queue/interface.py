"""Abstract interface for the DCAF job queue."""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from .models import JobEvent, JobRequest, JobStatus


class JobMessageHandle(ABC):
    """Handle returned to ``subscribe_jobs`` handlers for message acknowledgement."""

    @abstractmethod
    async def ack(self) -> None:
        """Acknowledge successful processing — removes the message from the queue."""
        ...

    @abstractmethod
    async def nak(self) -> None:
        """Negative-acknowledge — message will be redelivered after a backoff."""
        ...

    @abstractmethod
    async def in_progress(self) -> None:
        """Reset the ack deadline — use during long-running processing."""
        ...


JobRequestHandler = Callable[[JobRequest, JobMessageHandle], Awaitable[None]]


class JobQueue(ABC):
    """Abstract async job queue.

    Concrete implementations publish job requests to a broker and
    provide read access to job status and events.

    Server side
    -----------
    Call :meth:`enqueue` to publish a job, then poll :meth:`get_status`
    and :meth:`get_events` to track progress.

    Worker side
    -----------
    Call :meth:`subscribe_jobs` to pull jobs from the queue and process them.
    Emit progress via :meth:`emit_event`.
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
    async def subscribe_jobs(
        self,
        handler: JobRequestHandler,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Pull jobs from the queue and invoke *handler* for each one.

        The handler receives a ``(JobRequest, JobMessageHandle)`` pair and is
        responsible for calling :meth:`JobMessageHandle.ack` or
        :meth:`JobMessageHandle.nak`.  Runs until *stop_event* is set (or
        forever if *stop_event* is ``None``).
        """
        ...

    @abstractmethod
    async def emit_event(self, event: JobEvent) -> None:
        """Store a job event emitted by a worker.

        Buffers the event in memory so that :meth:`get_events` and the SSE
        endpoint can serve it.  Also mirrors ``status`` transitions into the
        in-memory job status.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release connections and resources."""
        ...

    @abstractmethod
    async def publish(self, subject: str, message: BaseModel) -> None:
        """Publish any Pydantic message to a NATS subject."""
        ...

    @abstractmethod
    async def subscribe(
        self,
        subject: str,
        durable: str,
        model_class: type[BaseModel],
        handler: Callable[[Any, "JobMessageHandle"], Awaitable[None]],
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """Durable pull consumer for any Pydantic message type.

        Parses bytes with ``model_class.model_validate_json``.
        Handler receives ``(parsed_message, JobMessageHandle)`` and must ack/nak.
        """
        ...
