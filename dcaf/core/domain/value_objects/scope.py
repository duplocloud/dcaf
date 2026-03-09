"""Scope value object — a named, typed credential context for a cloud provider."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scope:
    """
    A single named credential set for a cloud provider or Kubernetes cluster.

    Wire format (Pranav's DuploCloud payload):
        {
          "ProviderInfo": {"Type": "eks", "Name": "prod", "AccountId": "123456789"},
          "Credential":   {"Data": {"token": "...", "base64certdata": "..."}}
        }

    Types: "eks" | "gke" | "kubernetes" | "aws" | "gcp"

    The ``name`` field doubles as the kubectl ``--context`` value for K8s types.
    For K8s types, ``account_id`` holds the API server URL.
    For aws, ``account_id`` holds the AWS account ID.
    For gcp, ``account_id`` holds the GCP project ID.
    """

    type: str  # "eks" | "gke" | "kubernetes" | "aws" | "gcp"
    name: str  # scope selector; kubectl --context value for K8s types
    account_id: str = ""
    _data: tuple[tuple[str, str], ...] = field(default_factory=tuple, repr=False)

    @classmethod
    def k8s(cls, *, name: str, server: str, token: str, ca_cert: str) -> Scope:
        """Plain Kubernetes cluster credential."""
        return cls(
            type="kubernetes",
            name=name,
            account_id=server,
            _data=(("base64certdata", ca_cert), ("token", token)),
        )

    @classmethod
    def eks(cls, *, name: str, server: str, token: str, ca_cert: str) -> Scope:
        """AWS EKS cluster credential."""
        return cls(
            type="eks",
            name=name,
            account_id=server,
            _data=(("base64certdata", ca_cert), ("token", token)),
        )

    @classmethod
    def gke(cls, *, name: str, server: str, token: str, ca_cert: str) -> Scope:
        """GCP GKE cluster credential."""
        return cls(
            type="gke",
            name=name,
            account_id=server,
            _data=(("base64certdata", ca_cert), ("token", token)),
        )

    @classmethod
    def aws(
        cls,
        *,
        name: str,
        account_id: str,
        access_key: str,
        secret_key: str,
        region: str = "",
        session_token: str = "",
    ) -> Scope:
        """AWS account credential (for non-EKS calls: S3, DynamoDB, etc.)."""
        data: list[tuple[str, str]] = [("access_key", access_key), ("secret_key", secret_key)]
        if region:
            data.append(("region", region))
        if session_token:
            data.append(("session_token", session_token))
        return cls(type="aws", name=name, account_id=account_id, _data=tuple(sorted(data)))

    @classmethod
    def gcp(cls, *, name: str, project_id: str, json_key: str) -> Scope:
        """GCP service account credential (base64-encoded JSON key)."""
        return cls(type="gcp", name=name, account_id=project_id, _data=(("json_key", json_key),))

    @property
    def credential(self) -> dict[str, str]:
        """Credential data as a plain dict."""
        return dict(self._data)

    @classmethod
    def from_dict(cls, d: dict) -> Scope:
        """Parse Pranav's wire format: {ProviderInfo: {...}, Credential: {Data: {...}}}."""
        info = d.get("ProviderInfo") or {}
        data = (d.get("Credential") or {}).get("Data") or {}
        return cls(
            type=(info.get("Type") or "").lower(),
            name=info.get("Name") or "",
            account_id=info.get("AccountId") or "",
            _data=tuple(sorted(data.items())),
        )

    def to_dict(self) -> dict:
        """Serialize back to Pranav's wire format."""
        return {
            "ProviderInfo": {"Type": self.type, "Name": self.name, "AccountId": self.account_id},
            "Credential": {"Data": dict(self._data)},
        }
