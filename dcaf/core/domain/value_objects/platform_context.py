"""Runtime context value object."""

from dataclasses import dataclass
from typing import Any

from dcaf.core.domain.value_objects.scope import Scope


@dataclass(frozen=True)
class PlatformContext:
    """
    Runtime context - tenant, credentials, namespace, roles, and tracing.

    Immutable value object containing runtime environment data
    that may be needed by tools during execution.

    Tracing fields (user_id, session_id, run_id, request_id) enable
    distributed tracing and observability by propagating identifiers
    through the entire agent execution pipeline to the LLM provider.

    Note: Credentials are passed separately for security reasons
    and should not be logged or serialized.
    """

    # Tenant identification
    tenant_id: str | None = None
    tenant_name: str | None = None

    # User roles for access control
    user_roles: tuple[str, ...] = ()  # Tuple for immutability

    # Kubernetes context
    k8s_namespace: str | None = None
    kubeconfig: str | None = None

    # DuploCloud context
    duplo_base_url: str | None = None
    duplo_token: str | None = None

    # AWS context
    aws_region: str | None = None

    # Tracing context for distributed tracing and observability
    user_id: str | None = None  # User making the request
    session_id: str | None = None  # Session grouping related runs
    run_id: str | None = None  # Unique identifier for this execution run
    request_id: str | None = None  # HTTP request correlation ID

    # Cloud provider credential scopes
    scopes: tuple["Scope", ...] = ()

    # Additional context can be stored here
    _extra: tuple = ()  # Stored as tuple for immutability

    def __post_init__(self) -> None:
        """Validate context after initialization."""
        # Convert extra to tuple if provided as dict
        if isinstance(self._extra, dict):
            object.__setattr__(self, "_extra", tuple(sorted(self._extra.items())))
        # Convert user_roles list to tuple for immutability
        if isinstance(self.user_roles, list):
            object.__setattr__(self, "user_roles", tuple(self.user_roles))
        # Convert scopes list to tuple for immutability
        if isinstance(self.scopes, list):
            object.__setattr__(self, "scopes", tuple(self.scopes))

    @property
    def extra(self) -> dict[str, Any]:
        """Get extra context as a dictionary."""
        return dict(self._extra)

    def with_extra(self, **kwargs: Any) -> "PlatformContext":
        """Create a new PlatformContext with additional extra values."""
        new_extra = dict(self._extra)
        new_extra.update(kwargs)
        return PlatformContext(
            tenant_id=self.tenant_id,
            tenant_name=self.tenant_name,
            user_roles=self.user_roles,
            k8s_namespace=self.k8s_namespace,
            kubeconfig=self.kubeconfig,
            duplo_base_url=self.duplo_base_url,
            duplo_token=self.duplo_token,
            aws_region=self.aws_region,
            user_id=self.user_id,
            session_id=self.session_id,
            run_id=self.run_id,
            request_id=self.request_id,
            scopes=self.scopes,
            _extra=tuple(sorted(new_extra.items())),
        )

    def with_tracing(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        request_id: str | None = None,
    ) -> "PlatformContext":
        """
        Create a new PlatformContext with tracing identifiers.

        This is the preferred method for setting tracing context as it
        provides explicit parameter names and type hints.

        Args:
            user_id: User identifier for tracking who made the request
            session_id: Session identifier for grouping related runs
            run_id: Unique identifier for this specific execution run
            request_id: HTTP request ID for correlation across services

        Returns:
            New PlatformContext with tracing fields set
        """
        return PlatformContext(
            tenant_id=self.tenant_id,
            tenant_name=self.tenant_name,
            user_roles=self.user_roles,
            k8s_namespace=self.k8s_namespace,
            kubeconfig=self.kubeconfig,
            duplo_base_url=self.duplo_base_url,
            duplo_token=self.duplo_token,
            aws_region=self.aws_region,
            user_id=user_id or self.user_id,
            session_id=session_id or self.session_id,
            run_id=run_id or self.run_id,
            request_id=request_id or self.request_id,
            scopes=self.scopes,
            _extra=self._extra,
        )

    def with_scope(self, scope: "Scope") -> "PlatformContext":
        """Return a new PlatformContext with the given scope appended."""
        return PlatformContext(
            tenant_id=self.tenant_id,
            tenant_name=self.tenant_name,
            user_roles=self.user_roles,
            k8s_namespace=self.k8s_namespace,
            kubeconfig=self.kubeconfig,
            duplo_base_url=self.duplo_base_url,
            duplo_token=self.duplo_token,
            aws_region=self.aws_region,
            user_id=self.user_id,
            session_id=self.session_id,
            run_id=self.run_id,
            request_id=self.request_id,
            scopes=(*self.scopes, scope),
            _extra=self._extra,
        )

    def scopes_for_type(self, types: list[str]) -> list["Scope"]:
        """Return scopes whose type is in the given list (case-insensitive)."""
        lower = {t.lower() for t in types}
        return [s for s in self.scopes if s.type.lower() in lower]

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for tool execution.

        Note: This includes sensitive data like tokens.
        Use with caution and avoid logging.
        """
        result: dict[str, Any] = {}
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.tenant_name:
            result["tenant_name"] = self.tenant_name
        if self.user_roles:
            result["user_roles"] = list(self.user_roles)
        if self.k8s_namespace:
            result["k8s_namespace"] = self.k8s_namespace
        if self.kubeconfig:
            result["kubeconfig"] = self.kubeconfig
        if self.duplo_base_url:
            result["duplo_base_url"] = self.duplo_base_url
        if self.duplo_token:
            result["duplo_token"] = self.duplo_token
        if self.aws_region:
            result["aws_region"] = self.aws_region
        # Tracing fields
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.run_id:
            result["run_id"] = self.run_id
        if self.request_id:
            result["request_id"] = self.request_id
        if self.scopes:
            result["scopes"] = [s.to_dict() for s in self.scopes]
        result.update(self.extra)
        return result

    def get_tracing_dict(self) -> dict[str, str]:
        """
        Get only the tracing fields as a dictionary.

        Useful for passing to logging, metrics, or external tracing systems
        without exposing sensitive platform context data.

        Returns:
            Dictionary with non-None tracing fields
        """
        result: dict[str, str] = {}
        if self.user_id:
            result["user_id"] = self.user_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.run_id:
            result["run_id"] = self.run_id
        if self.request_id:
            result["request_id"] = self.request_id
        return result

    @classmethod
    def empty(cls) -> "PlatformContext":
        """Create an empty PlatformContext."""
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformContext":
        """Create a PlatformContext from a dictionary."""
        known_keys = {
            "tenant_id",
            "tenant_name",
            "user_roles",
            "k8s_namespace",
            "kubeconfig",
            "duplo_base_url",
            "duplo_token",
            "aws_region",
            # Tracing fields
            "user_id",
            "session_id",
            "run_id",
            "request_id",
            # Scopes
            "scopes",
        }
        known = {k: v for k, v in data.items() if k in known_keys}
        extra = {k: v for k, v in data.items() if k not in known_keys}

        # Convert user_roles list to tuple
        if "user_roles" in known and isinstance(known["user_roles"], list):
            known["user_roles"] = tuple(known["user_roles"])

        # Parse scopes from wire format
        if "scopes" in known:
            raw = known["scopes"]
            known["scopes"] = (
                tuple(Scope.from_dict(s) for s in raw) if isinstance(raw, list) else ()
            )

        return cls(**known, _extra=tuple(sorted(extra.items())))

    def __repr__(self) -> str:
        """Safe repr that doesn't expose sensitive data."""
        tracing_parts = []
        if self.user_id:
            tracing_parts.append(f"user_id={self.user_id!r}")
        if self.session_id:
            tracing_parts.append(f"session_id={self.session_id!r}")
        if self.run_id:
            tracing_parts.append(f"run_id={self.run_id!r}")
        if self.request_id:
            tracing_parts.append(f"request_id={self.request_id!r}")
        tracing_str = ", ".join(tracing_parts) if tracing_parts else "none"

        return (
            f"PlatformContext(tenant_id={self.tenant_id!r}, "
            f"tenant_name={self.tenant_name!r}, "
            f"user_roles={list(self.user_roles)!r}, "
            f"k8s_namespace={self.k8s_namespace!r}, "
            f"has_token={self.duplo_token is not None}, "
            f"tracing=[{tracing_str}])"
        )
