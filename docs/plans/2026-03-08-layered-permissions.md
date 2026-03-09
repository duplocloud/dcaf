# Layered Permission Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the multi-layer deny/allow permission engine described in `docs/plans/Agent Actions Permissions-20260308230639.md` so that a `permissions` list in `platform_context` drives tool-call authorization (Global → Project → Agent → Skill → Ticket deny chain, then allow chain, then HITL fallback).

**Architecture:** A new `PermissionRule` / `PermissionLayer` value-object pair parses the wire format. `PlatformContext` grows a `permissions` field. `ApprovalPolicy.check()` (already wired into `AgentService`) evaluates the 10-step chain using `fnmatch` glob matching; a new `ApprovalDecision.deny()` verdict represents a hard block. `AgentService._process_response` is extended to handle blocked tool calls by calling `tool_call.reject()`. All changes are backwards-compatible: when `permissions` is empty the existing `requires_approval` flag behaviour is preserved unchanged.

**Tech Stack:** Python 3.11+, `fnmatch` (stdlib), `dataclasses`, `re`, pytest-asyncio, Ruff, MyPy

---

## Background: how the existing code fits together

```
AgentRequest.context (dict)
  └─ AgentService.execute()
       ├─ request.get_platform_context() → PlatformContext
       └─ _process_response(tools, context)
            ├─ for each tool_call from runtime:
            │    requires_approval = tool.requires_approval  ← currently hard-coded
            │    if requires_approval: request_tool_approval()
            │    else:                 auto_approve() + execute()
            └─ (self._policy is stored but NOT called — that's the gap)
```

After this plan:

```
_process_response(tools, context)
  ├─ for each tool_call:
  │    decision = self._policy.check(tool, context, tool_input)
  │    if decision.is_blocked:   tool_call.reject()        ← NEW
  │    elif decision.requires_approval: request_approval() ← unchanged
  │    else:                     auto_approve() + execute() ← unchanged
```

**Key files:**

| File | Role |
|------|------|
| `dcaf/core/domain/value_objects/permission.py` | NEW — PermissionRule, PermissionLayer |
| `dcaf/core/domain/value_objects/platform_context.py` | ADD permissions field |
| `dcaf/core/domain/services/approval_policy.py` | ADD deny() verdict + layered evaluation |
| `dcaf/core/application/services/agent_service.py` | WIRE policy.check() into _process_response |
| `dcaf/core/domain/value_objects/__init__.py` | EXPORT new types |
| `dcaf/core/domain/__init__.py` | EXPORT new types |

**Test files:**

| File | Role |
|------|------|
| `tests/core/domain/value_objects/test_permission.py` | NEW |
| `tests/core/test_approval_policy.py` | EXTEND (new layered tests) |
| `tests/core/test_platform_context_vo.py` | EXTEND (permissions field) |
| `tests/core/application/services/test_agent_service_permissions.py` | NEW |

---

## Task 1: Baseline regression tests — lock in existing ApprovalPolicy behaviour

Before touching any implementation code, write tests that pin the current behaviour.
These must pass NOW (before any other task). They are insurance for Tasks 4–5.

**Files:**
- Modify: `tests/core/test_approval_policy.py`

**Step 1: Add baseline tests at the bottom of `tests/core/test_approval_policy.py`**

```python
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
```

**Step 2: Run tests to confirm they all pass before any code changes**

```bash
pytest tests/core/test_approval_policy.py -v
```

Expected: All tests PASS (including the 11 that already exist + 7 new ones).

**Step 3: Commit**

```bash
git add tests/core/test_approval_policy.py
git commit -m "test(permissions): add baseline regression tests for ApprovalPolicy"
```

---

## Task 2: PermissionRule and PermissionLayer value objects

**Files:**
- Create: `dcaf/core/domain/value_objects/permission.py`
- Create: `tests/core/domain/value_objects/test_permission.py`

> Note: `tests/core/domain/value_objects/` directory does not exist yet — create it with a blank `__init__.py`.

**Step 1: Write the failing tests first**

Create `tests/core/domain/__init__.py` (empty), `tests/core/domain/value_objects/__init__.py` (empty), then create `tests/core/domain/value_objects/test_permission.py`:

```python
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
```

**Step 2: Run tests to confirm they fail (module not found)**

```bash
pytest tests/core/domain/value_objects/test_permission.py -v
```

Expected: `ModuleNotFoundError: No module named 'dcaf.core.domain.value_objects.permission'`

**Step 3: Create `dcaf/core/domain/value_objects/permission.py`**

```python
"""Permission value objects for layered deny/allow rule evaluation."""

import fnmatch
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionRule:
    """
    A single permission rule in the format ``ToolName(argument pattern)``.

    Examples::

        PermissionRule("Bash(kubectl delete *)")   # blocks kubectl delete commands
        PermissionRule("Bash(kubectl get *)")      # allows kubectl get commands
        PermissionRule("kubectl")                  # matches any kubectl call

    Matching is case-insensitive for both tool name and argument pattern.
    Argument patterns use standard glob syntax (``*`` and ``?``).
    """

    raw: str
    _tool_name: str = field(init=False, repr=False, compare=False)
    _arg_pattern: str | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        m = re.match(r"^([^(]+)\((.+)\)$", self.raw)
        if m:
            object.__setattr__(self, "_tool_name", m.group(1).strip())
            object.__setattr__(self, "_arg_pattern", m.group(2).strip())
        else:
            object.__setattr__(self, "_tool_name", self.raw.strip())
            object.__setattr__(self, "_arg_pattern", None)

    @property
    def tool_name(self) -> str:
        """Tool name extracted from the rule (part before the parenthesis)."""
        return self._tool_name

    @property
    def argument_pattern(self) -> str | None:
        """Glob pattern for the tool argument, or None if rule has no parentheses."""
        return self._arg_pattern

    def matches(self, tool_name: str, argument: str | None = None) -> bool:
        """
        Return True if this rule matches the given tool call.

        Args:
            tool_name: Name of the tool being called.
            argument:  Primary argument string to match against the pattern.
        """
        if tool_name.lower() != self._tool_name.lower():
            return False
        if self._arg_pattern is None:
            return True
        if argument is None:
            return False
        return fnmatch.fnmatch(str(argument).lower(), self._arg_pattern.lower())


@dataclass(frozen=True)
class PermissionLayer:
    """
    One layer in the permission evaluation chain.

    Attributes:
        layer: One of ``"global"``, ``"project"``, ``"agent"``, ``"skill"``, ``"ticket"``.
        list:  Either ``"deny"`` or ``"allow"``.
        rules: Ordered tuple of :class:`PermissionRule` objects.
    """

    layer: str
    list: str
    rules: tuple[PermissionRule, ...]

    def __post_init__(self) -> None:
        # Allow callers to pass a plain list of rule strings
        if isinstance(self.rules, (list, tuple)):
            coerced = tuple(
                r if isinstance(r, PermissionRule) else PermissionRule(r) for r in self.rules
            )
            object.__setattr__(self, "rules", coerced)

    @classmethod
    def from_dict(cls, data: dict) -> "PermissionLayer":
        """Parse from the platform_context wire format."""
        return cls(
            layer=data.get("layer", ""),
            list=data.get("list", ""),
            rules=tuple(PermissionRule(r) for r in data.get("rules", [])),
        )

    def to_dict(self) -> dict:
        """Serialize back to wire format."""
        return {
            "layer": self.layer,
            "list": self.list,
            "rules": [r.raw for r in self.rules],
        }
```

**Step 4: Run tests to confirm they pass**

```bash
pytest tests/core/domain/value_objects/test_permission.py -v
```

Expected: All PASS.

**Step 5: Commit**

```bash
git add dcaf/core/domain/value_objects/permission.py \
        tests/core/domain/__init__.py \
        tests/core/domain/value_objects/__init__.py \
        tests/core/domain/value_objects/test_permission.py
git commit -m "feat(permissions): add PermissionRule and PermissionLayer value objects"
```

---

## Task 3: Add `permissions` field to PlatformContext

**Files:**
- Modify: `dcaf/core/domain/value_objects/platform_context.py`
- Modify: `dcaf/core/domain/value_objects/__init__.py`
- Modify: `dcaf/core/domain/__init__.py`
- Modify: `tests/core/test_platform_context_vo.py`

**Step 1: Write the failing tests**

Add this class at the bottom of `tests/core/test_platform_context_vo.py`:

```python
# Add this import at the top of the file (with the other imports):
# from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule


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
        layer = PermissionLayer(layer="global", list="deny",
                                rules=(PermissionRule("Bash(rm -rf *)"),))
        ctx = PlatformContext(permissions=(layer,))
        ctx2 = ctx.with_tracing(user_id="alice")
        assert ctx2.permissions == ctx.permissions

    def test_with_extra_carries_permissions(self):
        from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule
        layer = PermissionLayer(layer="global", list="deny",
                                rules=(PermissionRule("Bash(rm -rf *)"),))
        ctx = PlatformContext(permissions=(layer,))
        ctx2 = ctx.with_extra(foo="bar")
        assert ctx2.permissions == ctx.permissions

    def test_with_scope_carries_permissions(self):
        from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule
        from dcaf.core.domain.value_objects.scope import Scope
        layer = PermissionLayer(layer="global", list="deny",
                                rules=(PermissionRule("Bash(rm -rf *)"),))
        ctx = PlatformContext(permissions=(layer,))
        scope = Scope.from_dict({
            "ProviderInfo": {"Type": "eks", "Name": "prod", "AccountId": "https://api"},
            "Credential": {"Data": {"token": "t", "base64certdata": "c"}},
        })
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
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/core/test_platform_context_vo.py::TestPlatformContextPermissions -v
```

Expected: FAIL — `TypeError: PlatformContext.__init__() got an unexpected keyword argument 'permissions'`

**Step 3: Add `permissions` to `PlatformContext`**

In `dcaf/core/domain/value_objects/platform_context.py`:

1. Add import at the top (after the `Scope` import):
```python
from dcaf.core.domain.value_objects.permission import PermissionLayer
```

2. Add field after the `scopes` field:
```python
    # Layered deny/allow permission rules
    permissions: tuple["PermissionLayer", ...] = ()
```

3. In `__post_init__`, add after the scopes coercion:
```python
        # Convert permissions list to tuple for immutability
        if isinstance(self.permissions, list):
            object.__setattr__(self, "permissions", tuple(self.permissions))
```

4. In `with_extra`, `with_tracing`, and `with_scope` — each creates a new `PlatformContext(...)`. Add `permissions=self.permissions,` to each constructor call. There are 3 methods; each one manually lists all fields. Add the new field to all three.

5. In `to_dict`, add before `result.update(self.extra)`:
```python
        if self.permissions:
            result["permissions"] = [layer.to_dict() for layer in self.permissions]
```

6. In `from_dict`, add `"permissions"` to `known_keys`:
```python
        known_keys = {
            ...
            "scopes",
            "permissions",   # ← add this
        }
```

7. In `from_dict`, add parsing after the scopes parsing:
```python
        # Parse permissions from wire format
        if "permissions" in known:
            raw_perms = known["permissions"]
            known["permissions"] = (
                tuple(PermissionLayer.from_dict(p) for p in raw_perms)
                if isinstance(raw_perms, list)
                else ()
            )
```

**Step 4: Export from `__init__.py` files**

In `dcaf/core/domain/value_objects/__init__.py`, add:
```python
from .permission import PermissionLayer, PermissionRule
```
And add `"PermissionLayer"`, `"PermissionRule"` to `__all__`.

In `dcaf/core/domain/__init__.py`, add:
```python
from .value_objects import PermissionLayer, PermissionRule
```
And add them to `__all__`.

**Step 5: Run the new tests**

```bash
pytest tests/core/test_platform_context_vo.py -v
```

Expected: All PASS (existing + new).

**Step 6: Run the full suite to catch regressions**

```bash
pytest -x -q
```

Expected: All pass.

**Step 7: Commit**

```bash
git add dcaf/core/domain/value_objects/permission.py \
        dcaf/core/domain/value_objects/platform_context.py \
        dcaf/core/domain/value_objects/__init__.py \
        dcaf/core/domain/__init__.py \
        tests/core/test_platform_context_vo.py
git commit -m "feat(permissions): add permissions field to PlatformContext"
```

---

## Task 4: Add `deny()` verdict and layered rule evaluation to `ApprovalPolicy`

**Files:**
- Modify: `dcaf/core/domain/services/approval_policy.py`
- Modify: `tests/core/test_approval_policy.py`

**Step 1: Write the failing tests**

Add these classes at the bottom of `tests/core/test_approval_policy.py`.

Add this import at the top:
```python
from dcaf.core.domain.value_objects.permission import PermissionLayer, PermissionRule
```

```python
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
    "layer": "global", "list": "deny",
    "rules": ["Bash(kubectl delete *)", "Bash(kubectl drain *)"],
}
GLOBAL_ALLOW_GET = {
    "layer": "global", "list": "allow",
    "rules": ["Bash(kubectl get *)", "Bash(kubectl describe *)"],
}
PROJECT_ALLOW_LOGS = {
    "layer": "project", "list": "allow",
    "rules": ["Bash(kubectl logs *)"],
}
AGENT_DENY_APPLY = {
    "layer": "agent", "list": "deny",
    "rules": ["Bash(kubectl apply *)"],
}
TICKET_ALLOW_SCALE = {
    "layer": "ticket", "list": "allow",
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
        # both deny-delete and allow-get present; delete matches deny
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
        # matches global deny first
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
        # "kubectl logs" matches neither deny-delete nor allow-get
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
        return PlatformContext.from_dict({
            "permissions": [
                {"layer": "global",  "list": "deny",  "rules": [
                    "Bash(kubectl delete *)", "Bash(kubectl drain *)",
                    "Bash(kubectl exec *)", "Bash(aws s3 rb *)", "Bash(aws iam delete-*)"]},
                {"layer": "project", "list": "deny",  "rules": [
                    "Bash(kubectl apply -f * --namespace=production)",
                    "Bash(kubectl rollout undo *)"]},
                {"layer": "agent",   "list": "deny",  "rules": [
                    "Bash(kubectl apply *)", "Bash(aws iam attach-role-policy *)"]},
                {"layer": "skill",   "list": "deny",  "rules": [
                    "Bash(kubectl delete namespace *)"]},
                {"layer": "ticket",  "list": "deny",  "rules": [
                    "Bash(kubectl get secret db-credentials *)"]},
                {"layer": "global",  "list": "allow", "rules": [
                    "Bash(kubectl get *)", "Bash(kubectl describe *)",
                    "Bash(aws s3 ls *)", "Bash(* --version)", "Bash(* --help *)"]},
                {"layer": "project", "list": "allow", "rules": [
                    "Bash(kubectl rollout status *)", "Bash(kubectl top *)",
                    "Bash(kubectl logs *)"]},
                {"layer": "agent",   "list": "allow", "rules": [
                    "Bash(kubectl logs * --tail=*)", "Bash(kubectl get events *)",
                    "Bash(aws ec2 describe-security-groups *)"]},
                {"layer": "skill",   "list": "allow", "rules": [
                    "Bash(kubectl apply -f * --namespace=staging)",
                    "Bash(kubectl scale deployment/* --replicas=*)",
                    "Bash(kubectl rollout restart *)"]},
                {"layer": "ticket",  "list": "allow", "rules": [
                    "Bash(kubectl scale deployment/worker --replicas=3)"]},
            ]
        })

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
```

**Step 2: Run the new tests to confirm they fail**

```bash
pytest tests/core/test_approval_policy.py::TestApprovalDecisionDeny \
       tests/core/test_approval_policy.py::TestApprovalPolicyDenyChain -v
```

Expected: FAIL — `AttributeError: type object 'ApprovalDecision' has no attribute 'deny'` and `AttributeError: 'ApprovalDecision' has no attribute 'is_blocked'`

**Step 3: Update `dcaf/core/domain/services/approval_policy.py`**

Replace the full file with:

```python
"""Approval policy domain service."""

import fnmatch
from dataclasses import dataclass, field
from typing import Any

from ..value_objects.platform_context import PlatformContext

_LAYER_ORDER = ("global", "project", "agent", "skill", "ticket")


class ToolLike:
    """Protocol for tool-like objects that have approval properties."""

    @property
    def name(self) -> str: ...

    @property
    def requires_approval(self) -> bool: ...


@dataclass
class ApprovalDecision:
    """Result of an approval policy check.

    Three possible verdicts:

    - ``approved()``       — no action required, execute immediately
    - ``needs_approval()`` — pause and send to human-in-the-loop
    - ``deny()``           — hard block, reject without HITL
    """

    requires_approval: bool
    is_blocked: bool = False
    reason: str | None = None

    @classmethod
    def approved(cls) -> "ApprovalDecision":
        """No approval needed — execute immediately."""
        return cls(requires_approval=False)

    @classmethod
    def needs_approval(cls, reason: str) -> "ApprovalDecision":
        """Pause for human-in-the-loop approval."""
        return cls(requires_approval=True, reason=reason)

    @classmethod
    def deny(cls, reason: str) -> "ApprovalDecision":
        """Hard block — reject without offering HITL."""
        return cls(requires_approval=False, is_blocked=True, reason=reason)


def _primary_argument(tool_input: dict[str, Any] | str | None) -> str | None:
    """Extract a single string from tool input for permission rule matching.

    For single-key dicts, returns the string value of that key.
    For multi-key dicts, concatenates all values separated by spaces.
    For strings, returns as-is.
    """
    if tool_input is None:
        return None
    if isinstance(tool_input, str):
        return tool_input
    if isinstance(tool_input, dict):
        values = list(tool_input.values())
        if len(values) == 1:
            return str(values[0])
        return " ".join(str(v) for v in values)
    return str(tool_input)


class ApprovalPolicy:
    """
    Domain service that determines what requires human approval.

    Evaluates tool calls against a layered deny/allow permission chain
    when ``PlatformContext.permissions`` is populated:

    1. Global DENY  → BLOCKED
    2. Project DENY → BLOCKED
    3. Agent DENY   → BLOCKED
    4. Skill DENY   → BLOCKED
    5. Ticket DENY  → BLOCKED
    6. Global ALLOW → ALLOWED
    7. Project ALLOW→ ALLOWED
    8. Agent ALLOW  → ALLOWED
    9. Skill ALLOW  → ALLOWED
    10. Ticket ALLOW→ ALLOWED
    11. (fallback)  → HITL

    When ``permissions`` is empty, falls back to the tool-level
    ``requires_approval`` flag (backwards compatible).

    Example::

        policy = ApprovalPolicy()
        decision = policy.check(tool, context, tool_input="kubectl get pods")
        if decision.is_blocked:
            # reject immediately
        elif decision.requires_approval:
            # send to HITL
        else:
            # execute
    """

    def __init__(self, always_approve_read_only: bool = True) -> None:
        self._always_approve_read_only = always_approve_read_only

    def requires_approval(
        self,
        tool: ToolLike,
        context: PlatformContext | None = None,
    ) -> bool:
        """Convenience: return True if this tool needs human approval."""
        return self.check(tool, context).requires_approval

    def check(
        self,
        tool: ToolLike,
        context: PlatformContext | None = None,
        tool_input: dict[str, Any] | str | None = None,
    ) -> ApprovalDecision:
        """
        Evaluate a tool call and return an :class:`ApprovalDecision`.

        Args:
            tool:       The tool being called.
            context:    Current platform context (may contain permissions).
            tool_input: Tool arguments; used for argument-pattern matching.
        """
        if context is not None and context.permissions:
            arg_str = _primary_argument(tool_input)

            # Steps 1-5: deny chain (global → project → agent → skill → ticket)
            for layer_name in _LAYER_ORDER:
                for layer in context.permissions:
                    if layer.layer == layer_name and layer.list == "deny":
                        for rule in layer.rules:
                            if rule.matches(tool.name, arg_str):
                                return ApprovalDecision.deny(
                                    f"Blocked by {layer_name} deny rule: {rule.raw}"
                                )

            # Steps 6-10: allow chain (global → project → agent → skill → ticket)
            for layer_name in _LAYER_ORDER:
                for layer in context.permissions:
                    if layer.layer == layer_name and layer.list == "allow":
                        for rule in layer.rules:
                            if rule.matches(tool.name, arg_str):
                                return ApprovalDecision.approved()

            # Step 11: no rule matched → HITL
            return ApprovalDecision.needs_approval(
                f"No permission rule matched for tool '{tool.name}'"
            )

        # No permissions in context: fall back to tool-level flag
        if tool.requires_approval:
            return ApprovalDecision.needs_approval(
                f"Tool '{tool.name}' is configured to require approval"
            )
        return ApprovalDecision.approved()

    def filter_requiring_approval(
        self,
        tools: list[ToolLike],
        context: PlatformContext | None = None,
    ) -> list[ToolLike]:
        """Filter tools to only those requiring approval."""
        return [t for t in tools if self.requires_approval(t, context)]
```

**Step 4: Run all approval policy tests**

```bash
pytest tests/core/test_approval_policy.py -v
```

Expected: All PASS.

**Step 5: Run full suite**

```bash
pytest -x -q
```

Expected: All pass.

**Step 6: Commit**

```bash
git add dcaf/core/domain/services/approval_policy.py tests/core/test_approval_policy.py
git commit -m "feat(permissions): add deny() verdict and layered evaluation to ApprovalPolicy"
```

---

## Task 5: Wire `ApprovalPolicy` into `AgentService._process_response`

**Files:**
- Modify: `dcaf/core/application/services/agent_service.py`
- Create: `tests/core/application/services/test_agent_service_permissions.py`

> **Read first:** `tests/core/application/services/test_agent_service_credentials.py` — the pattern for AsyncFakeRuntime is exactly what we'll reuse.

**Step 1: Write the failing integration tests**

Create `tests/core/application/__init__.py` and `tests/core/application/services/__init__.py` (both empty if they don't exist yet).

Create `tests/core/application/services/test_agent_service_permissions.py`:

```python
"""Integration tests: AgentService._process_response with permission engine."""

from typing import Any

import pytest

from dcaf.core.application.dto.requests import AgentRequest
from dcaf.core.application.dto.responses import AgentResponse, ToolCallDTO
from dcaf.core.application.services.agent_service import AgentService
from dcaf.core.domain.entities import Message
from dcaf.core.domain.value_objects.platform_context import PlatformContext
from dcaf.core.testing import FakeConversationRepository, FakeEventPublisher


# ---------------------------------------------------------------------------
# Fake runtime that injects tool calls into the response
# ---------------------------------------------------------------------------


class FakeRuntimeWithToolCall:
    """Returns a fake tool-call response so AgentService exercises _process_response."""

    def __init__(
        self,
        tool_name: str,
        tool_input: dict | None = None,
        requires_approval: bool = False,
    ):
        self._tool_name = tool_name
        self._tool_input = tool_input or {"command": tool_name}
        self._requires_approval = requires_approval

    async def invoke(self, messages, tools, **kwargs: Any) -> AgentResponse:
        tc = ToolCallDTO(
            id="tc-1",
            name=self._tool_name,
            input=self._tool_input,
            requires_approval=self._requires_approval,
        )
        return AgentResponse(
            conversation_id="conv-test",
            text=None,
            data=None,
            tool_calls=[tc],
        )

    async def invoke_stream(self, **kwargs: Any):
        return
        yield


def _make_service(runtime) -> AgentService:
    return AgentService(
        runtime=runtime,
        conversations=FakeConversationRepository(),
        events=FakeEventPublisher(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DENY_DELETE_ALLOW_GET = {
    "permissions": [
        {"layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"]},
        {"layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"]},
    ]
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentServicePermissionBlocked:
    async def test_blocked_tool_call_is_rejected_not_pending(self):
        """A tool call matching a deny rule must end up REJECTED, not in HITL."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl delete pods --all"},
        )
        service = _make_service(runtime)
        request = AgentRequest(
            content="delete all pods",
            context=DENY_DELETE_ALLOW_GET,
        )

        response = await service.execute(request)

        # Not blocking on HITL
        assert not response.has_pending_approvals
        assert response.is_complete
        # Tool call should be present and in rejected/failed state
        tool_calls = response.tool_calls
        assert len(tool_calls) == 1
        assert tool_calls[0].status in ("rejected", "failed")

    async def test_blocked_tool_reason_contains_deny(self):
        """The rejection reason must mention the deny rule."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl delete deployments/api"},
        )
        service = _make_service(runtime)
        request = AgentRequest(content="delete api", context=DENY_DELETE_ALLOW_GET)

        response = await service.execute(request)

        tool_call = response.tool_calls[0]
        assert "deny" in (tool_call.rejection_reason or "").lower() or \
               "blocked" in (tool_call.rejection_reason or "").lower()


class TestAgentServicePermissionAllowed:
    async def test_allowed_tool_call_executes_without_hitl(self):
        """A tool call matching an allow rule must execute and not go to HITL."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl get pods"},
        )
        service = _make_service(runtime)
        request = AgentRequest(content="get pods", context=DENY_DELETE_ALLOW_GET)

        response = await service.execute(request)

        assert not response.has_pending_approvals


class TestAgentServicePermissionHITLFallback:
    async def test_unmatched_tool_call_goes_to_hitl(self):
        """A tool call with no matching rule must go to HITL (step 11)."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "helm upgrade my-release ./chart"},
        )
        service = _make_service(runtime)
        request = AgentRequest(content="upgrade helm", context=DENY_DELETE_ALLOW_GET)

        response = await service.execute(request)

        assert response.has_pending_approvals
        assert not response.is_complete


class TestAgentServicePermissionsBackwardsCompat:
    async def test_no_permissions_uses_tool_requires_approval_flag(self):
        """When context has no permissions, tool.requires_approval governs."""
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl delete pods"},
            requires_approval=False,
        )
        service = _make_service(runtime)
        # No permissions in context
        request = AgentRequest(content="do it", context={"tenant_name": "prod"})

        response = await service.execute(request)

        assert not response.has_pending_approvals

    async def test_no_context_uses_tool_flag(self):
        runtime = FakeRuntimeWithToolCall(
            tool_name="Bash",
            tool_input={"command": "kubectl get pods"},
            requires_approval=False,
        )
        service = _make_service(runtime)
        request = AgentRequest(content="get pods")

        response = await service.execute(request)

        assert not response.has_pending_approvals
```

**Step 2: Check what `AgentResponse.tool_calls` and `ToolCallDTO` fields look like**

Before writing implementation, check the response DTO fields so we know what `.status` and `.rejection_reason` look like.

```bash
grep -n "rejection_reason\|status\|tool_calls" \
  dcaf/core/application/dto/responses.py | head -30
```

Adjust the test assertions to match actual field names if needed.

**Step 3: Run new tests to confirm they fail**

```bash
pytest tests/core/application/services/test_agent_service_permissions.py -v
```

Expected: Some failures because `_process_response` doesn't call `self._policy.check()` yet.

**Step 4: Update `_process_response` in `AgentService`**

In `dcaf/core/application/services/agent_service.py`, locate `_process_response` (around line 368).

Replace the tool-call loop with:

```python
        # Process tool calls
        processed_tool_calls = []
        for tc_dto in runtime_response.tool_calls:
            # Find the registered tool (may be None for runtime-only tools)
            tool = self._find_tool(tc_dto.name, tools)

            # Evaluate permission policy
            _tool_for_policy = tool or _FallbackTool(tc_dto.name, tc_dto.requires_approval)
            decision = self._policy.check(_tool_for_policy, context, tc_dto.input)

            # Create domain entity
            tool_call = ToolCall(
                id=ToolCallId(tc_dto.id),
                tool_name=tc_dto.name,
                input=ToolInput(tc_dto.input),
                description=tc_dto.description,
                intent=tc_dto.intent,
                requires_approval=decision.requires_approval,
            )

            if decision.is_blocked:
                # Hard deny — reject immediately, no HITL
                tool_call.reject(decision.reason or "Blocked by permission policy")
                processed_tool_calls.append(ToolCallDTO.from_tool_call(tool_call))

            elif decision.requires_approval:
                # Send to human-in-the-loop
                conversation.request_tool_approval([tool_call])
                processed_tool_calls.append(ToolCallDTO.from_tool_call(tool_call))

            else:
                # Auto-approve and execute
                tool_call.auto_approve()
                if tool:
                    try:
                        result = tool.execute(
                            tc_dto.input,
                            context.to_dict() if tool.requires_platform_context else None,
                        )
                        tool_call.start_execution()
                        tool_call.complete(result)
                    except Exception as e:  # Intentional catch-all: user tools can raise anything
                        tool_call.start_execution()
                        tool_call.fail(str(e))

                processed_tool_calls.append(ToolCallDTO.from_tool_call(tool_call))
```

Add `_FallbackTool` as a private class at the bottom of `agent_service.py` (after all methods, still in the module):

```python
class _FallbackTool:
    """Minimal ToolLike for runtime tool calls not registered in the tools list."""

    def __init__(self, name: str, requires_approval: bool) -> None:
        self._name = name
        self._requires_approval = requires_approval

    @property
    def name(self) -> str:
        return self._name

    @property
    def requires_approval(self) -> bool:
        return self._requires_approval
```

**Step 5: Run the new tests**

```bash
pytest tests/core/application/services/test_agent_service_permissions.py -v
```

Expected: All PASS.

**Step 6: Run the full test suite**

```bash
pytest -x -q
```

Expected: All pass (672+ tests).

**Step 7: Lint and type-check**

```bash
ruff check .
mypy dcaf/
```

Fix any issues before committing.

**Step 8: Commit**

```bash
git add dcaf/core/application/services/agent_service.py \
        tests/core/application/__init__.py \
        tests/core/application/services/__init__.py \
        tests/core/application/services/test_agent_service_permissions.py
git commit -m "feat(permissions): wire ApprovalPolicy layered evaluation into AgentService"
```

---

## Task 6: Update docs and wire protocol

**Files:**
- Modify: `docs/guides/message-protocol.md`
- Modify: `docs/guides/credential-injection.md` (or create `docs/guides/permissions.md`)

**Step 1: Add `permissions` to the `platform_context` fields table in `message-protocol.md`**

Find the Platform Context fields table and add:
```markdown
| `permissions` | `array` | Layered deny/allow rules — see [Permissions](permissions.md) |
```

**Step 2: Create `docs/guides/permissions.md`**

```markdown
# Agent Action Permissions

DCAF's permission engine evaluates every tool call against a layered deny/allow
rule chain before executing it or sending it to Human-in-the-Loop (HITL).

## Evaluation Chain

Rules are evaluated top-down. **First match wins.** The entire deny chain runs
before the allow chain begins.

| Step | Layer  | List  | Match Result |
|------|--------|-------|--------------|
| 1    | Global | DENY  | → BLOCKED    |
| 2    | Project| DENY  | → BLOCKED    |
| 3    | Agent  | DENY  | → BLOCKED    |
| 4    | Skill  | DENY  | → BLOCKED    |
| 5    | Ticket | DENY  | → BLOCKED    |
| 6    | Global | ALLOW | → ALLOWED    |
| 7    | Project| ALLOW | → ALLOWED    |
| 8    | Agent  | ALLOW | → ALLOWED    |
| 9    | Skill  | ALLOW | → ALLOWED    |
| 10   | Ticket | ALLOW | → ALLOWED    |
| 11   | —      | —     | → HITL       |

A higher-layer DENY cannot be bypassed by a lower-layer ALLOW.

## Rule Syntax

```
ToolName(argument glob pattern)
```

- **Tool name** is matched case-insensitively.
- **Argument pattern** uses standard glob syntax (`*`, `?`).
- Rules with no parentheses match any call to that tool regardless of arguments.

Examples:
```
Bash(kubectl delete *)          # blocks all kubectl delete commands
Bash(kubectl get *)             # allows all kubectl get commands
Bash(* --version)               # allows --version on any tool
kubectl                         # matches any kubectl call
```

## Wire Format

Permissions arrive in `platform_context.permissions` as a list of layer objects:

```json
{
  "permissions": [
    {
      "layer": "global",
      "list": "deny",
      "rules": [
        "Bash(kubectl delete *)",
        "Bash(kubectl exec *)"
      ]
    },
    {
      "layer": "global",
      "list": "allow",
      "rules": [
        "Bash(kubectl get *)",
        "Bash(kubectl describe *)"
      ]
    }
  ]
}
```

## Fallback Behaviour

When `permissions` is absent or empty, DCAF falls back to the tool-level
`requires_approval=True` flag on each `@tool` definition (existing behaviour,
fully backwards compatible).
```

**Step 3: Add permissions guide to `mkdocs.yml` nav**

In `mkdocs.yml`, after `Credential Injection`:
```yaml
    - Permissions: guides/permissions.md
```

**Step 4: Build docs**

```bash
mkdocs build --strict 2>&1 | tail -5
```

Expected: `Documentation built in X.XXs` (no errors).

**Step 5: Commit**

```bash
git add docs/guides/permissions.md docs/guides/message-protocol.md mkdocs.yml
git commit -m "docs(permissions): add layered permissions guide and update message-protocol"
```

---

## Final Verification

```bash
pytest -v
ruff check .
ruff format --check .
mypy dcaf/
mkdocs build --strict
```

All must pass before opening the PR.
