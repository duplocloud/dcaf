"""Context-local storage for per-request identifiers.

Use `current_request_id` and `current_user_id` to attach correlation data that
log records can later inject. These values are scoped to the running asyncio
Task (via `contextvars`), so concurrent requests remain isolated.
"""

from __future__ import annotations

import contextvars
from typing import Optional

# Unique ID assigned to each inbound HTTP request
current_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_request_id", default=None
)

# Optional authenticated principal (email/subject) attached by auth middleware
current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_id", default=None
) 