"""FastAPI middleware to attach a user identifier to the logging context.

For demo purposes we read `X-User-Id` from the request headers (if present).
A real implementation would integrate with your auth layer / JWTs.
"""

from __future__ import annotations

from typing import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.utils.request_context import current_user_id


class UserContextMiddleware(BaseHTTPMiddleware):
    header_name = "X-User-Id"

    async def dispatch(self, request, call_next: Callable[[object], Awaitable[Response]]):  # type: ignore[override]
        token = None
        user_id = request.headers.get(self.header_name)
        if user_id:
            token = current_user_id.set(user_id)
        try:
            response = await call_next(request)
        finally:
            if token is not None:
                current_user_id.reset(token)
        return response 