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


class TestPlatformContextPermissions:
    def test_empty_context_has_no_permissions(self):
        ctx = PlatformContext.empty()
        assert ctx.permissions == ()

    def test_from_dict_parses_permissions(self):
        data = {
            "permissions": [
                {
                    "layer": "global",
                    "list": "deny",
                    "rules": ["Bash(kubectl delete *)"],
                },
                {
                    "layer": "global",
                    "list": "allow",
                    "rules": ["Bash(kubectl get *)"],
                },
            ]
        }
        ctx = PlatformContext.from_dict(data)
        assert len(ctx.permissions) == 2
        assert ctx.permissions[0].layer == "global"
        assert ctx.permissions[0].list == "deny"
        assert ctx.permissions[1].list == "allow"

    def test_from_dict_no_permissions_key(self):
        ctx = PlatformContext.from_dict({"tenant_name": "prod"})
        assert ctx.permissions == ()

    def test_to_dict_includes_permissions(self):
        from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule

        layer = PermissionLayer(
            layer="global",
            list="deny",
            rules=(PermissionRule("Bash(kubectl delete *)"),),
        )
        ctx = PlatformContext(permissions=(layer,))
        d = ctx.to_dict()
        assert "permissions" in d
        assert d["permissions"][0]["layer"] == "global"
        assert d["permissions"][0]["rules"] == ["Bash(kubectl delete *)"]

    def test_to_dict_omits_permissions_when_empty(self):
        ctx = PlatformContext.empty()
        assert "permissions" not in ctx.to_dict()

    def test_with_tracing_carries_permissions(self):
        from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule

        layer = PermissionLayer(
            layer="global", list="deny", rules=(PermissionRule("Bash(rm -rf *)"),)
        )
        ctx = PlatformContext(permissions=(layer,))
        ctx2 = ctx.with_tracing(user_id="alice")
        assert ctx2.permissions == ctx.permissions

    def test_with_extra_carries_permissions(self):
        from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule

        layer = PermissionLayer(
            layer="global", list="deny", rules=(PermissionRule("Bash(rm -rf *)"),)
        )
        ctx = PlatformContext(permissions=(layer,))
        ctx2 = ctx.with_extra(foo="bar")
        assert ctx2.permissions == ctx.permissions

    def test_with_scope_carries_permissions(self):
        from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule

        layer = PermissionLayer(
            layer="global", list="deny", rules=(PermissionRule("Bash(rm -rf *)"),)
        )
        ctx = PlatformContext(permissions=(layer,))
        scope = Scope.from_dict(
            {
                "ProviderInfo": {"Type": "eks", "Name": "prod", "AccountId": "https://api"},
                "Credential": {"Data": {"token": "t", "base64certdata": "c"}},
            }
        )
        ctx2 = ctx.with_scope(scope)
        assert ctx2.permissions == ctx.permissions

    def test_from_dict_roundtrip(self):
        data = {
            "tenant_name": "prod",
            "permissions": [
                {"layer": "global", "list": "deny", "rules": ["Bash(kubectl delete *)"]},
            ],
        }
        ctx = PlatformContext.from_dict(data)
        result = ctx.to_dict()
        assert result["tenant_name"] == "prod"
        assert result["permissions"][0]["layer"] == "global"
