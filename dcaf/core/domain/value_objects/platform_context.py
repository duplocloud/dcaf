"""Runtime context value object."""

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class PlatformContext:
    """
    Runtime context - tenant, credentials, namespace.
    
    Immutable value object containing runtime environment data
    that may be needed by tools during execution.
    
    Note: Credentials are passed separately for security reasons
    and should not be logged or serialized.
    """
    
    tenant_name: Optional[str] = None
    k8s_namespace: Optional[str] = None
    duplo_base_url: Optional[str] = None
    duplo_token: Optional[str] = None
    aws_region: Optional[str] = None
    kubeconfig: Optional[str] = None
    
    # Additional context can be stored here
    _extra: tuple = ()  # Stored as tuple for immutability
    
    def __post_init__(self) -> None:
        """Validate context after initialization."""
        # Convert extra to tuple if provided as dict
        if isinstance(self._extra, dict):
            object.__setattr__(self, "_extra", tuple(sorted(self._extra.items())))
    
    @property
    def extra(self) -> Dict[str, Any]:
        """Get extra context as a dictionary."""
        return dict(self._extra)
    
    def with_extra(self, **kwargs: Any) -> "PlatformContext":
        """Create a new PlatformContext with additional extra values."""
        new_extra = dict(self._extra)
        new_extra.update(kwargs)
        return PlatformContext(
            tenant_name=self.tenant_name,
            k8s_namespace=self.k8s_namespace,
            duplo_base_url=self.duplo_base_url,
            duplo_token=self.duplo_token,
            aws_region=self.aws_region,
            kubeconfig=self.kubeconfig,
            _extra=tuple(sorted(new_extra.items())),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for tool execution.
        
        Note: This includes sensitive data like tokens.
        Use with caution and avoid logging.
        """
        result = {}
        if self.tenant_name:
            result["tenant_name"] = self.tenant_name
        if self.k8s_namespace:
            result["k8s_namespace"] = self.k8s_namespace
        if self.duplo_base_url:
            result["duplo_base_url"] = self.duplo_base_url
        if self.duplo_token:
            result["duplo_token"] = self.duplo_token
        if self.aws_region:
            result["aws_region"] = self.aws_region
        if self.kubeconfig:
            result["kubeconfig"] = self.kubeconfig
        result.update(self.extra)
        return result
    
    @classmethod
    def empty(cls) -> "PlatformContext":
        """Create an empty PlatformContext."""
        return cls()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlatformContext":
        """Create a PlatformContext from a dictionary."""
        known_keys = {
            "tenant_name", "k8s_namespace", "duplo_base_url", 
            "duplo_token", "aws_region", "kubeconfig"
        }
        known = {k: v for k, v in data.items() if k in known_keys}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        return cls(**known, _extra=tuple(sorted(extra.items())))
    
    def __repr__(self) -> str:
        """Safe repr that doesn't expose sensitive data."""
        return (
            f"PlatformContext(tenant_name={self.tenant_name!r}, "
            f"k8s_namespace={self.k8s_namespace!r}, "
            f"has_token={self.duplo_token is not None})"
        )
