"""
Credential management for cloud providers.

Prepares scoped credentials at request time — writing merged kubeconfigs for
K8s-type scopes and per-scope env dicts for AWS/GCP scopes — without ever
mutating os.environ (concurrency-safe for async servers).

Usage (k8s-ai-agent style):
    async with CredentialManager(context) as prepared:
        base_env = prepared.get_subprocess_env()          # includes KUBECONFIG
        for scope in context.scopes_for_type(["eks"]):
            aws_env = prepared.get_subprocess_env(scope.name)  # per-account creds
            subprocess.run(["kubectl", "--context", scope.name, ...], env=base_env)
    # all temp files deleted here
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

import yaml

from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.domain.value_objects.scope import Scope

logger = logging.getLogger(__name__)

_K8S_TYPES = frozenset({"eks", "gke", "kubernetes"})
_AWS_TYPES = frozenset({"aws"})
_GCP_TYPES = frozenset({"gcp"})


@dataclass
class PreparedCredentials:
    """
    Ready-to-use credential artifacts for a single request.

    - kubeconfig_path: path to a merged kubeconfig file for all K8s-type scopes.
      KUBECONFIG is included in every get_subprocess_env() result automatically.
    - _scope_envs: per-scope env dicts for AWS/GCP scopes, keyed by scope.name.
      Pass scope_name to get_subprocess_env() to overlay that scope's credentials.
    """

    kubeconfig_path: str | None = None
    _scope_envs: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)

    def get_subprocess_env(self, scope_name: str | None = None) -> dict[str, str]:
        """
        Return a subprocess env dict (copy of os.environ + credentials).

        If scope_name is given and that scope has credentials, they are overlaid
        on top of the base env. This is safe to call concurrently.
        """
        env = os.environ.copy()
        if self.kubeconfig_path:
            env["KUBECONFIG"] = self.kubeconfig_path
        if scope_name and scope_name in self._scope_envs:
            env.update(self._scope_envs[scope_name])
        return env

    def to_context_additions(self) -> dict[str, Any]:
        """Dict to merge into the platform_context passed to tools."""
        result: dict[str, Any] = {}
        if self.kubeconfig_path:
            result["kubeconfig_path"] = self.kubeconfig_path
        return result


class CredentialManager:
    """
    Async context manager that prepares cloud credentials from a PlatformContext.

    - K8s scopes (eks/gke/kubernetes): builds a merged kubeconfig YAML with one
      context per scope named after scope.name. Tools inject --context <scope.name>.
    - AWS scopes: stores per-scope env dicts keyed by scope.name.
    - GCP scopes: writes per-scope JSON key temp files.
    - Legacy ctx.kubeconfig (base64): decoded and written as a single-cluster file.

    Never mutates os.environ. All temp files are deleted on __aexit__.
    """

    def __init__(self, context: PlatformContext) -> None:
        self._context = context
        self._temp_files: list[str] = []

    async def __aenter__(self) -> PreparedCredentials:
        return self._prepare()

    async def __aexit__(self, *args: Any) -> None:
        self._cleanup()

    def _prepare(self) -> PreparedCredentials:
        ctx = self._context
        scope_envs: dict[str, dict[str, str]] = {}

        # --- K8s scopes: build one merged kubeconfig ---
        k8s_scopes = [s for s in ctx.scopes if s.type in _K8S_TYPES]
        kubeconfig_path: str | None = None
        if k8s_scopes:
            kubeconfig_path = self._write_merged_kubeconfig(k8s_scopes)
        elif ctx.kubeconfig:
            # Legacy: single base64-encoded kubeconfig (no scopes)
            kubeconfig_path = self._write_raw_tempfile(ctx.kubeconfig, "kubeconfig_")

        # --- AWS and GCP scopes: per-scope env dicts ---
        for scope in ctx.scopes:
            if scope.type in _AWS_TYPES:
                scope_envs[scope.name] = _build_aws_env(scope)
            elif scope.type in _GCP_TYPES:
                gcp_env = self._build_gcp_env(scope)
                if gcp_env:
                    scope_envs[scope.name] = gcp_env

        return PreparedCredentials(
            kubeconfig_path=kubeconfig_path,
            _scope_envs=scope_envs,
        )

    def _write_merged_kubeconfig(self, scopes: list[Scope]) -> str | None:
        """Build a merged kubeconfig YAML with one context per K8s scope."""
        clusters = []
        contexts = []
        users = []

        for scope in scopes:
            cred = scope.credential
            token = cred.get("token", "")
            ca_cert = cred.get("base64certdata", "")
            server = scope.account_id  # account_id holds the API server URL for K8s types

            clusters.append(
                {
                    "name": scope.name,
                    "cluster": {
                        "certificate-authority-data": ca_cert,
                        "server": server,
                    },
                }
            )
            contexts.append(
                {
                    "name": scope.name,
                    "context": {"cluster": scope.name, "user": scope.name},
                }
            )
            users.append(
                {
                    "name": scope.name,
                    "user": {"token": token},
                }
            )

        kubeconfig = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": clusters,
            "contexts": contexts,
            "users": users,
            "current-context": scopes[0].name if scopes else "",
        }

        try:
            content = yaml.dump(kubeconfig, default_flow_style=False).encode()
            tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                delete=False, prefix="kubeconfig_", suffix=".yaml"
            )
            tmp.write(content)
            tmp.flush()
            tmp.close()
            os.chmod(tmp.name, 0o600)
            self._temp_files.append(tmp.name)
            logger.debug(
                "CredentialManager: wrote merged kubeconfig %s (%d contexts)", tmp.name, len(scopes)
            )
            return tmp.name
        except Exception as e:
            logger.warning("CredentialManager: failed to write kubeconfig: %s", e)
            return None

    def _write_raw_tempfile(self, b64_content: str, prefix: str, suffix: str = "") -> str | None:
        """Decode base64 content and write to a restricted temp file."""
        try:
            decoded = base64.b64decode(b64_content)
            tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
                delete=False, prefix=prefix, suffix=suffix
            )
            tmp.write(decoded)
            tmp.flush()
            tmp.close()
            os.chmod(tmp.name, 0o600)
            self._temp_files.append(tmp.name)
            logger.debug("CredentialManager: wrote temp file %s", tmp.name)
            return tmp.name
        except Exception as e:
            logger.warning("CredentialManager: failed to write temp file (%s): %s", prefix, e)
            return None

    def _build_gcp_env(self, scope: Scope) -> dict[str, str]:
        """Write GCP JSON key to temp file and return env dict."""
        json_b64 = scope.credential.get("json_key", "")
        if not json_b64:
            return {}
        gcp_path = self._write_raw_tempfile(json_b64, "gcp_key_", suffix=".json")
        if gcp_path:
            return {"GOOGLE_APPLICATION_CREDENTIALS": gcp_path}
        return {}

    def _cleanup(self) -> None:
        for path in self._temp_files:
            try:
                os.unlink(path)
                logger.debug("CredentialManager: deleted temp file %s", path)
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning("CredentialManager: failed to delete %s: %s", path, e)
        self._temp_files.clear()


def _build_aws_env(scope: Scope) -> dict[str, str]:
    """Build AWS credential env vars from a Scope."""
    cred = scope.credential
    aws_env: dict[str, str] = {}
    if cred.get("access_key"):
        aws_env["AWS_ACCESS_KEY_ID"] = cred["access_key"]
    if cred.get("secret_key"):
        aws_env["AWS_SECRET_ACCESS_KEY"] = cred["secret_key"]
    if cred.get("region"):
        aws_env["AWS_REGION"] = cred["region"]
    if cred.get("session_token"):
        aws_env["AWS_SESSION_TOKEN"] = cred["session_token"]
    return aws_env
