"""Permission value objects for layered deny/allow rule evaluation."""

import fnmatch
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionRule:
    """
    A single permission rule in the format ``ToolName(argument pattern)``.

    Examples::

        PermissionRule("Bash(kubectl delete *)")   # blocks kubectl delete commands
        PermissionRule("Bash(kubectl get *)")      # allows kubectl get commands
        PermissionRule("kubectl")                  # matches any kubectl call

    Matching is case-insensitive for both tool name and argument pattern.
    Argument patterns use standard glob syntax (``*`` and ``?``).
    """

    raw: str
    _tool_name: str = field(init=False, repr=False, compare=False)
    _arg_pattern: str | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        m = re.match(r"^([^(]+)\((.+)\)$", self.raw)
        if m:
            object.__setattr__(self, "_tool_name", m.group(1).strip())
            object.__setattr__(self, "_arg_pattern", m.group(2).strip())
        else:
            object.__setattr__(self, "_tool_name", self.raw.strip())
            object.__setattr__(self, "_arg_pattern", None)

    @property
    def tool_name(self) -> str:
        """Tool name extracted from the rule (part before the parenthesis)."""
        return self._tool_name

    @property
    def argument_pattern(self) -> str | None:
        """Glob pattern for the tool argument, or None if rule has no parentheses."""
        return self._arg_pattern

    def matches(self, tool_name: str, argument: str | None = None) -> bool:
        """
        Return True if this rule matches the given tool call.

        Args:
            tool_name: Name of the tool being called.
            argument:  Primary argument string to match against the pattern.
        """
        if tool_name.lower() != self._tool_name.lower():
            return False
        if self._arg_pattern is None:
            return True
        if argument is None:
            return False
        return fnmatch.fnmatch(str(argument).lower(), self._arg_pattern.lower())


@dataclass(frozen=True)
class PermissionLayer:
    """
    One layer in the permission evaluation chain.

    Attributes:
        layer: One of ``"global"``, ``"project"``, ``"agent"``, ``"skill"``, ``"ticket"``.
        list:  Either ``"deny"`` or ``"allow"``.
        rules: Ordered tuple of :class:`PermissionRule` objects.
    """

    layer: str
    list: str
    rules: tuple[PermissionRule, ...]

    def __post_init__(self) -> None:
        # Allow callers to pass a plain list of rule strings
        if isinstance(self.rules, (list, tuple)):
            coerced = tuple(
                r if isinstance(r, PermissionRule) else PermissionRule(r) for r in self.rules
            )
            object.__setattr__(self, "rules", coerced)

    @classmethod
    def from_dict(cls, data: dict) -> "PermissionLayer":
        """Parse from the platform_context wire format."""
        return cls(
            layer=data.get("layer", ""),
            list=data.get("list", ""),
            rules=tuple(PermissionRule(r) for r in data.get("rules", [])),
        )

    def to_dict(self) -> dict:
        """Serialize back to wire format."""
        return {
            "layer": self.layer,
            "list": self.list,
            "rules": [r.raw for r in self.rules],
        }
