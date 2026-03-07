"""Tests for CredentialManager service (scopes-based)."""

import base64
import os

import yaml

from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.domain.value_objects.scope import Scope
from dcaf.core.services.credential_manager import CredentialManager, PreparedCredentials

FAKE_KUBECONFIG = b"apiVersion: v1\nclusters: []\n"
FAKE_GCP_JSON = b'{"type": "service_account", "project_id": "my-project"}'
FAKE_TOKEN = "eyJhbGciOiJSUzI1NiJ9.fake"
FAKE_CERT = base64.b64encode(
    b"-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"
).decode()


class TestPreparedCredentials:
    def test_get_subprocess_env_no_credentials(self, monkeypatch):
        monkeypatch.delenv("KUBECONFIG", raising=False)
        monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
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
            _scope_envs={
                "prod-aws": {"AWS_ACCESS_KEY_ID": "AKIA123", "AWS_SECRET_ACCESS_KEY": "sec"}
            },
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
        s = Scope.eks(
            name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT
        )
        ctx = PlatformContext(scopes=(s,))
        async with CredentialManager(ctx) as prepared:
            assert prepared.kubeconfig_path is not None
            assert os.path.exists(prepared.kubeconfig_path)

    async def test_kubeconfig_contains_one_context_per_scope(self):
        s1 = Scope.eks(
            name="prod", server="https://prod.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT
        )
        s2 = Scope.eks(
            name="staging",
            server="https://staging.example.com",
            token=FAKE_TOKEN,
            ca_cert=FAKE_CERT,
        )
        ctx = PlatformContext(scopes=(s1, s2))
        async with CredentialManager(ctx) as prepared:
            with open(prepared.kubeconfig_path) as f:
                kubeconfig = yaml.safe_load(f.read())
            context_names = {c["name"] for c in kubeconfig["contexts"]}
            assert "prod" in context_names
            assert "staging" in context_names

    async def test_kubeconfig_file_has_restricted_permissions(self):
        s = Scope.eks(
            name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT
        )
        ctx = PlatformContext(scopes=(s,))
        async with CredentialManager(ctx) as prepared:
            mode = oct(os.stat(prepared.kubeconfig_path).st_mode)[-3:]
            assert mode == "600"

    async def test_kubeconfig_tempfile_deleted_on_exit(self):
        s = Scope.eks(
            name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT
        )
        ctx = PlatformContext(scopes=(s,))
        path = None
        async with CredentialManager(ctx) as prepared:
            path = prepared.kubeconfig_path
        assert path is not None
        assert not os.path.exists(path)

    async def test_non_k8s_scopes_not_in_kubeconfig(self):
        """AWS scope does not pollute the kubeconfig."""
        k8s = Scope.eks(
            name="prod", server="https://api.example.com", token=FAKE_TOKEN, ca_cert=FAKE_CERT
        )
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
        s = Scope.aws(
            name="prod-aws",
            account_id="123",
            access_key="AKIA123",
            secret_key="sec",
            region="us-east-1",
        )
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


class TestCredentialManagerKubeconfigPrecedence:
    async def test_prepopulated_kubeconfig_path_wins_over_base64(self):
        """kubeconfig_path in extra takes precedence — no temp file is written."""
        kube_b64 = base64.b64encode(FAKE_KUBECONFIG).decode()
        ctx = PlatformContext.from_dict(
            {"kubeconfig": kube_b64, "kubeconfig_path": "/tmp/pre-populated.yaml"}
        )
        async with CredentialManager(ctx) as prepared:
            assert prepared.kubeconfig_path == "/tmp/pre-populated.yaml"

    async def test_prepopulated_kubeconfig_path_no_tempfile_written(self):
        """When kubeconfig_path is pre-populated, the base64 kubeconfig is not decoded."""
        kube_b64 = base64.b64encode(FAKE_KUBECONFIG).decode()
        ctx = PlatformContext.from_dict(
            {"kubeconfig": kube_b64, "kubeconfig_path": "/tmp/pre-populated.yaml"}
        )
        async with CredentialManager(ctx) as prepared:
            # Path is the pre-populated one, not a temp file
            assert prepared.kubeconfig_path is not None
            assert "kubeconfig_" not in prepared.kubeconfig_path
