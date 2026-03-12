# Agent Action Permissions

DCAF's permission engine evaluates every tool call against a layered deny/allow
rule chain before executing it or sending it to Human-in-the-Loop (HITL).

---

## Evaluation Chain

Rules are evaluated top-down. **First match wins.** The entire deny chain runs
before the allow chain begins — so any deny rule at any layer beats any allow
rule at any layer.

| Step | Layer   | List  | Managed By     | Match Result |
|------|---------|-------|----------------|--------------|
| 1    | Global  | DENY  | Platform Admin | → BLOCKED    |
| 2    | Project | DENY  | Platform Admin | → BLOCKED    |
| 3    | Agent   | DENY  | Platform Admin | → BLOCKED    |
| 4    | Skill   | DENY  | Platform Admin | → BLOCKED    |
| 5    | Ticket  | DENY  | End User       | → BLOCKED    |
| 6    | Global  | ALLOW | Platform Admin | → ALLOWED    |
| 7    | Project | ALLOW | Platform Admin | → ALLOWED    |
| 8    | Agent   | ALLOW | Platform Admin | → ALLOWED    |
| 9    | Skill   | ALLOW | Platform Admin | → ALLOWED    |
| 10   | Ticket  | ALLOW | End User       | → ALLOWED    |
| 11   | —       | —     | —              | → HITL       |

**Key rules:**

- A global DENY (step 1) cannot be overridden by any allow at any layer.
- An agent-level DENY (step 3) beats a global ALLOW (step 6) — deny chain
  always runs first.
- Ticket-level ALLOW (step 10) is for one-off grants on commands that have no
  deny match but would otherwise go to HITL (step 11). It cannot bypass a deny.

---

## Rule Syntax

```
ToolName(argument glob pattern)
```

- **Tool name** is matched **case-insensitively** (`bash` matches `Bash`).
- **Argument pattern** uses standard glob syntax (`*` matches any sequence,
  `?` matches any single character).
- Rules with **no parentheses** match any call to that tool regardless of
  arguments.

Examples:

```
Bash(kubectl delete *)           # blocks all kubectl delete commands
Bash(kubectl get *)              # allows all kubectl get commands
Bash(kubectl scale * --replicas=3)  # specific scale command
bash(kubectl get *)              # lowercase tool name also matches 'Bash'
Bash                             # matches ANY Bash call (no arg filter)
```

### How the argument is extracted

The rule pattern is matched against a **single string** derived from the tool's
input:

| Tool input                          | Matched string                  |
|-------------------------------------|---------------------------------|
| `{"command": "kubectl get pods"}`   | `kubectl get pods`              |
| `"kubectl get pods"` (plain string) | `kubectl get pods`              |
| `{"cmd": "ls", "dir": "/tmp"}`      | `ls /tmp` (all values joined)   |
| `{}`  or `null`                     | `None` — bare tool-name rules still match |

Single-key dicts (the common case for shell tools) use just the value. Multi-key
dicts concatenate all values with spaces. This means argument patterns always
work naturally for tools like `Bash(command=...)`.

### Rule matching within a layer

Each layer can have multiple rules. They are evaluated in order; the **first
matching rule in that layer** triggers the decision for the whole layer.
Because the outer loop iterates layers in the fixed order
`global → project → agent → skill → ticket`, the effective precedence is:

1. Global deny rules (checked left-to-right within the layer)
2. Project deny rules
3. Agent deny rules
4. Skill deny rules
5. Ticket deny rules
6. Global allow rules
7. Project allow rules
8. Agent allow rules
9. Skill allow rules
10. Ticket allow rules

---

## Wire Format

Permissions arrive in `platform_context.permissions` inside the last user
message:

```json
{
  "messages": [{
    "role": "user",
    "content": "List my pods",
    "platform_context": {
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
        },
        {
          "layer": "ticket",
          "list": "allow",
          "rules": [
            "Bash(kubectl scale deployment/worker --replicas=3)"
          ]
        }
      ]
    }
  }]
}
```

**Notes:**

- `layer` must be one of: `global`, `project`, `agent`, `skill`, `ticket`.
- `list` must be `deny` or `allow`.
- An empty `rules` array is a **no-op** — that layer is simply skipped.
- Omitting a layer entirely is equivalent to an empty rules array for that layer.
- Multiple entries for the same `layer`/`list` pair are supported; all rules
  from all matching entries are evaluated in the order they appear.

---

## Step-by-Step Example

**Permissions configured:**

| Layer  | List  | Rules                                    |
|--------|-------|------------------------------------------|
| global | deny  | `Bash(kubectl delete *)`, `Bash(kubectl exec *)` |
| global | allow | `Bash(kubectl get *)`, `Bash(kubectl describe *)` |
| ticket | allow | `Bash(kubectl scale deployment/worker --replicas=3)` |

---

### Case 1 — `kubectl get pods` → ALLOWED

```
Step 1  Global DENY:   "Bash(kubectl delete *)"      → no match
                       "Bash(kubectl exec *)"         → no match
Step 2  Project DENY:  (no rules)                    → no match
Step 3  Agent DENY:    (no rules)                    → no match
Step 4  Skill DENY:    (no rules)                    → no match
Step 5  Ticket DENY:   (no rules)                    → no match

Step 6  Global ALLOW:  "Bash(kubectl get *)"          → ✅ MATCH → ALLOWED
```

---

### Case 2 — `kubectl delete pods --all` → BLOCKED

```
Step 1  Global DENY:   "Bash(kubectl delete *)"       → ✅ MATCH → BLOCKED
        rejection_reason: "Blocked by global deny rule: Bash(kubectl delete *)"
```

The response includes:
```json
{
  "content": "The request was blocked by the permission policy: Blocked by global deny rule: Bash(kubectl delete *)",
  "data": {
    "tool_calls": [{
      "name": "Bash",
      "input": {"command": "kubectl delete pods --all"},
      "status": "rejected",
      "rejection_reason": "Blocked by global deny rule: Bash(kubectl delete *)"
    }]
  },
  "has_pending_approvals": false,
  "is_complete": true
}
```

---

### Case 3 — `helm upgrade my-release ./chart` → HITL

```
Steps 1-5  DENY chain:   no rules match "helm upgrade ..."
Steps 6-10 ALLOW chain:  no rules match "helm upgrade ..."

Step 11  No match → HITL (pending approval)
```

The response includes:
```json
{
  "data": {
    "tool_calls": [{
      "name": "Bash",
      "status": "pending",
      "requires_approval": true
    }]
  },
  "has_pending_approvals": true,
  "is_complete": false
}
```

---

### Case 4 — `kubectl scale deployment/worker --replicas=3` → ALLOWED via ticket

```
Steps 1-5  DENY chain:   no rules match
Step 6     Global ALLOW: "Bash(kubectl get *)"         → no match (wrong command)
Steps 7-9  ALLOW chain:  (no project/agent/skill rules)
Step 10    Ticket ALLOW: "Bash(kubectl scale deployment/worker --replicas=3)"
                                                        → ✅ MATCH → ALLOWED
```

---

## Human-in-the-Loop Fallback

When no rule matches across all 10 steps (step 11), DCAF sends the tool call
to the end user for approval. The user can:

- **Approve** — the action executes this turn only.
- **Deny** — the action is blocked this turn only.

The pending tool call appears in `data.tool_calls` with `status: "pending"` and
`requires_approval: true`. To approve, re-submit the conversation with that tool
call's `execute` field set to `true`:

```json
{
  "data": {
    "tool_calls": [{"id": "tc-1", "name": "Bash", "input": {...}, "execute": true}]
  }
}
```

---

## Streaming Endpoint Parity

The streaming endpoint (`POST /api/chat-stream`) applies the **same** permission
policy:

- **Blocked** tool call → `text_delta` event with rejection message; no
  `tool_calls` event is emitted.
- **HITL** tool call → `tool_calls` event with `status: "pending"` and
  `requires_approval: true`.
- **Allowed** tool call → `executed_tool_calls` event with the result.

---

## Fallback Behaviour

When `permissions` is absent or `[]`, DCAF falls back to the tool-level
`requires_approval` flag on each `@tool` definition (existing pre-permissions
behaviour, fully backwards compatible).

```python
@tool(description="Run a shell command", requires_approval=True)
def Bash(command: str) -> str: ...
```

With no permissions in context, this tool always goes to HITL. With permissions
present, the permission chain governs instead — an allow rule can execute it
without HITL even if `requires_approval=True` is set on the tool definition.

---

## Layer Ownership

| Layer   | Who Sets It      | Scope                        |
|---------|------------------|------------------------------|
| Global  | Helpdesk Admin   | All projects & agents        |
| Project | Project Admin    | All agents in the project    |
| Agent   | Platform         | That agent only              |
| Skill   | Platform         | Agents with that skill       |
| Ticket  | System via HITL  | Single ticket lifecycle      |
