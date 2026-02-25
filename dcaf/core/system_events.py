"""System event descriptors for configurable ``IntermittentUpdateEvent`` emission.

These descriptors control which internal framework events automatically emit
an ``IntermittentUpdateEvent`` to the client UI during streaming.

Quick start::

    from dcaf.core.system_events import THINKING, TOOL_STARTED, TOOL_COMPLETED

    # Use defaults (THINKING + TOOL_STARTED are on by default)
    agent = Agent(tools=[...])

    # Choose specific events
    agent = Agent(system_events=[THINKING, TOOL_STARTED, TOOL_COMPLETED])

    # Customise the text
    agent = Agent(system_events=[
        THINKING.with_text("Working..."),
        TOOL_STARTED.with_text("Running {tool_name}..."),
        TOOL_COMPLETED.with_text("Done: {tool_name}"),
    ])

    # Full control via formatter function (i18n, dynamic logic, etc.)
    agent = Agent(system_events=[
        THINKING.with_formatter(lambda _: t("agent.thinking")),
        TOOL_STARTED.with_formatter(lambda d: t("agent.tool_started", tool=d["tool_name"])),
    ])

    # Disable all system events
    agent = Agent(system_events=False)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SystemEvent:
    """Descriptor for a system-generated ``IntermittentUpdateEvent``.

    Ties one internal framework event type to a display message for the
    client UI.  Supports plain text, ``{variable}`` templates, and custom
    formatter functions for full control.

    Use the pre-built constants (``THINKING``, ``TOOL_STARTED``, etc.) rather
    than constructing this class directly.  Each constant's docstring lists
    which template variables are available for that event.
    """

    event_type: str
    """Public event type string (e.g. ``"tool_call_started"``).

    Matches the constants in :mod:`dcaf.core.events` used with
    ``@agent.on()``.
    """

    default_text: str
    """Default display text.  May contain ``{variable}`` placeholders."""

    formatter: Callable[[dict[str, Any]], str] | None = field(default=None, compare=False)
    """Custom formatter function.  When set, replaces ``default_text``
    interpolation entirely."""

    def format(self, data: dict[str, Any]) -> str:
        """Return the display text for this event given its data payload.

        Args:
            data: Event-specific variables (e.g. ``{"tool_name": "list_pods"}``).
                  Extra keys are ignored.

        Returns:
            The formatted string to display in the UI.
        """
        if self.formatter is not None:
            return self.formatter(data)
        # format_map ignores extra keys — safe with any payload shape
        return self.default_text.format_map(data)

    def with_text(self, text: str) -> SystemEvent:
        """Return a copy of this event with a custom text template.

        The text may contain ``{variable}`` placeholders; see the constant's
        docstring for available variables.

        Example::

            TOOL_STARTED.with_text("Using {tool_name}...")
            TOOL_COMPLETED.with_text("Finished {tool_name} ✓")
        """
        return SystemEvent(self.event_type, text, None)

    def with_formatter(self, fn: Callable[[dict[str, Any]], str]) -> SystemEvent:
        """Return a copy of this event with a custom formatter function.

        The formatter receives the event's full data dict and must return a
        string.  Use this for i18n, dynamic logic, or anything beyond simple
        templates.

        Example::

            TOOL_STARTED.with_formatter(
                lambda d: translations["tool_started"].format(tool=d["tool_name"])
            )
        """
        return SystemEvent(self.event_type, self.default_text, fn)


# ---------------------------------------------------------------------------
# Pre-built constants
# ---------------------------------------------------------------------------
# Import these by name — they are the intended public API.
# Each constant maps one internal framework event to a default display message.

THINKING = SystemEvent("reasoning_started", "Thinking...")
"""Emitted when the model begins its reasoning phase.

No template variables available.

Example::

    THINKING.with_text("Working...")
    THINKING.with_formatter(lambda _: translations["thinking"])
"""

TOOL_STARTED = SystemEvent("tool_call_started", "Calling tool: {tool_name}")
"""Emitted when a tool begins executing.

Available template variables:

- ``{tool_name}`` — the name of the tool being called

Example::

    TOOL_STARTED.with_text("Running {tool_name}...")
    TOOL_STARTED.with_formatter(lambda d: f"▶ {d['tool_name']}")
"""

TOOL_COMPLETED = SystemEvent("tool_call_completed", "Done: {tool_name}")
"""Emitted when a tool finishes successfully.

Available template variables:

- ``{tool_name}`` — the name of the tool that completed

Off by default.  Opt in via ``system_events=[..., TOOL_COMPLETED]``.

Example::

    TOOL_COMPLETED.with_text("{tool_name} complete")
    TOOL_COMPLETED.with_formatter(lambda d: f"✓ {d['tool_name']}")
"""

THINKING_COMPLETE = SystemEvent("reasoning_completed", "Done thinking")
"""Emitted when the model finishes its reasoning phase.

Pairs with ``THINKING`` to bracket the reasoning window.  Off by default.
Opt in via ``system_events=[THINKING, THINKING_COMPLETE, TOOL_STARTED]``.

No template variables available.

Example::

    THINKING_COMPLETE.with_text("Ready")
    THINKING_COMPLETE.with_formatter(lambda _: translations["thinking_done"])
"""

TOOL_FAILED = SystemEvent("tool_call_failed", "Failed: {tool_name}")
"""Emitted when a tool raises an exception.

Available template variables:

- ``{tool_name}`` — the name of the tool that failed
- ``{error}`` — the error message

Off by default.  Opt in via ``system_events=[..., TOOL_FAILED]``.

.. note::
    Requires adapter-level support.  Not yet emitted by all runtimes.

Example::

    TOOL_FAILED.with_text("{tool_name} failed: {error}")
    TOOL_FAILED.with_formatter(lambda d: f"✗ {d['tool_name']}: {d.get('error', '')}")
"""

# ---------------------------------------------------------------------------
# Default set — enabled automatically unless the user overrides system_events
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_EVENTS: list[SystemEvent] = [THINKING, TOOL_STARTED]
"""The system events enabled by default in every ``Agent``.

Currently: ``THINKING`` (reasoning started) and ``TOOL_STARTED`` (tool begins).
All other constants are opt-in.
"""
