# Agent Actions Permissions

# DuploCloud Helpdesk — Permission Evaluation Order
## Core Rules
*   **Firewall model:** rules are evaluated top-down, **first match wins**, execution stops immediately.
*   **DENY always before ALLOW:** the entire deny chain is exhausted before the allow chain begins.
*   **Inheritance flows downward:** each layer narrows what the layer above allows. Lower layers cannot override a higher-layer DENY
* * *
## Evaluation Chain

| Step | Layer | List | Managed By | Match Result |
| ---| ---| ---| ---| --- |
| 1 | Global | DENY | Platform Admin | → BLOCKED |
| 2 | Project | DENY | Platform Admin | → BLOCKED |
| 3 | Agent | DENY | Platform Admin | → BLOCKED |
| 4 | Skill | DENY | Platform Admin | → BLOCKED |
| 5 | Ticket | DENY | End User | → BLOCKED |
| 6 | Global | ALLOW | Platform Admin | → ALLOWED |
| 7 | Project | ALLOW | Platform Admin | → ALLOWED |
| 8 | Agent | ALLOW | Platform Admin | → ALLOWED |
| 9 | Skill | ALLOW | Platform Admin | → ALLOWED |
| 10 | Ticket | ALLOW | End User | → ALLOWED |
| 11 | — | — | — | → Human in the Loop Triggered |

* * *
## Step-by-Step Example
**Action requested:** `Bash(kubectl get pods)`
**Context:** Agent Jane Doe, Project K8s Support, Skill Cluster Viewer, Ticket TKT-00421

```perl
Step 1 — Global DENY:   "Bash(kubectl delete *)"      → no match, continue
Step 2 — Project DENY:  "Bash(kubectl exec *)"        → no match, continue
Step 3 — Agent DENY:    "Bash(kubectl apply *)"       → no match, continue
Step 4 — Skill DENY:    "Bash(kubectl drain *)"       → no match, continue
Step 5 — Ticket DENY:   (no ticket-level deny rules)  → no match, continue

Step 6 — Global ALLOW:  "Bash(kubectl get *)"         → ✅ MATCH → ALLOWED
```

* * *
## Human-in-the-Loop (HITL) — Step 11 Fallback
Triggered when **no rule matches** across all 10 steps.

```sql
Agent requests action
       │
       ▼
  HITL notification sent to end user
       │
       ├─► User APPROVES
       │         │
       │         ├─► Scope: "This action only"
       │         │     → One-time pass, nothing written
       │         │
       │         └─► Scope: "All subsequent" (opt-in)
       │               → Rule written to HelpDesk
       │               → Applies for the rest of this ticket's lifecycle only
       │
       └─► User DENIES 
                 │
                 ├─► Scope: "This action only"
                 │     → Action blocked once, nothing written
                 │
                 └─► Scope: "All subsequent" (opt-in)
                       → Rule written to HelpDesk
```

* * *
## Permissions Payload in Platform Context

```json
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
        "Bash(aws iam delete-*)"
      ]
    },
    {
      "layer": "project",
      "list": "deny",
      "rules": [
        "Bash(kubectl apply -f * --namespace=production)",
        "Bash(kubectl rollout undo *)"
      ]
    },
    {
      "layer": "agent",
      "list": "deny",
      "rules": [
        "Bash(kubectl apply *)",
        "Bash(aws iam attach-role-policy *)"
      ]
    },
    {
      "layer": "skill",
      "list": "deny",
      "rules": [
        "Bash(kubectl delete namespace *)"
      ]
    },
    {
      "layer": "ticket",
      "list": "deny",
      "rules": [
        "Bash(kubectl get secret db-credentials *)"
      ]
    },
    {
      "layer": "global",
      "list": "allow",
      "rules": [
        "Bash(kubectl get *)",
        "Bash(kubectl describe *)",
        "Bash(aws s3 ls *)",
        "Bash(* --version)",
        "Bash(* --help *)"
      ]
    },
    {
      "layer": "project",
      "list": "allow",
      "rules": [
        "Bash(kubectl rollout status *)",
        "Bash(kubectl top *)",
        "Bash(kubectl logs *)"
      ]
    },
    {
      "layer": "agent",
      "list": "allow",
      "rules": [
        "Bash(kubectl logs * --tail=*)",
        "Bash(kubectl get events *)",
        "Bash(aws ec2 describe-security-groups *)"
      ]
    },
    {
      "layer": "skill",
      "list": "allow",
      "rules": [
        "Bash(kubectl apply -f * --namespace=staging)",
        "Bash(kubectl scale deployment/* --replicas=*)",
        "Bash(kubectl rollout restart *)"
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
```

## Layer Ownership Summary

| Layer | Who Sets It | Scope | Persisted |
| ---| ---| ---| --- |
| Global | Helpdesk Admin | All projects & agents | Yes |
| Project | Project Admin | All agents in the project | Yes |
| Agent | Platform | That agent only | Yes |
| Skill | Platform | Agents with that skill | Yes |
| Ticket | System via HITL | Single ticket lifecycle | Yes (ticket-scoped) |

* * *
## Key Design Decisions
1. **DENY chain runs entirely before ALLOW.** A project-level DENY cannot be bypassed by a global-level ALLOW.
2. **Ticket-level rules are the most specific** but sit at the bottom of both chains — they represent the most tailored, situational decisions made mid-flight.
3. **HITL scope is opt-in.** The safe default is always "this action only" to prevent accidental blanket approvals.
4. **Timeouts default to DENY** to ensure no action is silently allowed due to an unanswered HITL request.