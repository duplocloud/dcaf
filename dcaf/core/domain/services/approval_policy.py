"""Approval policy domain service."""

from dataclasses import dataclass
from typing import Any, Protocol

from ..value_objects.platform_context import PlatformContext

_LAYER_ORDER = ("global", "project", "agent", "skill", "ticket")


class ToolLike(Protocol):
    """Protocol for tool-like objects that have approval properties."""

    @property
    def name(self) -> str: ...

    @property
    def requires_approval(self) -> bool: ...


@dataclass
class ApprovalDecision:
    """Result of an approval policy check.

    Three possible verdicts:

    - ``approved()``       — no action required, execute immediately
    - ``needs_approval()`` — pause and send to human-in-the-loop
    - ``deny()``           — hard block, reject without HITL
    """

    requires_approval: bool
    is_blocked: bool = False
    reason: str | None = None

    @classmethod
    def approved(cls) -> "ApprovalDecision":
        """No approval needed — execute immediately."""
        return cls(requires_approval=False)

    @classmethod
    def needs_approval(cls, reason: str) -> "ApprovalDecision":
        """Pause for human-in-the-loop approval."""
        return cls(requires_approval=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> "ApprovalDecision":
        """Hard block — reject without offering HITL."""
        return cls(requires_approval=False, is_blocked=True, reason=reason)


def _primary_argument(tool_input: "dict[str, Any] | str | None") -> str | None:
    """Extract a single string from tool input for permission rule matching.

    For single-key dicts, returns the string value of that key.
    For multi-key dicts, concatenates all values separated by spaces.
    For strings, returns as-is.
    """
    if tool_input is None:
        return None
    if isinstance(tool_input, str):
        return tool_input
    if isinstance(tool_input, dict):
        values = list(tool_input.values())
        if len(values) == 1:
            return str(values[0])
        return " ".join(str(v) for v in values)
    return str(tool_input)


class ApprovalPolicy:
    """
    Domain service that determines what requires human approval.

    Evaluates tool calls against a layered deny/allow permission chain
    when ``PlatformContext.permissions`` is populated:

    1. Global DENY  → BLOCKED
    2. Project DENY → BLOCKED
    3. Agent DENY   → BLOCKED
    4. Skill DENY   → BLOCKED
    5. Ticket DENY  → BLOCKED
    6. Global ALLOW → ALLOWED
    7. Project ALLOW→ ALLOWED
    8. Agent ALLOW  → ALLOWED
    9. Skill ALLOW  → ALLOWED
    10. Ticket ALLOW→ ALLOWED
    11. (fallback)  → HITL

    When ``permissions`` is empty, falls back to the tool-level
    ``requires_approval`` flag (backwards compatible).

    Example::

        policy = ApprovalPolicy()
        decision = policy.check(tool, context, tool_input="kubectl get pods")
        if decision.is_blocked:
            # reject immediately
        elif decision.requires_approval:
            # send to HITL
        else:
            # execute
    """

    def __init__(self, always_approve_read_only: bool = True) -> None:
        self._always_approve_read_only = always_approve_read_only

    def requires_approval(
        self,
        tool: ToolLike,
        context: PlatformContext | None = None,
    ) -> bool:
        """Convenience: return True if this tool needs human approval."""
        return self.check(tool, context).requires_approval

    def check(
        self,
        tool: ToolLike,
        context: PlatformContext | None = None,
        tool_input: "dict[str, Any] | str | None" = None,
    ) -> ApprovalDecision:
        """
        Evaluate a tool call and return an :class:`ApprovalDecision`.

        Args:
            tool:       The tool being called.
            context:    Current platform context (may contain permissions).
            tool_input: Tool arguments; used for argument-pattern matching.
        """
        if context is not None and context.permissions:
            arg_str = _primary_argument(tool_input)

            # Steps 1-5: deny chain (global → project → agent → skill → ticket)
            for layer_name in _LAYER_ORDER:
                for layer in context.permissions:
                    if layer.layer == layer_name and layer.list == "deny":
                        for rule in layer.rules:
                            if rule.matches(tool.name, arg_str):
                                return ApprovalDecision.deny(
                                    f"Blocked by {layer_name} deny rule: {rule.raw}"
                                )

            # Steps 6-10: allow chain (global → project → agent → skill → ticket)
            for layer_name in _LAYER_ORDER:
                for layer in context.permissions:
                    if layer.layer == layer_name and layer.list == "allow":
                        for rule in layer.rules:
                            if rule.matches(tool.name, arg_str):
                                return ApprovalDecision.approved()

            # Step 11: no rule matched → HITL
            return ApprovalDecision.needs_approval(
                f"No permission rule matched for tool '{tool.name}'"
            )

        # No permissions in context: fall back to tool-level flag
        if tool.requires_approval:
            return ApprovalDecision.needs_approval(
                f"Tool '{tool.name}' is configured to require approval"
            )
        return ApprovalDecision.approved()

    def filter_requiring_approval(
        self,
        tools: list[ToolLike],
        context: PlatformContext | None = None,
    ) -> list[ToolLike]:
        """Filter tools to only those requiring approval."""
        return [t for t in tools if self.requires_approval(t, context)]
