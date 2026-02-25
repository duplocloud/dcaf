"""Stream context for user-emitted events.

Provides :func:`emit` — a module-level function that pushes any
``StreamEvent`` subclass into the active stream from tools,
``@agent.on()`` handlers, or interceptors.

Design
------
When ``Agent.run_stream()`` is called it creates a :class:`collections.deque`
and stores it in a :class:`contextvars.ContextVar`.  The deque is visible to
the entire synchronous call-chain (tools, helpers, interceptors) and is
drained between each internal event the runtime produces.

Because Python's ``ContextVar`` is propagated into thread-pool executors
automatically, this mechanism works for both synchronous and async tool
execution without any extra wiring.

``emit()`` is a no-op when called outside an active ``run_stream()``
invocation, so it is safe to call from code that may be run standalone in
tests or scripts.
"""

from __future__ import annotations

from collections import deque
from contextvars import ContextVar
from typing import Any

# Internal ContextVar — not exported.  Populated exclusively by
# Agent.run_stream(); read by emit().
_active_queue: ContextVar[deque[Any] | None] = ContextVar("_active_queue", default=None)


def emit(event: Any) -> None:
    """Push a stream event into the active stream from anywhere in the call stack.

    The event is queued and delivered to the client before the next
    framework-generated event in the same stream turn.  Safe to call from:

    * ``@tool`` decorated functions
    * ``@agent.on()`` event handlers
    * Interceptors (``LLMRequest`` / ``LLMResponse`` pipelines)
    * Any helper function called from any of the above

    Has **no effect** when called outside an active ``run_stream()``
    invocation (e.g. from a standalone script or test that calls ``agent.run()``
    instead of ``agent.run_stream()``).

    Args:
        event: Any ``StreamEvent`` subclass instance.  Common choices:

               * :class:`~dcaf.core.schemas.events.IntermittentUpdateEvent`
                 — WIP status messages ("Searching...", "Generating code...")
               * :class:`~dcaf.core.schemas.events.TextDeltaEvent`
                 — Stream content directly from tool code

    Example — WIP status from a tool::

        from dcaf.core import emit, tool
        from dcaf.core.schemas.events import IntermittentUpdateEvent

        @tool(description="Search the web")
        def web_search(query: str) -> str:
            emit(IntermittentUpdateEvent(text=f"Searching for: {query}"))
            results = _do_search(query)
            emit(IntermittentUpdateEvent(
                text="Search complete",
                content={"count": len(results), "query": query},
            ))
            return format_results(results)

    Example — stream code directly from a tool::

        from dcaf.core.schemas.events import TextDeltaEvent

        @tool(description="Generate a Python script")
        def generate_script(description: str) -> str:
            emit(IntermittentUpdateEvent(text="Generating script..."))
            code = _llm_generate(description)
            emit(TextDeltaEvent(text=f"\\n```python\\n{code}\\n```\\n"))
            return code
    """
    queue = _active_queue.get()
    if queue is not None:
        queue.append(event)
