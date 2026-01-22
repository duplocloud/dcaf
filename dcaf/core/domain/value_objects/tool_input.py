"""Immutable tool input parameters."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolInput:
    """
    Immutable tool input parameters.

    Wraps tool input in an immutable container to ensure
    inputs cannot be modified after creation.
    """

    _parameters: tuple  # Store as tuple of items for immutability

    def __init__(self, parameters: Mapping[str, Any]) -> None:
        """
        Initialize with a mapping of parameters.

        Args:
            parameters: The input parameters for the tool
        """
        # Convert to tuple of items for immutability
        # Using object.__setattr__ because dataclass is frozen
        object.__setattr__(self, "_parameters", tuple(sorted(parameters.items())))

    @property
    def parameters(self) -> dict[str, Any]:
        """Get the parameters as a dictionary."""
        return dict(self._parameters)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a parameter value by key."""
        return self.parameters.get(key, default)

    def __contains__(self, key: str) -> bool:
        """Check if a parameter exists."""
        return key in self.parameters

    def __repr__(self) -> str:
        return f"ToolInput({self.parameters!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ToolInput):
            return NotImplemented
        return self._parameters == other._parameters

    def __hash__(self) -> int:
        return hash(self._parameters)

    @classmethod
    def empty(cls) -> "ToolInput":
        """Create an empty ToolInput."""
        return cls({})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolInput":
        """Create a ToolInput from a dictionary."""
        return cls(data)
