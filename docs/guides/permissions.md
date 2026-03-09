# Agent Action Permissions

DCAF's permission engine evaluates every tool call against a layered deny/allow
rule chain before executing it or sending it to Human-in-the-Loop (HITL).

## Evaluation Chain

Rules are evaluated top-down. **First match wins.** The entire deny chain runs
before the allow chain begins.

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

## Step-by-Step Example

**Action requested:** `Bash(kubectl get pods)`

```
Step 1 — Global DENY:   "Bash(kubectl delete *)"      → no match, continue
Step 2 — Project DENY:  "Bash(kubectl exec *)"        → no match, continue
Step 3 — Agent DENY:    "Bash(kubectl apply *)"       → no match, continue
Step 4 — Skill DENY:    "Bash(kubectl drain *)"       → no match, continue
Step 5 — Ticket DENY:   (no ticket-level deny rules)  → no match, continue

Step 6 — Global ALLOW:  "Bash(kubectl get *)"         → ✅ MATCH → ALLOWED
```

## Human-in-the-Loop Fallback

When no rule matches across all 10 steps (step 11), DCAF sends the tool call
to the end user for approval. The user can:

- **Approve once** — the action executes this time only.
- **Deny once** — the action is blocked this time only.

## Fallback Behaviour

When `permissions` is absent or empty, DCAF falls back to the tool-level
`requires_approval=True` flag on each `@tool` definition (existing behaviour,
fully backwards compatible).

## Layer Ownership

| Layer   | Who Sets It    | Scope                        |
|---------|----------------|------------------------------|
| Global  | Helpdesk Admin | All projects & agents        |
| Project | Project Admin  | All agents in the project    |
| Agent   | Platform       | That agent only              |
| Skill   | Platform       | Agents with that skill       |
| Ticket  | System via HITL| Single ticket lifecycle      |
