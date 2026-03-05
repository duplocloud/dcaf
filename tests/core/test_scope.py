"""Tests for the Scope value object."""

import pytest

from dcaf.core.domain.value_objects.scope import Scope


class TestScopeFactories:
    def test_eks_factory(self):
        s = Scope.eks(
            name="prod", server="https://api.example.com", token="tok123", ca_cert="cert=="
        )
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
            name="prod-aws",
            account_id="123",
            access_key="AKIA",
            secret_key="sec",
            region="us-east-1",
            session_token="tok",
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
        wire = {
            "ProviderInfo": {"Type": "EKS", "Name": "x", "AccountId": ""},
            "Credential": {"Data": {}},
        }
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
