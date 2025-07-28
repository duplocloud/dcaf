"""FastAPI middleware to ensure every request carries a correlation ID.

The middleware reads an incoming `X-Request-Id` header (if any) or generates a
new UUID4. The value is stored in `current_request_id` contextvar so log
records—and any downstream async functions—can access it. The ID is also echoed
back to the client via the same header.
"""

from __future__ import annotations

import uuid
from typing import Callable, Awaitable

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.utils.request_context import current_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that adds and propagates `X-Request-Id`."""

    header_name = "X-Request-Id"

    async def dispatch(self, request, call_next: Callable[[object], Awaitable[Response]]):  # type: ignore[override]
        # Extract or create correlation ID
        incoming_id = request.headers.get(self.header_name)
        req_id = incoming_id or str(uuid.uuid4())

        token = current_request_id.set(req_id)
        try:
            response = await call_next(request)
        finally:
            # Ensure we reset the var even if an exception occurs
            current_request_id.reset(token)

        response.headers[self.header_name] = req_id
        return response 