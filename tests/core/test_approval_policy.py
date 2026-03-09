"""Tests for ApprovalPolicy domain service (dcaf.core.domain.services.approval_policy)."""

from dcaf.core.domain.services.approval_policy import ApprovalDecision, ApprovalPolicy
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
