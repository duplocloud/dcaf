# Credential Loading & CredentialManager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract cloud credential setup (AWS, GCP, Kubernetes) out of individual agents and into a reusable `CredentialManager` service in `dcaf/core/`, so any agent or tool can access prepared credentials without duplicating decode-and-write logic.

**Architecture:** Credentials arrive as a list of **Scopes** — a typed, named credential pair (`{ProviderInfo, Credential}` wire format already used in production by the k8s-ai-agent). A new `Scope` frozen dataclass and a `CredentialManager` service handle all preparation: K8s-type scopes build a merged kubeconfig (one context per scope), AWS scopes produce per-scope env dicts, GCP scopes write per-scope JSON key temp files. `PreparedCredentials.get_subprocess_env(scope_name)` returns a ready subprocess env dict keyed by scope name. Temp files are cleaned up after the request via an async context manager. LLM-layer (Bedrock) credential injection is handled separately by fixing `ModelFactory`.

**Wire format (from Pranav's payload, proven in k8s-ai-agent):**
```json
{
  "ProviderInfo": {"Type": "eks", "Name": "prod-cluster", "AccountId": "123456789"},
  "Credential":   {"Data": {"token": "eyJ...", "base64certdata": "LS0t..."}}
}
```
Types: `"eks"` | `"gke"` | `"kubernetes"` | `"aws"` | `"gcp"`

**k8s-ai-agent migration summary:**
| Before | After |
|--------|-------|
| `main.py` monkey-patches `PlatformContext.model_fields["scopes"]` | Removed — `PlatformContext.scopes` is native |
| `_extract_scopes()` reads `platform_context.scopes` from message | Replaced by `ctx.scopes` |
| `_k8s_scopes(scopes)` filters by `ProviderInfo.Type` | Replaced by `ctx.scopes_for_type(["eks","gke","kubernetes"])` |
| `_write_kubeconfigs(scopes)` builds merged kubeconfig manually | Replaced by `CredentialManager` (DCAF handles it) |
| `env["KUBECONFIG"] = kubeconfig_path` | `prepared.get_subprocess_env()["KUBECONFIG"]` |
| `scope["ProviderInfo"]["Name"]` | `scope.name` |
| `_inject_context()` adds `--context`/`--kube-context` | **Stays in k8s-ai-agent** (agent-specific kubectl/helm knowledge) |

**Tech Stack:** Python 3.11+, aioboto3, google-auth, PyYAML, tempfile, Ruff, MyPy, pytest-asyncio

---

## Credential Flow (before and after)

### Before (scattered, duplicated)
```
PlatformContext (raw) → each agent decodes base64, writes temp file, sets env vars
K8s agent: base64 decode → tempfile → subprocess env["KUBECONFIG"]
AWS agent: nothing (relies on global env vars)
GCP agent: nothing (relies on GOOGLE_APPLICATION_CREDENTIALS global)
LLM (Bedrock): aioboto3 default chain ignores explicit key/secret in ModelConfig
```

### After (centralized, scopes-based)
```
PlatformContext.scopes: tuple[Scope, ...] → CredentialManager → PreparedCredentials
  K8s scopes (eks/gke/kubernetes):
    → merged kubeconfig YAML (one context per scope) → temp file
    → PreparedCredentials.kubeconfig_path
    → prepared.get_subprocess_env()["KUBECONFIG"]
  AWS scopes:
    → per-scope env dicts keyed by scope.name
    → prepared.get_subprocess_env("prod-aws") → {AWS_ACCESS_KEY_ID, ...}
  GCP scopes:
    → per-scope JSON key temp files
    → prepared.get_subprocess_env("prod-gcp") → {GOOGLE_APPLICATION_CREDENTIALS}
Cleanup: CredentialManager.__aexit__ deletes all temp files

LLM (Bedrock): ModelFactory uses explicit aioboto3.Session with key+secret from ModelConfig
```

---

## Concurrency note

**Do not use `os.environ` to set credentials at request time** — it mutates global process state and is not safe for concurrent async requests. The `CredentialManager` passes credentials via subprocess env dicts and explicit SDK session objects. The `is_local` mode (Task 6) is the only place global env vars are acceptable (single-process, dev use only).

---

## Task 1: Create Scope Dataclass + Add scopes Field to PlatformContext

**Files:**
- Create: `dcaf/core/domain/value_objects/scope.py`
- Modify: `dcaf/core/domain/value_objects/platform_context.py`
- Modify: `dcaf/core/models.py` (legacy PlatformContext — add `scopes` field for wire compat)
- Create: `tests/core/test_scope.py`
- Create (or extend): `tests/core/test_platform_context_vo.py`

The k8s-ai-agent currently monkey-patches DCAF's `PlatformContext` with a `scopes` field. This task makes `scopes` native to DCAF and defines a typed `Scope` value object matching the production wire format.

---

### Step 1: Write the failing Scope tests

```python
# tests/core/test_scope.py
"""Tests for the Scope value object."""
import pytest
from dcaf.core.domain.value_objects.scope import Scope


class TestScopeFactories:
    def test_eks_factory(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token="tok123", ca_cert="cert==")
        assert s.type == "eks"
        assert s.name == "prod"
        assert s.account_id == "https://api.example.com"
        assert s.credential["token"] == "tok123"
        assert s.credential["base64certdata"] == "cert=="

    def test_k8s_factory(self):
        s = Scope.k8s(name="dev", server="https://dev.example.com", token="t", ca_cert="c")
        assert s.type == "kubernetes"
        assert s.name == "dev"

    def test_aws_factory_minimal(self):
        s = Scope.aws(name="prod-aws", account_id="123456789", access_key="AKIA", secret_key="sec")
        assert s.type == "aws"
        assert s.name == "prod-aws"
        assert s.credential["access_key"] == "AKIA"
        assert s.credential["secret_key"] == "sec"
        assert "region" not in s.credential

    def test_aws_factory_with_region_and_token(self):
        s = Scope.aws(
            name="prod-aws", account_id="123", access_key="AKIA", secret_key="sec",
            region="us-east-1", session_token="tok"
        )
        assert s.credential["region"] == "us-east-1"
        assert s.credential["session_token"] == "tok"

    def test_gcp_factory(self):
        s = Scope.gcp(name="prod-gcp", project_id="my-project", json_key="base64json==")
        assert s.type == "gcp"
        assert s.account_id == "my-project"
        assert s.credential["json_key"] == "base64json=="

    def test_scope_is_frozen(self):
        s = Scope.k8s(name="x", server="s", token="t", ca_cert="c")
        with pytest.raises((AttributeError, TypeError)):
            s.name = "y"  # type: ignore[misc]


class TestScopeWireFormat:
    def test_from_dict_parses_wire_format(self):
        wire = {
            "ProviderInfo": {"Type": "eks", "Name": "prod", "AccountId": "123456789"},
            "Credential": {"Data": {"token": "tok123", "base64certdata": "cert=="}},
        }
        s = Scope.from_dict(wire)
        assert s.type == "eks"
        assert s.name == "prod"
        assert s.account_id == "123456789"
        assert s.credential["token"] == "tok123"
        assert s.credential["base64certdata"] == "cert=="

    def test_from_dict_lowercases_type(self):
        wire = {"ProviderInfo": {"Type": "EKS", "Name": "x", "AccountId": ""}, "Credential": {"Data": {}}}
        assert Scope.from_dict(wire).type == "eks"

    def test_round_trip(self):
        original = Scope.eks(name="prod", server="https://api.example.com", token="t", ca_cert="c")
        wire = original.to_dict()
        restored = Scope.from_dict(wire)
        assert restored.type == original.type
        assert restored.name == original.name
        assert restored.credential == original.credential

    def test_from_dict_handles_missing_keys(self):
        s = Scope.from_dict({})
        assert s.type == ""
        assert s.name == ""
        assert s.credential == {}
```

### Step 2: Run to verify failure

```
pytest tests/core/test_scope.py -v
```
Expected: FAIL — `dcaf.core.domain.value_objects.scope` does not exist.

### Step 3: Create `dcaf/core/domain/value_objects/scope.py`

```python
# dcaf/core/domain/value_objects/scope.py
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
    """

    type: str        # "eks" | "gke" | "kubernetes" | "aws" | "gcp"
    name: str        # scope selector; kubectl --context value for K8s types
    account_id: str = ""  # server URL for K8s, AWS account ID for aws, project_id for gcp
    _data: tuple[tuple[str, str], ...] = field(default_factory=tuple, repr=False)

    @classmethod
    def k8s(cls, *, name: str, server: str, token: str, ca_cert: str) -> "Scope":
        """Plain Kubernetes cluster credential."""
        return cls(
            type="kubernetes",
            name=name,
            account_id=server,
            _data=(("base64certdata", ca_cert), ("token", token)),
        )

    @classmethod
    def eks(cls, *, name: str, server: str, token: str, ca_cert: str) -> "Scope":
        """AWS EKS cluster credential."""
        return cls(
            type="eks",
            name=name,
            account_id=server,
            _data=(("base64certdata", ca_cert), ("token", token)),
        )

    @classmethod
    def gke(cls, *, name: str, server: str, token: str, ca_cert: str) -> "Scope":
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
    ) -> "Scope":
        """AWS account credential (for non-EKS calls: S3, DynamoDB, etc.)."""
        data: list[tuple[str, str]] = [("access_key", access_key), ("secret_key", secret_key)]
        if region:
            data.append(("region", region))
        if session_token:
            data.append(("session_token", session_token))
        return cls(type="aws", name=name, account_id=account_id, _data=tuple(sorted(data)))

    @classmethod
    def gcp(cls, *, name: str, project_id: str, json_key: str) -> "Scope":
        """GCP service account credential (base64-encoded JSON key)."""
        return cls(type="gcp", name=name, account_id=project_id, _data=(("json_key", json_key),))

    @property
    def credential(self) -> dict[str, str]:
        """Credential data as a plain dict."""
        return dict(self._data)

    @classmethod
    def from_dict(cls, d: dict) -> "Scope":
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
```

### Step 4: Run to verify Scope tests pass

```
pytest tests/core/test_scope.py -v
```
Expected: all PASS.

---

### Step 5: Write the failing PlatformContext scopes tests

```python
# tests/core/test_platform_context_vo.py
"""Tests for scopes field on domain PlatformContext value object."""
from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.domain.value_objects.scope import Scope


WIRE_EKS = {
    "ProviderInfo": {"Type": "eks", "Name": "prod", "AccountId": "123456789"},
    "Credential": {"Data": {"token": "tok", "base64certdata": "cert=="}},
}
WIRE_AWS = {
    "ProviderInfo": {"Type": "aws", "Name": "prod-aws", "AccountId": "123456789"},
    "Credential": {"Data": {"access_key": "AKIA", "secret_key": "sec"}},
}


class TestPlatformContextScopes:
    def test_scopes_field_defaults_empty(self):
        ctx = PlatformContext()
        assert ctx.scopes == ()

    def test_from_dict_parses_scopes_list(self):
        ctx = PlatformContext.from_dict({"scopes": [WIRE_EKS, WIRE_AWS]})
        assert len(ctx.scopes) == 2
        assert ctx.scopes[0].type == "eks"
        assert ctx.scopes[1].type == "aws"

    def test_from_dict_scopes_not_in_extra(self):
        ctx = PlatformContext.from_dict({"scopes": [WIRE_EKS]})
        assert "scopes" not in ctx.extra

    def test_to_dict_serializes_scopes(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token="tok", ca_cert="cert==")
        ctx = PlatformContext(scopes=(s,))
        d = ctx.to_dict()
        assert "scopes" in d
        assert d["scopes"][0]["ProviderInfo"]["Name"] == "prod"

    def test_to_dict_omits_scopes_when_empty(self):
        ctx = PlatformContext()
        assert "scopes" not in ctx.to_dict()

    def test_scopes_for_type_filters_correctly(self):
        ctx = PlatformContext.from_dict({"scopes": [WIRE_EKS, WIRE_AWS]})
        k8s = ctx.scopes_for_type(["eks", "gke", "kubernetes"])
        assert len(k8s) == 1
        assert k8s[0].type == "eks"

    def test_with_scope_appends_scope(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token="tok", ca_cert="cert==")
        ctx = PlatformContext().with_scope(s)
        assert len(ctx.scopes) == 1
        assert ctx.scopes[0].name == "prod"

    def test_with_scope_returns_new_instance(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token="tok", ca_cert="cert==")
        ctx1 = PlatformContext()
        ctx2 = ctx1.with_scope(s)
        assert ctx1 is not ctx2
        assert len(ctx1.scopes) == 0  # original unchanged
```

### Step 6: Run to verify PlatformContext tests fail

```
pytest tests/core/test_platform_context_vo.py -v
```
Expected: FAIL — `TypeError: unexpected keyword argument 'scopes'`.

### Step 7: Add `scopes` field to domain PlatformContext

In `dcaf/core/domain/value_objects/platform_context.py`:

**Add import** (near top, after existing imports):
```python
from dcaf.core.domain.value_objects.scope import Scope
```

**Add field** (after `aws_region: str | None = None`, line ~39):
```python
# Scopes carry per-provider credential sets (one per cluster/account).
# Wire format: [{"ProviderInfo": {...}, "Credential": {"Data": {...}}}, ...]
scopes: tuple[Scope, ...] = ()
```

**Add `"scopes"` to `known_keys`** in `from_dict()` (line ~187):
```python
known_keys = {
    ...existing keys...,
    "scopes",
}
```

**Parse scopes in `from_dict()`** (after the `_extra` assignment):
```python
scopes = tuple(Scope.from_dict(s) for s in data.get("scopes") or [])
return cls(...existing args..., scopes=scopes)
```

**Add scopes to `to_dict()`** (after the `aws_region` block):
```python
if self.scopes:
    result["scopes"] = [s.to_dict() for s in self.scopes]
```

**Update `with_extra()`** to pass `scopes=self.scopes`.

**Add helper methods** (after the `with_extra()` method):
```python
def with_scope(self, scope: "Scope") -> "PlatformContext":
    """Return a new PlatformContext with the given scope appended."""
    return PlatformContext(
        **{f: getattr(self, f) for f in self.__dataclass_fields__ if f != "scopes"},
        scopes=(*self.scopes, scope),
    )

def scopes_for_type(self, types: list[str]) -> list["Scope"]:
    """Return scopes whose type is in the given list (case-insensitive)."""
    lower = [t.lower() for t in types]
    return [s for s in self.scopes if s.type in lower]
```

### Step 8: Add `scopes` to legacy `models.py` PlatformContext

In `dcaf/core/models.py`, add to the legacy `PlatformContext` class (after the existing fields):
```python
# Scopes list — wire-format credential contexts (multi-cloud, multi-account).
# Eliminates the monkey-patch in k8s-ai-agent's main.py.
# Shape: list of {"ProviderInfo": {...}, "Credential": {"Data": {...}}}
scopes: list[dict] | None = None
```

### Step 9: Run to verify all tests pass

```
pytest tests/core/test_scope.py tests/core/test_platform_context_vo.py -v
```
Expected: all PASS.

### Step 10: Full quality check

```
pytest -x && ruff check . && mypy dcaf/
```

### Step 11: Commit

```bash
git add dcaf/core/domain/value_objects/scope.py \
        dcaf/core/domain/value_objects/platform_context.py \
        dcaf/core/models.py \
        tests/core/test_scope.py \
        tests/core/test_platform_context_vo.py
git commit -m "feat(models): add Scope value object and scopes field to PlatformContext"
```

---

## Task 2: Create CredentialManager Service (Scopes-Aware)

**Files:**
- Create: `dcaf/core/services/credential_manager.py`
- Create: `tests/core/services/__init__.py` (empty)
- Create: `tests/core/services/test_credential_manager.py`

The `CredentialManager` is an async context manager. It reads `PlatformContext.scopes` and the legacy `kubeconfig` field, prepares credentials, and returns a `PreparedCredentials` object. For K8s-type scopes it builds a merged kubeconfig (one context per scope). For AWS/GCP scopes it stores per-scope env dicts keyed by `scope.name`. Temp files are deleted on `__aexit__`. Never mutates `os.environ`.

The `get_subprocess_env(scope_name=None)` API is intentionally simple: pass a scope name to get that scope's credentials, or omit to get base env with `KUBECONFIG` only.

---

### Step 1: Write the failing tests

```python
# tests/core/services/test_credential_manager.py
"""Tests for CredentialManager service (scopes-based)."""
import base64
import os

import pytest
import yaml

from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.domain.value_objects.scope import Scope
from dcaf.core.services.credential_manager import CredentialManager, PreparedCredentials


FAKE_KUBECONFIG = b"apiVersion: v1\nclusters: []\n"
FAKE_GCP_JSON = b'{"type": "service_account", "project_id": "my-project"}'
FAKE_TOKEN = "eyJhbGciOiJSUzI1NiJ9.fake"
FAKE_CERT = base64.b64encode(b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----").decode()


class TestPreparedCredentials:
    def test_get_subprocess_env_no_credentials(self):
        prepared = PreparedCredentials()
        env = prepared.get_subprocess_env()
        assert "KUBECONFIG" not in env
        assert "AWS_ACCESS_KEY_ID" not in env

    def test_get_subprocess_env_sets_kubeconfig(self):
        prepared = PreparedCredentials(kubeconfig_path="/tmp/kube_abc")
        env = prepared.get_subprocess_env()
        assert env["KUBECONFIG"] == "/tmp/kube_abc"

    def test_get_subprocess_env_with_aws_scope(self):
        prepared = PreparedCredentials(
            _scope_envs={"prod-aws": {"AWS_ACCESS_KEY_ID": "AKIA123", "AWS_SECRET_ACCESS_KEY": "sec"}},
        )
        env = prepared.get_subprocess_env("prod-aws")
        assert env["AWS_ACCESS_KEY_ID"] == "AKIA123"
        assert env["AWS_SECRET_ACCESS_KEY"] == "sec"

    def test_get_subprocess_env_unknown_scope_returns_base_env(self):
        prepared = PreparedCredentials(kubeconfig_path="/tmp/kube")
        env = prepared.get_subprocess_env("nonexistent")
        assert env["KUBECONFIG"] == "/tmp/kube"
        assert "AWS_ACCESS_KEY_ID" not in env

    def test_to_context_additions_empty(self):
        assert PreparedCredentials().to_context_additions() == {}

    def test_to_context_additions_includes_kubeconfig_path(self):
        additions = PreparedCredentials(kubeconfig_path="/tmp/kube").to_context_additions()
        assert additions["kubeconfig_path"] == "/tmp/kube"


class TestCredentialManagerNoCredentials:
    async def test_empty_context_returns_empty_prepared(self):
        ctx = PlatformContext()
        async with CredentialManager(ctx) as prepared:
            assert prepared.kubeconfig_path is None

    async def test_legacy_kubeconfig_field_written_to_tempfile(self):
        """Backwards compat: PlatformContext.kubeconfig (base64) still works."""
        kube_b64 = base64.b64encode(FAKE_KUBECONFIG).decode()
        ctx = PlatformContext(kubeconfig=kube_b64)
        async with CredentialManager(ctx) as prepared:
            assert prepared.kubeconfig_path is not None
            assert os.path.exists(prepared.kubeconfig_path)
            with open(prepared.kubeconfig_path, "rb") as f:
                assert f.read() == FAKE_KUBECONFIG

    async def test_legacy_kubeconfig_tempfile_deleted_on_exit(self):
        kube_b64 = base64.b64encode(FAKE_KUBECONFIG).decode()
        ctx = PlatformContext(kubeconfig=kube_b64)
        path = None
        async with CredentialManager(ctx) as prepared:
            path = prepared.kubeconfig_path
        assert path is not None
        assert not os.path.exists(path)


class TestCredentialManagerK8sScopes:
    async def test_eks_scope_produces_kubeconfig_path(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT)
        ctx = PlatformContext(scopes=(s,))
        async with CredentialManager(ctx) as prepared:
            assert prepared.kubeconfig_path is not None
            assert os.path.exists(prepared.kubeconfig_path)

    async def test_kubeconfig_contains_one_context_per_scope(self):
        s1 = Scope.eks(name="prod", server="https://prod.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT)
        s2 = Scope.eks(name="staging", server="https://staging.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT)
        ctx = PlatformContext(scopes=(s1, s2))
        async with CredentialManager(ctx) as prepared:
            with open(prepared.kubeconfig_path) as f:
                kubeconfig = yaml.safe_load(f.read())
            context_names = {c["name"] for c in kubeconfig["contexts"]}
            assert "prod" in context_names
            assert "staging" in context_names

    async def test_kubeconfig_file_has_restricted_permissions(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT)
        ctx = PlatformContext(scopes=(s,))
        async with CredentialManager(ctx) as prepared:
            mode = oct(os.stat(prepared.kubeconfig_path).st_mode)[-3:]
            assert mode == "600"

    async def test_kubeconfig_tempfile_deleted_on_exit(self):
        s = Scope.eks(name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT)
        ctx = PlatformContext(scopes=(s,))
        path = None
        async with CredentialManager(ctx) as prepared:
            path = prepared.kubeconfig_path
        assert path is not None
        assert not os.path.exists(path)

    async def test_non_k8s_scopes_not_in_kubeconfig(self):
        """AWS scope does not pollute the kubeconfig."""
        k8s = Scope.eks(name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT)
        aws = Scope.aws(name="prod-aws", account_id="123", access_key="AKIA", secret_key="sec")
        ctx = PlatformContext(scopes=(k8s, aws))
        async with CredentialManager(ctx) as prepared:
            with open(prepared.kubeconfig_path) as f:
                kubeconfig = yaml.safe_load(f.read())
            context_names = {c["name"] for c in kubeconfig["contexts"]}
            assert "prod" in context_names
            assert "prod-aws" not in context_names


class TestCredentialManagerAwsScopes:
    async def test_aws_scope_env_contains_credentials(self):
        s = Scope.aws(name="prod-aws", account_id="123", access_key="AKIA123", secret_key="sec", region="us-east-1")
        ctx = PlatformContext(scopes=(s,))
        async with CredentialManager(ctx) as prepared:
            env = prepared.get_subprocess_env("prod-aws")
            assert env["AWS_ACCESS_KEY_ID"] == "AKIA123"
            assert env["AWS_SECRET_ACCESS_KEY"] == "sec"
            assert env["AWS_REGION"] == "us-east-1"

    async def test_two_aws_scopes_keyed_separately(self):
        s1 = Scope.aws(name="account-a", account_id="111", access_key="AKIA_A", secret_key="sec_a")
        s2 = Scope.aws(name="account-b", account_id="222", access_key="AKIA_B", secret_key="sec_b")
        ctx = PlatformContext(scopes=(s1, s2))
        async with CredentialManager(ctx) as prepared:
            assert prepared.get_subprocess_env("account-a")["AWS_ACCESS_KEY_ID"] == "AKIA_A"
            assert prepared.get_subprocess_env("account-b")["AWS_ACCESS_KEY_ID"] == "AKIA_B"


class TestCredentialManagerGcpScopes:
    async def test_gcp_scope_writes_json_key_tempfile(self):
        gcp_b64 = base64.b64encode(FAKE_GCP_JSON).decode()
        s = Scope.gcp(name="prod-gcp", project_id="my-project", json_key=gcp_b64)
        ctx = PlatformContext(scopes=(s,))
        async with CredentialManager(ctx) as prepared:
            env = prepared.get_subprocess_env("prod-gcp")
            path = env["GOOGLE_APPLICATION_CREDENTIALS"]
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == FAKE_GCP_JSON

    async def test_gcp_tempfile_deleted_on_exit(self):
        gcp_b64 = base64.b64encode(FAKE_GCP_JSON).decode()
        s = Scope.gcp(name="prod-gcp", project_id="my-project", json_key=gcp_b64)
        ctx = PlatformContext(scopes=(s,))
        path = None
        async with CredentialManager(ctx) as prepared:
            path = prepared.get_subprocess_env("prod-gcp").get("GOOGLE_APPLICATION_CREDENTIALS")
        assert path is not None
        assert not os.path.exists(path)
```

### Step 2: Run to verify failure

```
pytest tests/core/services/test_credential_manager.py -v
```
Expected: FAIL — module doesn't exist.

### Step 3: Create the CredentialManager

```python
# dcaf/core/services/credential_manager.py
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

        # --- AWS scopes: per-scope env dicts ---
        for scope in ctx.scopes:
            if scope.type in _AWS_TYPES:
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
                if aws_env:
                    scope_envs[scope.name] = aws_env

            # --- GCP scopes: write JSON key temp file ---
            elif scope.type in _GCP_TYPES:
                json_b64 = scope.credential.get("json_key", "")
                if json_b64:
                    gcp_path = self._write_raw_tempfile(json_b64, "gcp_key_", suffix=".json")
                    if gcp_path:
                        scope_envs[scope.name] = {"GOOGLE_APPLICATION_CREDENTIALS": gcp_path}

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

            clusters.append({
                "name": scope.name,
                "cluster": {
                    "certificate-authority-data": ca_cert,
                    "server": server,
                },
            })
            contexts.append({
                "name": scope.name,
                "context": {"cluster": scope.name, "user": scope.name},
            })
            users.append({
                "name": scope.name,
                "user": {"token": token},
            })

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
            logger.debug("CredentialManager: wrote merged kubeconfig %s (%d contexts)", tmp.name, len(scopes))
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
```

> **Note on server URL:** For K8s scopes, `scope.account_id` holds the API server URL (e.g. `https://api.prod.example.com`). Check the actual wire format from Pranav's payload against a real EKS token if the server URL is instead in `Credential.Data` — in that case add a `server` key to `_data` in `Scope.eks()` and read it from `scope.credential["server"]` here.

Also create `tests/core/services/__init__.py` (empty) so pytest finds the package.

### Step 4: Run to verify pass

```
pytest tests/core/services/test_credential_manager.py -v
```
Expected: all PASS.

### Step 5: Run quality checks

```
pytest -x && ruff check . && mypy dcaf/
```

Note: `yaml` is from `PyYAML`. Verify it's in `pyproject.toml` dependencies — it likely already is (agno/other dependencies pull it in). If not, add `PyYAML>=6.0` to `[project.dependencies]`.

### Step 6: Commit

```bash
git add dcaf/core/services/credential_manager.py \
        tests/core/services/__init__.py \
        tests/core/services/test_credential_manager.py
git commit -m "feat(core): add scopes-aware CredentialManager service"
```

---

## Task 3: Wire CredentialManager into AgentService

**Files:**
- Modify: `dcaf/core/application/services/agent_service.py:85-175`

`AgentService.execute()` (line 94) and `execute_stream()` (line 141) both do:
```python
context = request.get_platform_context()
```
then pass `context.to_dict()` to the runtime. We wrap this with `CredentialManager` so tools receive a platform_context dict that already has `kubeconfig_path` merged in. The scopes list is included by `context.to_dict()`, giving tools access to scope names for `--context` injection.

### Step 1: Write the failing test

```python
# tests/core/application/services/test_agent_service_credentials.py
"""Test that AgentService wires CredentialManager and enhances platform_context."""
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

FAKE_KUBECONFIG_B64 = base64.b64encode(b"apiVersion: v1\n").decode()


class TestAgentServiceCredentialWiring:
    @pytest.fixture
    def service(self):
        from dcaf.core.application.services.agent_service import AgentService
        runtime = AsyncMock()
        runtime.invoke = AsyncMock(return_value=MagicMock(text="ok", tool_calls=[]))
        conversations = MagicMock()
        conversations.get.return_value = None
        conversations.save = MagicMock()
        return AgentService(runtime=runtime, conversations=conversations)

    async def test_kubeconfig_path_added_to_platform_context(self, service):
        """CredentialManager should add kubeconfig_path to the context passed to runtime."""
        from dcaf.core.application.dtos.requests import AgentRequest
        from dcaf.core.domain.value_objects.platform_context import PlatformContext

        ctx = PlatformContext(kubeconfig=FAKE_KUBECONFIG_B64)
        request = AgentRequest(content="list pods", platform_context=ctx)

        await service.execute(request)

        call_kwargs = service._runtime.invoke.call_args.kwargs
        assert "kubeconfig_path" in call_kwargs["platform_context"]
        # Should be a real temp file path, not the raw base64
        assert call_kwargs["platform_context"]["kubeconfig_path"].startswith("/tmp")
```

### Step 2: Run to verify failure

```
pytest tests/core/application/services/test_agent_service_credentials.py -v
```
Expected: FAIL — `kubeconfig_path` not in context.

### Step 3: Modify AgentService.execute()

In `dcaf/core/application/services/agent_service.py`, update `execute()` (around line 94):

```python
async def execute(self, request: AgentRequest) -> AgentResponse:
    from dcaf.core.services.credential_manager import CredentialManager

    conversation = self._get_or_create_conversation(request)
    context = request.get_platform_context()
    conversation.update_context(context)
    conversation.add_user_message(request.content)

    async with CredentialManager(context) as prepared:
        platform_context_dict = (
            {**context.to_dict(), **prepared.to_context_additions()} if context else None
        )
        runtime_response = await self._runtime.invoke(
            messages=conversation.messages,
            tools=request.tools,
            system_prompt=request.system_prompt,
            static_system=request.static_system,
            dynamic_system=request.dynamic_system,
            platform_context=platform_context_dict,
        )

    response = self._process_response(
        conversation=conversation,
        runtime_response=runtime_response,
        tools=request.tools,
        context=context,
    )
    self._conversations.save(conversation)
    self._publish_events(conversation)
    return response
```

Apply the same `CredentialManager` wrap to `execute_stream()` (around line 141). The stream must remain within the `async with` block so temp files persist for the full stream duration:

```python
async def execute_stream(self, request: AgentRequest) -> AsyncIterator[StreamEvent]:
    from dcaf.core.services.credential_manager import CredentialManager

    conversation = self._get_or_create_conversation(request)
    context = request.get_platform_context()
    conversation.update_context(context)
    conversation.add_user_message(request.content)
    yield StreamEvent.message_start()

    async with CredentialManager(context) as prepared:
        platform_context_dict = (
            {**context.to_dict(), **prepared.to_context_additions()} if context else None
        )
        # ... rest of the streaming loop unchanged, using platform_context_dict ...
```

### Step 4: Run to verify pass

```
pytest tests/core/application/services/test_agent_service_credentials.py -v
```

### Step 5: Full suite

```
pytest -x && ruff check . && mypy dcaf/
```

### Step 6: Commit

```bash
git add dcaf/core/application/services/agent_service.py \
        tests/core/application/services/test_agent_service_credentials.py
git commit -m "feat(agent-service): wire CredentialManager into request lifecycle"
```

---

## Task 4: Fix ModelFactory — AWS Explicit Credential Path

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/model_factory.py:165-175`
- Create: `tests/core/test_model_factory.py`

`ModelConfig.aws_access_key` and `aws_secret_key` are populated from env vars and explicit kwargs but `_create_bedrock_model()` ignores them — it always uses `aws_profile` or the boto3 default chain. This task adds the explicit credential branch.

Note: this is for LLM-layer credentials set at **startup** (via env vars or `Agent(aws_access_key=...)`). Per-request credential injection to the LLM is not in scope.

### Step 1: Write the failing tests

```python
# tests/core/test_model_factory.py
"""Tests for ModelFactory credential routing."""
from unittest.mock import MagicMock, patch

import pytest

from dcaf.core.adapters.outbound.agno.model_factory import ModelConfig


@pytest.fixture
def base_config():
    return ModelConfig(
        model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        provider="bedrock",
        aws_region="us-east-1",
    )


class TestBedrockCredentialRouting:
    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    async def test_profile_creates_session_with_profile(self, mock_caching, mock_aioboto3, base_config):
        base_config.aws_profile = "my-profile"
        from dcaf.core.adapters.outbound.agno.model_factory import ModelFactory
        factory = ModelFactory(base_config)
        factory._model = None
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert call_kwargs.get("profile_name") == "my-profile"
        assert "aws_access_key_id" not in call_kwargs

    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    async def test_explicit_keys_create_session_with_credentials(self, mock_caching, mock_aioboto3, base_config):
        base_config.aws_access_key = "AKIAIOSFODNN7EXAMPLE"
        base_config.aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        from dcaf.core.adapters.outbound.agno.model_factory import ModelFactory
        factory = ModelFactory(base_config)
        factory._model = None
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert call_kwargs.get("aws_access_key_id") == "AKIAIOSFODNN7EXAMPLE"
        assert call_kwargs.get("aws_secret_access_key") == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        assert "profile_name" not in call_kwargs

    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    async def test_no_credentials_uses_default_chain(self, mock_caching, mock_aioboto3, base_config):
        from dcaf.core.adapters.outbound.agno.model_factory import ModelFactory
        factory = ModelFactory(base_config)
        factory._model = None
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert "profile_name" not in call_kwargs
        assert "aws_access_key_id" not in call_kwargs

    @patch("dcaf.core.adapters.outbound.agno.model_factory.aioboto3")
    @patch("dcaf.core.adapters.outbound.agno.model_factory.CachingAwsBedrock")
    async def test_profile_takes_precedence_over_keys(self, mock_caching, mock_aioboto3, base_config):
        base_config.aws_profile = "my-profile"
        base_config.aws_access_key = "AKIAIOSFODNN7EXAMPLE"
        base_config.aws_secret_key = "secret"
        from dcaf.core.adapters.outbound.agno.model_factory import ModelFactory
        factory = ModelFactory(base_config)
        factory._model = None
        await factory._create_bedrock_model()
        call_kwargs = mock_aioboto3.Session.call_args.kwargs
        assert call_kwargs.get("profile_name") == "my-profile"
        assert "aws_access_key_id" not in call_kwargs
```

### Step 2: Run to verify failure

```
pytest tests/core/test_model_factory.py -v
```
Expected: explicit-keys test and profile-precedence test FAIL.

### Step 3: Implement the fix

In `dcaf/core/adapters/outbound/agno/model_factory.py`, replace lines 165–175:

```python
# Create async session with the appropriate credential strategy
if config.aws_profile:
    logger.info(f"Agno: Using AWS profile '{config.aws_profile}' (region: {region})")
    async_session = aioboto3.Session(
        region_name=region,
        profile_name=config.aws_profile,
    )
elif config.aws_access_key and config.aws_secret_key:
    logger.info(f"Agno: Using explicit AWS key/secret (region: {region})")
    async_session = aioboto3.Session(
        region_name=region,
        aws_access_key_id=config.aws_access_key,
        aws_secret_access_key=config.aws_secret_key,
    )
else:
    logger.info(f"Agno: Using default AWS credential chain / IAM role (region: {region})")
    async_session = aioboto3.Session(region_name=region)
```

### Step 4: Run to verify pass

```
pytest tests/core/test_model_factory.py -v
```

### Step 5: Full suite

```
pytest -x && ruff check . && mypy dcaf/
```

### Step 6: Commit

```bash
git add dcaf/core/adapters/outbound/agno/model_factory.py tests/core/test_model_factory.py
git commit -m "fix(bedrock): use explicit AWS key/secret in aioboto3 session when provided"
```

---

## Task 5: Extract Kubeconfig Handling from K8s Agent

**Files:**
- Modify: `dcaf/agents/k8s_agent.py:56-76, 202-223`

The K8s agent currently does base64 decode + tempfile write in `process_messages()` (lines 62–76) and sets `KUBECONFIG` in the subprocess env (line 223). After Task 3, the platform_context dict passed to the agent already has `kubeconfig_path` set by `CredentialManager`. Replace the decode/write logic with a direct read from context.

Note: `dcaf/agents/` is legacy v1. Only modify what's necessary — no refactoring beyond the credential extraction.

### Step 1: Verify current behavior with a test (read first)

Read `dcaf/agents/k8s_agent.py` lines 56–80 fully before making changes. Confirm the `kubeconfig_path` variable is set from the base64 decode, then used at line 223.

### Step 2: Write a test that shows the new behavior

```python
# In the existing test file for k8s_agent (add to it, do not create new)
def test_k8s_agent_uses_kubeconfig_path_from_context_if_present():
    """If platform_context already has kubeconfig_path, use it directly."""
    # This tests the agent doesn't try to decode base64 when path is pre-populated
    from dcaf.agents.k8s_agent import K8sAgent
    agent = K8sAgent.__new__(K8sAgent)
    messages = {
        "messages": [
            {
                "role": "user",
                "content": "list pods",
                "platform_context": {"kubeconfig_path": "/tmp/pre_prepared_kube"},
            }
        ]
    }
    processed, _ = agent.process_messages(messages)
    # kubeconfig_path should be extracted directly, not from base64 kubeconfig
    # (This test structure will need adapting to whatever the real fixture pattern is)
```

Inspect the existing test file first to match its fixture pattern.

### Step 3: Replace base64 decode block in process_messages()

Replace lines 62–76 in `dcaf/agents/k8s_agent.py`:

**Before:**
```python
kubeconfig_path: str | None = None
for m in reversed(messages.get("messages", [])):
    if m.get("role") == "user":
        kube_b64 = (m.get("platform_context") or {}).get("kubeconfig")
        if kube_b64:
            try:
                tmp = tempfile.NamedTemporaryFile(delete=False)
                tmp.write(base64.b64decode(kube_b64))
                tmp.flush()
                os.chmod(tmp.name, 0o600)
                kubeconfig_path = tmp.name
            except Exception as e:
                logger.warning("Failed to set up kubeconfig: %s", e)
            break
```

**After:**
```python
kubeconfig_path: str | None = None
for m in reversed(messages.get("messages", [])):
    if m.get("role") == "user":
        ctx = m.get("platform_context") or {}
        # CredentialManager pre-populates kubeconfig_path; fall back to raw base64 for legacy callers
        kubeconfig_path = ctx.get("kubeconfig_path")
        if not kubeconfig_path:
            kube_b64 = ctx.get("kubeconfig")
            if kube_b64:
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False)  # noqa: SIM115
                    tmp.write(base64.b64decode(kube_b64))
                    tmp.flush()
                    os.chmod(tmp.name, 0o600)
                    kubeconfig_path = tmp.name
                except Exception as e:
                    logger.warning("Failed to set up kubeconfig: %s", e)
        break
```

Keep the legacy fallback so the agent works with raw base64 callers that don't go through `CredentialManager` (legacy v1 path).

### Step 4: Run tests

```
pytest -x && ruff check . && mypy dcaf/
```

### Step 5: Commit

```bash
git add dcaf/agents/k8s_agent.py
git commit -m "refactor(k8s-agent): prefer pre-prepared kubeconfig_path from CredentialManager"
```

---

## Task 6: Add DCAF_IS_LOCAL Flag and GCP EnvVar Documentation

**Files:**
- Modify: `dcaf/core/config.py`
- Modify: `tests/core/test_config.py`

### Step 1: Write the failing tests

Add to `tests/core/test_config.py`:

```python
class TestIsLocalFlag:
    def test_is_local_env_var_defined(self):
        from dcaf.core.config import EnvVars
        assert hasattr(EnvVars, "IS_LOCAL")
        assert EnvVars.IS_LOCAL == "DCAF_IS_LOCAL"

    def test_load_agent_config_is_local_from_env(self, monkeypatch):
        monkeypatch.setenv("DCAF_IS_LOCAL", "true")
        monkeypatch.setenv("DCAF_PROVIDER", "bedrock")
        from dcaf.core.config import load_agent_config
        config = load_agent_config()
        assert config.get("is_local") is True

    def test_load_agent_config_is_local_default_false(self, monkeypatch):
        monkeypatch.delenv("DCAF_IS_LOCAL", raising=False)
        monkeypatch.setenv("DCAF_PROVIDER", "bedrock")
        from dcaf.core.config import load_agent_config
        config = load_agent_config()
        assert config.get("is_local") is False

    def test_load_agent_config_is_local_override(self, monkeypatch):
        monkeypatch.delenv("DCAF_IS_LOCAL", raising=False)
        monkeypatch.setenv("DCAF_PROVIDER", "bedrock")
        from dcaf.core.config import load_agent_config
        config = load_agent_config(is_local=True)
        assert config.get("is_local") is True


class TestGCPEnvVarConstants:
    def test_google_application_credentials_env_var_defined(self):
        from dcaf.core.config import EnvVars
        assert hasattr(EnvVars, "GOOGLE_APPLICATION_CREDENTIALS")
        assert EnvVars.GOOGLE_APPLICATION_CREDENTIALS == "GOOGLE_APPLICATION_CREDENTIALS"
```

### Step 2: Run to verify failure

```
pytest tests/core/test_config.py::TestIsLocalFlag tests/core/test_config.py::TestGCPEnvVarConstants -v
```

### Step 3: Implement changes in config.py

In `EnvVars` class, add after `DISABLE_TOOL_FILTERING`:
```python
# Local development mode — enables env-var-based credential loading
# In production, credentials arrive via PlatformContext from the credential selector
IS_LOCAL = "DCAF_IS_LOCAL"
```

In the Google section of `EnvVars`, add:
```python
# Path to a service account JSON key file. Standard ADC env var.
# Set for local dev; on GCP, service account is auto-detected via metadata.
GOOGLE_APPLICATION_CREDENTIALS = "GOOGLE_APPLICATION_CREDENTIALS"
```

In `load_agent_config()`, after the behavior flags block:
```python
# Local dev flag
config["is_local"] = get_env(EnvVars.IS_LOCAL, False, cast=bool)
```

### Step 4: Run to verify pass

```
pytest tests/core/test_config.py -v
```

### Step 5: Full suite

```
pytest -x && ruff check . && mypy dcaf/
```

### Step 6: Commit

```bash
git add dcaf/core/config.py tests/core/test_config.py
git commit -m "feat(config): add DCAF_IS_LOCAL flag and document GOOGLE_APPLICATION_CREDENTIALS"
```

---

## Task 7: Update env.example

**Files:**
- Modify: `env.example` (or `.env.example` — check which name exists)

Add the new credential variables so local devs know what to set:

```bash
# Local development mode (set to true to use env-var credentials instead of injected)
DCAF_IS_LOCAL=true

# AWS credentials for local dev (Bedrock)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# GCP credentials for local dev (Vertex AI)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GOOGLE_CLOUD_PROJECT=your-project-id
```

### Step 1: Find and update the example file

```
ls /path/to/dcaf/*.example* dcaf/env* 2>/dev/null
```

### Step 2: Commit

```bash
git add env.example   # or .env.example
git commit -m "docs(config): document credential env vars in env.example"
```

---

---

## Task 8: MkDocs Documentation

**Files:**
- Create: `docs/guides/credential-management.md`
- Modify: `mkdocs.yml` (add nav entry)
- Modify: `docs/guides/working-with-bedrock.md` (add cross-reference + updated auth section)
- Modify: `docs/guides/working-with-gemini.md` (add cross-reference + updated auth section)
- Modify: `docs/guides/environment-configuration.md` (add new env vars)

CI gates on `mkdocs build --strict` — this task must pass that gate before the branch can merge.

### Step 1: Create the main credential management guide

Create `docs/guides/credential-management.md` with the following structure:

```markdown
# Credential Management

DCAF provides a unified `CredentialManager` service that prepares cloud credentials
from `PlatformContext` for any agent or tool — without duplicating decode-and-write
logic in each agent.

## How It Works

Credentials arrive in `PlatformContext` as raw values (base64-encoded kubeconfig,
AWS key/secret dicts, GCP service account JSON). Before the agent runs, `CredentialManager`
decodes and prepares them:

1. Writes temp files (kubeconfig, GCP JSON key) with `0o600` permissions
2. Extracts AWS key/secret into `PreparedCredentials` fields
3. Merges prepared values into the `platform_context` dict passed to tools
4. Deletes all temp files after the request completes

Tools read `kubeconfig_path` from `platform_context` (merged in by `CredentialManager`).
For per-scope AWS/GCP credentials, tools call `prepared.get_subprocess_env(scope_name)` —
never accessing the raw base64 data or mutating `os.environ`.

## AWS (Bedrock + CLI Tools)

### On AWS infrastructure (IAM role)
No credentials needed in `PlatformContext`. The default boto3 credential chain
(instance profile / EKS pod identity) handles authentication automatically.

### Explicit key/secret (local dev or cross-account) — Scope API
Pass an `aws` scope in `PlatformContext`:

```python
from dcaf.core.domain.value_objects.scope import Scope
from dcaf.core.domain.value_objects.platform_context import PlatformContext

context = PlatformContext().with_scope(
    Scope.aws(
        name="prod-aws",
        account_id="123456789012",
        access_key="AKIA...",
        secret_key="...",
        region="us-east-1",          # optional
        session_token="...",         # optional, for temporary credentials
    )
)
```

`CredentialManager` makes them available via:
```python
async with CredentialManager(context) as prepared:
    env = prepared.get_subprocess_env("prod-aws")
    subprocess.run(["aws", "s3", "ls"], env=env)
```

### Multi-account (Scope list — e.g. migration from AWS account A to account B)
```python
context = PlatformContext(scopes=(
    Scope.aws(name="source-account", account_id="111", access_key="AKIA_SRC", secret_key="..."),
    Scope.aws(name="target-account", account_id="222", access_key="AKIA_TGT", secret_key="..."),
))
# In tool:
src_env = prepared.get_subprocess_env("source-account")
tgt_env = prepared.get_subprocess_env("target-account")
```

### LLM layer (startup-time credentials)
For the Bedrock LLM itself, set credentials at startup via env vars or explicit kwargs:

```python
# Via env vars (local dev with DCAF_IS_LOCAL=true)
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Or explicit kwargs
agent = Agent(aws_access_key="AKIA...", aws_secret_key="...")
```

### Credential priority (AWS)
1. `aws_profile` (named profile) — highest priority
2. Explicit `aws_access_key` + `aws_secret_key`
3. Default boto3 chain (env vars → `~/.aws/credentials` → instance profile / IAM role)

## GCP (Vertex AI + CLI Tools)

### On GCP infrastructure (service account / Workload Identity)
No credentials needed. Application Default Credentials (ADC) auto-detects the
service account via the GCP metadata service. Set `GOOGLE_CLOUD_PROJECT` or let
DCAF auto-detect it.

### Service account JSON key (local dev)
Point ADC at a downloaded key file:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GOOGLE_CLOUD_PROJECT=my-project
```

### Injected JSON key (multi-tenant or runtime) — Scope API
Pass the base64-encoded JSON key content as a `gcp` scope:

```python
import base64, json
from dcaf.core.domain.value_objects.scope import Scope

key_json = json.dumps({...})  # service account JSON
context = PlatformContext().with_scope(
    Scope.gcp(
        name="prod-gcp",
        project_id="my-project",
        json_key=base64.b64encode(key_json.encode()).decode(),
    )
)
```

`CredentialManager` writes it to a secure temp file. Tools use
`prepared.get_subprocess_env("prod-gcp")` to get an env dict with
`GOOGLE_APPLICATION_CREDENTIALS` pointing to the temp file.

## Kubernetes (K8s / EKS / GKE)

### Scopes-based (production, multi-cluster)
Credentials arrive as scopes from Pranav's DuploCloud payload:
```python
# Wire format arrives from the orchestrator:
context = PlatformContext.from_dict({
    "scopes": [
        {"ProviderInfo": {"Type": "eks", "Name": "prod", "AccountId": "https://api.prod..."},
         "Credential": {"Data": {"token": "eyJ...", "base64certdata": "LS0t..."}}},
    ]
})
# CredentialManager builds a merged kubeconfig; kubeconfig_path is in platform_context
```

Tools inject `--context <scope.name>` for each kubectl/helm command. The context
name in kubeconfig matches `scope.name` exactly.

### Legacy: single base64 kubeconfig
```python
import base64

with open("~/.kube/config", "rb") as f:
    kubeconfig_b64 = base64.b64encode(f.read()).decode()

context = PlatformContext(kubeconfig=kubeconfig_b64)
```

`CredentialManager` writes it to a temp file and merges `kubeconfig_path`
into the platform context dict. kubectl tools set `KUBECONFIG` from this path
in their subprocess env dict — never via global `os.environ`.

## Future Providers

### Azure (coming)
The `PlatformContext` `_extra` dict can carry Azure credentials today.
When Azure support is added to `CredentialManager`, it will follow the
same pattern:

```python
context = PlatformContext()
context = context.with_extra(
    azure_credentials={
        "client_id": "...",
        "client_secret": "...",
        "tenant_id": "...",
    }
)
```

A dedicated `azure_credentials` field will be added to `PlatformContext`
and `CredentialManager` will gain an Azure preparation branch.

## Local Development

Set `DCAF_IS_LOCAL=true` to declare that credentials should come from
local environment variables rather than injected `PlatformContext` values.

```bash
DCAF_IS_LOCAL=true
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
GOOGLE_CLOUD_PROJECT=my-project
```

## Security Notes

- `CredentialManager` never mutates `os.environ`. Credentials are passed
  via subprocess env dicts and explicit SDK session objects.
- Temp files are created with `0o600` permissions and deleted on request exit.
- `PlatformContext.to_dict()` includes credential values — avoid logging it.
  Use `get_tracing_dict()` for safe log output.
```

### Step 2: Add nav entry to mkdocs.yml

In `mkdocs.yml`, add after the `Working with Google Vertex AI` entry:
```yaml
    - Credential Management: guides/credential-management.md
```

### Step 3: Update working-with-bedrock.md

Add a section near the top of the auth/configuration section:

```markdown
## Authentication

For a full overview of credential loading across all providers, see
[Credential Management](credential-management.md).

### On AWS infrastructure
No configuration needed — DCAF uses the default boto3 credential chain
(instance profile, EKS pod identity, IAM role).

### Local development / explicit credentials
See [Credential Management → AWS](credential-management.md#aws-bedrock-cli-tools).
```

### Step 4: Update working-with-gemini.md

Add a parallel section referencing the credential management guide:

```markdown
## Authentication

For a full overview of credential loading across all providers, see
[Credential Management](credential-management.md).

### On GCP infrastructure
No configuration needed — DCAF uses Application Default Credentials (ADC),
which auto-detects the service account via the GCP metadata service.

### Local development / service account key
See [Credential Management → GCP](credential-management.md#gcp-vertex-ai-cli-tools).
```

### Step 5: Update environment-configuration.md

Add the new variables to the relevant sections. Search for the existing AWS and Google sections and add:

**AWS section — add:**
```
DCAF_IS_LOCAL     | false  | Set to true for local dev; enables env-var credential loading
```

**Google section — add:**
```
GOOGLE_APPLICATION_CREDENTIALS | (none) | Path to a GCP service account JSON key file (standard ADC env var)
```

### Step 6: Verify docs build passes

```
mkdocs build --strict
```
Expected: build succeeds with no warnings or errors.

### Step 7: Commit

```bash
git add docs/guides/credential-management.md \
        docs/guides/working-with-bedrock.md \
        docs/guides/working-with-gemini.md \
        docs/guides/environment-configuration.md \
        mkdocs.yml
git commit -m "docs: add credential management guide covering AWS, GCP, K8s, and future Azure"
```

---

## Deferred / Not in Scope

| Item | Reason |
|------|--------|
| IAM role-via-key-and-secret (Boto3 assume_role) | Deferred per Andy |
| GCP explicit token approach (Kumar's pattern) | Research needed; `Scope.gcp()` provides the JSON key path; token-only auth may need a different credential type |
| Full multi-tenant credential injection (Pranav wiring) | `PlatformContext.scopes` is ready and matches the wire format; wiring through to ModelFactory for per-request LLM creds is a separate ticket (requires per-request model recreation) |
| Azure scopes | `Scope.from_dict()` will parse any `ProviderInfo.Type` — just add `Scope.azure()` factory and handle `"azure"` type in CredentialManager when the time comes |

---

## Execution Order

Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (each builds on the previous).

Tasks 1 and 4 are independent of each other — can be done in either order.
Tasks 2 and 3 depend on Task 1.
Task 5 depends on Tasks 2 and 3.
Tasks 6 and 7 are independent of all others.
Task 8 (docs) should be done last — it documents the final behavior of all prior tasks.

---

## Files Changed Summary

| File | Change |
|------|--------|
| `dcaf/core/domain/value_objects/scope.py` | New — `Scope` frozen dataclass with typed factories and wire-format serialization |
| `dcaf/core/domain/value_objects/platform_context.py` | Add `scopes: tuple[Scope, ...]`; update `to_dict`, `from_dict`, `with_extra`; add `with_scope()` + `scopes_for_type()` |
| `dcaf/core/models.py` | Add `scopes: list[dict] \| None = None` to legacy PlatformContext (eliminates k8s-ai-agent monkey-patch) |
| `dcaf/core/services/credential_manager.py` | New — scopes-aware `CredentialManager` + `PreparedCredentials` |
| `dcaf/core/application/services/agent_service.py` | Wrap `execute()` and `execute_stream()` with `CredentialManager` |
| `dcaf/core/adapters/outbound/agno/model_factory.py` | Add explicit key/secret branch in `_create_bedrock_model()` |
| `dcaf/agents/k8s_agent.py` | Prefer `kubeconfig_path` from context before falling back to base64 decode |
| `dcaf/core/config.py` | Add `IS_LOCAL`, `GOOGLE_APPLICATION_CREDENTIALS` to `EnvVars`; add `is_local` loading |
| `env.example` | Document new credential env vars |
| `tests/core/test_platform_context_vo.py` | New |
| `tests/core/services/test_credential_manager.py` | New |
| `tests/core/application/services/test_agent_service_credentials.py` | New |
| `tests/core/test_model_factory.py` | New |
| `tests/core/test_config.py` | Extended |
| `docs/guides/credential-management.md` | New — full guide: AWS, GCP, K8s, Azure stub, local dev |
| `docs/guides/working-with-bedrock.md` | Add auth section cross-referencing credential guide |
| `docs/guides/working-with-gemini.md` | Add auth section cross-referencing credential guide |
| `docs/guides/environment-configuration.md` | Add `DCAF_IS_LOCAL` and `GOOGLE_APPLICATION_CREDENTIALS` entries |
| `mkdocs.yml` | Add `Credential Management` nav entry |
