"""Tests for PermissionRule and PermissionLayer value objects."""

import pytest

from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule


class TestPermissionRuleParsing:
    def test_parses_tool_name_and_arg_pattern(self):
        rule = PermissionRule("Bash(kubectl delete *)")
        assert rule.tool_name == "Bash"
        assert rule.argument_pattern == "kubectl delete *"

    def test_parses_rule_without_parens(self):
        rule = PermissionRule("kubectl")
        assert rule.tool_name == "kubectl"
        assert rule.argument_pattern is None

    def test_parses_rule_with_spaces_in_pattern(self):
        rule = PermissionRule("Bash(aws s3 rb *)")
        assert rule.tool_name == "Bash"
        assert rule.argument_pattern == "aws s3 rb *"

    def test_raw_preserved(self):
        rule = PermissionRule("Bash(kubectl get *)")
        assert rule.raw == "Bash(kubectl get *)"


class TestPermissionRuleMatches:
    def test_matches_tool_name_case_insensitive(self):
        rule = PermissionRule("bash")
        assert rule.matches("bash")
        assert rule.matches("Bash")
        assert rule.matches("BASH")

    def test_no_match_different_tool_name(self):
        rule = PermissionRule("Bash(kubectl get *)")
        assert not rule.matches("kubectl", "get pods")

    def test_matches_tool_and_argument_glob(self):
        rule = PermissionRule("Bash(kubectl delete *)")
        assert rule.matches("Bash", "kubectl delete pods")
        assert rule.matches("Bash", "kubectl delete deployments/api")

    def test_no_match_argument_does_not_fit_pattern(self):
        rule = PermissionRule("Bash(kubectl delete *)")
        assert not rule.matches("Bash", "kubectl get pods")

    def test_no_arg_pattern_matches_any_argument(self):
        rule = PermissionRule("kubectl")
        assert rule.matches("kubectl")
        assert rule.matches("kubectl", "get pods")
        assert rule.matches("kubectl", "delete everything")

    def test_arg_pattern_present_no_argument_given(self):
        rule = PermissionRule("Bash(kubectl exec *)")
        assert not rule.matches("Bash", None)

    def test_wildcard_only_pattern(self):
        rule = PermissionRule("Bash(*)")
        assert rule.matches("Bash", "kubectl get pods")
        assert rule.matches("Bash", "aws s3 ls")

    def test_double_wildcard_in_middle(self):
        rule = PermissionRule("Bash(* --version)")
        assert rule.matches("Bash", "kubectl --version")
        assert rule.matches("Bash", "helm --version")
        assert not rule.matches("Bash", "kubectl get pods")

    def test_argument_matching_is_case_insensitive(self):
        rule = PermissionRule("Bash(kubectl get *)")
        assert rule.matches("Bash", "KUBECTL GET pods")


class TestPermissionLayerFromDict:
    def test_parses_layer_list_rules(self):
        data = {
            "layer": "global",
            "list": "deny",
            "rules": ["Bash(kubectl delete *)", "Bash(kubectl drain *)"],
        }
        layer = PermissionLayer.from_dict(data)
        assert layer.layer == "global"
        assert layer.list == "deny"
        assert len(layer.rules) == 2
        assert layer.rules[0].tool_name == "Bash"

    def test_empty_rules(self):
        data = {"layer": "ticket", "list": "allow", "rules": []}
        layer = PermissionLayer.from_dict(data)
        assert layer.rules == ()

    def test_to_dict_roundtrip(self):
        data = {
            "layer": "project",
            "list": "deny",
            "rules": ["Bash(kubectl exec *)"],
        }
        layer = PermissionLayer.from_dict(data)
        assert layer.to_dict() == data
