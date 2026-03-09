"""Tests for ApprovalPolicy domain service (dcaf.core.domain.services.approval_policy)."""

from dcaf.core.domain.services.approval_policy import ApprovalDecision, ApprovalPolicy
from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule
from dcaf.core.domain.value_objects.platform_context import PlatformContext

# =============================================================================
# Helper: simple ToolLike stub
# =============================================================================


class FakeTool:
    """Minimal implementation of ToolLike protocol."""

    def __init__(self, name: str, requires_approval: bool = False):
        self._name = name
        self._requires_approval = requires_approval

    @property
    def name(self) -> str:
        return self._name

    @property
    def requires_approval(self) -> bool:
        return self._requires_approval


# =============================================================================
# ApprovalDecision Tests
# =============================================================================


class TestApprovalDecision:
    def test_approved_factory(self):
        decision = ApprovalDecision.approved()
        assert decision.requires_approval is False
        assert decision.reason is None

    def test_needs_approval_factory(self):
        decision = ApprovalDecision.needs_approval("dangerous operation")
        assert decision.requires_approval is True
        assert decision.reason == "dangerous operation"

    def test_manual_creation(self):
        decision = ApprovalDecision(requires_approval=True, reason="custom")
        assert decision.requires_approval is True
        assert decision.reason == "custom"


# =============================================================================
# ApprovalPolicy.check Tests
# =============================================================================


class TestApprovalPolicyCheck:
    def test_tool_not_requiring_approval(self):
        policy = ApprovalPolicy()
        tool = FakeTool(name="list_pods", requires_approval=False)
        decision = policy.check(tool)
        assert decision.requires_approval is False

    def test_tool_requiring_approval(self):
        policy = ApprovalPolicy()
        tool = FakeTool(name="delete_pod", requires_approval=True)
        decision = policy.check(tool)
        assert decision.requires_approval is True
        assert "delete_pod" in decision.reason

    def test_check_with_context(self):
        policy = ApprovalPolicy()
        tool = FakeTool(name="restart", requires_approval=True)
        context = PlatformContext.from_dict({"tenant_name": "production"})
        decision = policy.check(tool, context)
        assert decision.requires_approval is True


# =============================================================================
# ApprovalPolicy.requires_approval Tests
# =============================================================================


class TestApprovalPolicyRequiresApproval:
    def test_returns_false_for_safe_tool(self):
        policy = ApprovalPolicy()
        tool = FakeTool(name="get_status", requires_approval=False)
        assert policy.requires_approval(tool) is False

    def test_returns_true_for_dangerous_tool(self):
        policy = ApprovalPolicy()
        tool = FakeTool(name="delete_all", requires_approval=True)
        assert policy.requires_approval(tool) is True


# =============================================================================
# ApprovalPolicy.filter_requiring_approval Tests
# =============================================================================


class TestFilterRequiringApproval:
    def test_empty_list(self):
        policy = ApprovalPolicy()
        result = policy.filter_requiring_approval([])
        assert result == []

    def test_none_require_approval(self):
        policy = ApprovalPolicy()
        tools = [
            FakeTool(name="list", requires_approval=False),
            FakeTool(name="get", requires_approval=False),
        ]
        result = policy.filter_requiring_approval(tools)
        assert result == []

    def test_some_require_approval(self):
        policy = ApprovalPolicy()
        safe = FakeTool(name="list", requires_approval=False)
        dangerous = FakeTool(name="delete", requires_approval=True)
        tools = [safe, dangerous]
        result = policy.filter_requiring_approval(tools)
        assert len(result) == 1
        assert result[0].name == "delete"

    def test_all_require_approval(self):
        policy = ApprovalPolicy()
        tools = [
            FakeTool(name="delete", requires_approval=True),
            FakeTool(name="destroy", requires_approval=True),
        ]
        result = policy.filter_requiring_approval(tools)
        assert len(result) == 2


# =============================================================================
# Baseline regression: behaviour when NO permissions in context (Task 1)
# These tests must pass BEFORE any implementation changes.
# =============================================================================


class TestApprovalPolicyNoPermissionsRegression:
    """Pins the existing tool-flag behaviour so refactors can't silently break it."""

    def test_no_context_safe_tool_approved(self):
        policy = ApprovalPolicy()
        tool = FakeTool("list_pods", requires_approval=False)
        decision = policy.check(tool)
        assert not decision.requires_approval

    def test_no_context_dangerous_tool_needs_approval(self):
        policy = ApprovalPolicy()
        tool = FakeTool("delete_pod", requires_approval=True)
        decision = policy.check(tool)
        assert decision.requires_approval
        assert "delete_pod" in decision.reason

    def test_empty_context_safe_tool_approved(self):
        policy = ApprovalPolicy()
        tool = FakeTool("list_pods", requires_approval=False)
        ctx = PlatformContext.empty()
        decision = policy.check(tool, ctx)
        assert not decision.requires_approval

    def test_empty_context_dangerous_tool_needs_approval(self):
        policy = ApprovalPolicy()
        tool = FakeTool("delete_pod", requires_approval=True)
        ctx = PlatformContext.empty()
        decision = policy.check(tool, ctx)
        assert decision.requires_approval

    def test_context_without_permissions_falls_back_to_tool_flag(self):
        policy = ApprovalPolicy()
        tool = FakeTool("scale", requires_approval=True)
        ctx = PlatformContext.from_dict({"tenant_name": "production"})
        decision = policy.check(tool, ctx)
        assert decision.requires_approval

    def test_approval_decision_approved_has_no_block(self):
        d = ApprovalDecision.approved()
        assert not d.requires_approval
        assert d.reason is None

    def test_approval_decision_needs_approval_has_reason(self):
        d = ApprovalDecision.needs_approval("too risky")
        assert d.requires_approval
        assert d.reason == "too risky"


# =============================================================================
# ApprovalDecision.deny() — Task 4
# =============================================================================


class TestApprovalDecisionDeny:
    def test_deny_creates_blocked_decision(self):
        d = ApprovalDecision.deny("global deny rule matched")
        assert d.is_blocked is True
        assert d.requires_approval is False
        assert d.reason == "global deny rule matched"

    def test_approved_is_not_blocked(self):
        d = ApprovalDecision.approved()
        assert d.is_blocked is False

    def test_needs_approval_is_not_blocked(self):
        d = ApprovalDecision.needs_approval("needs review")
        assert d.is_blocked is False


# =============================================================================
# ApprovalPolicy with layered permissions — Task 4
# =============================================================================


def _ctx_with_rules(*layers_data: dict) -> PlatformContext:
    """Helper: build a PlatformContext containing permission layers from dicts."""
    return PlatformContext.from_dict({"permissions": list(layers_data)})


GLOBAL_DENY_DELETE = {
    "layer": "global",
    "list": "deny",
    "rules": ["Bash(kubectl delete *)", "Bash(kubectl drain *)"],
}
GLOBAL_ALLOW_GET = {
    "layer": "global",
    "list": "allow",
    "rules": ["Bash(kubectl get *)", "Bash(kubectl describe *)"],
}
PROJECT_ALLOW_LOGS = {
    "layer": "project",
    "list": "allow",
    "rules": ["Bash(kubectl logs *)"],
}
AGENT_DENY_APPLY = {
    "layer": "agent",
    "list": "deny",
    "rules": ["Bash(kubectl apply *)"],
}
TICKET_ALLOW_SCALE = {
    "layer": "ticket",
    "list": "allow",
    "rules": ["Bash(kubectl scale deployment/worker --replicas=3)"],
}


class TestApprovalPolicyDenyChain:
    def test_global_deny_rule_blocks_tool(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, GLOBAL_ALLOW_GET)
        decision = policy.check(tool, ctx, "kubectl delete pods")
        assert decision.is_blocked
        assert "global" in decision.reason.lower()

    def test_deny_blocks_even_if_allow_rule_also_matches(self):
        """DENY chain runs entirely before ALLOW — deny wins."""
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, GLOBAL_ALLOW_GET)
        decision = policy.check(tool, ctx, "kubectl delete pods")
        assert decision.is_blocked

    def test_agent_deny_blocks_even_with_global_allow(self):
        """Lower-level DENY cannot be bypassed by higher-level ALLOW."""
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_ALLOW_GET, AGENT_DENY_APPLY)
        decision = policy.check(tool, ctx, "kubectl apply -f deployment.yaml")
        assert decision.is_blocked

    def test_deny_chain_order_global_before_project(self):
        """Global deny is checked before project deny."""
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        project_deny = {"layer": "project", "list": "deny", "rules": ["Bash(kubectl drain *)"]}
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, project_deny, GLOBAL_ALLOW_GET)
        decision = policy.check(tool, ctx, "kubectl delete pods")
        assert decision.is_blocked
        assert "global" in decision.reason.lower()


class TestApprovalPolicyAllowChain:
    def test_global_allow_rule_passes_tool(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, GLOBAL_ALLOW_GET)
        decision = policy.check(tool, ctx, "kubectl get pods")
        assert not decision.is_blocked
        assert not decision.requires_approval

    def test_project_allow_passes_after_global_deny_doesnt_match(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, PROJECT_ALLOW_LOGS)
        decision = policy.check(tool, ctx, "kubectl logs my-pod")
        assert not decision.is_blocked
        assert not decision.requires_approval

    def test_ticket_allow_rule_passes(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, TICKET_ALLOW_SCALE)
        decision = policy.check(tool, ctx, "kubectl scale deployment/worker --replicas=3")
        assert not decision.is_blocked
        assert not decision.requires_approval


class TestApprovalPolicyHITLFallback:
    def test_no_matching_rule_triggers_hitl(self):
        """Step 11: nothing matched → HITL."""
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        ctx = _ctx_with_rules(GLOBAL_DENY_DELETE, GLOBAL_ALLOW_GET)
        decision = policy.check(tool, ctx, "kubectl logs my-pod --tail=100")
        assert not decision.is_blocked
        assert decision.requires_approval

    def test_empty_permissions_list_falls_back_to_tool_flag(self):
        """Empty permissions → preserve legacy behaviour."""
        policy = ApprovalPolicy()
        tool = FakeTool("delete_all", requires_approval=True)
        ctx = PlatformContext.from_dict({"permissions": []})
        decision = policy.check(tool, ctx)
        assert decision.requires_approval
        assert not decision.is_blocked


class TestApprovalPolicyDocumentExample:
    """End-to-end test matching the step-by-step example from the design document."""

    def _build_context(self) -> PlatformContext:
        return PlatformContext.from_dict(
            {
                "permissions": [
                    {
                        "layer": "global",
                        "list": "deny",
                        "rules": [
                            "Bash(kubectl delete *)",
                            "Bash(kubectl drain *)",
                            "Bash(kubectl exec *)",
                            "Bash(aws s3 rb *)",
                            "Bash(aws iam delete-*)",
                        ],
                    },
                    {
                        "layer": "project",
                        "list": "deny",
                        "rules": [
                            "Bash(kubectl apply -f * --namespace=production)",
                            "Bash(kubectl rollout undo *)",
                        ],
                    },
                    {
                        "layer": "agent",
                        "list": "deny",
                        "rules": ["Bash(kubectl apply *)", "Bash(aws iam attach-role-policy *)"],
                    },
                    {
                        "layer": "skill",
                        "list": "deny",
                        "rules": ["Bash(kubectl delete namespace *)"],
                    },
                    {
                        "layer": "ticket",
                        "list": "deny",
                        "rules": ["Bash(kubectl get secret db-credentials *)"],
                    },
                    {
                        "layer": "global",
                        "list": "allow",
                        "rules": [
                            "Bash(kubectl get *)",
                            "Bash(kubectl describe *)",
                            "Bash(aws s3 ls *)",
                            "Bash(* --version)",
                            "Bash(* --help *)",
                        ],
                    },
                    {
                        "layer": "project",
                        "list": "allow",
                        "rules": [
                            "Bash(kubectl rollout status *)",
                            "Bash(kubectl top *)",
                            "Bash(kubectl logs *)",
                        ],
                    },
                    {
                        "layer": "agent",
                        "list": "allow",
                        "rules": [
                            "Bash(kubectl logs * --tail=*)",
                            "Bash(kubectl get events *)",
                            "Bash(aws ec2 describe-security-groups *)",
                        ],
                    },
                    {
                        "layer": "skill",
                        "list": "allow",
                        "rules": [
                            "Bash(kubectl apply -f * --namespace=staging)",
                            "Bash(kubectl scale deployment/* --replicas=*)",
                            "Bash(kubectl rollout restart *)",
                        ],
                    },
                    {
                        "layer": "ticket",
                        "list": "allow",
                        "rules": ["Bash(kubectl scale deployment/worker --replicas=3)"],
                    },
                ]
            }
        )

    def test_kubectl_get_pods_is_allowed(self):
        """From the document example: kubectl get pods → ALLOWED at global allow step 6."""
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        decision = policy.check(tool, self._build_context(), "kubectl get pods")
        assert not decision.is_blocked
        assert not decision.requires_approval

    def test_kubectl_delete_is_blocked(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        decision = policy.check(tool, self._build_context(), "kubectl delete pods")
        assert decision.is_blocked

    def test_kubectl_exec_is_blocked(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        decision = policy.check(tool, self._build_context(), "kubectl exec -it my-pod -- bash")
        assert decision.is_blocked

    def test_unknown_command_triggers_hitl(self):
        policy = ApprovalPolicy()
        tool = FakeTool("Bash", requires_approval=False)
        decision = policy.check(tool, self._build_context(), "helm upgrade my-chart ./chart")
        assert not decision.is_blocked
        assert decision.requires_approval
