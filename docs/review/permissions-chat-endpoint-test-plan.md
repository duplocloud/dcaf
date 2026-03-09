# Permissions Chat Endpoint — Test Plan

Validates the layered deny/allow permission engine introduced in PR #51 via the
`POST /api/chat` endpoint (and noted streaming/WS variants). Permissions arrive in
`platform_context.permissions` on the last user message.

See [Permissions Guide](../guides/permissions.md) for the rule syntax and layer
evaluation order.

---

## Base Request Template

```json
POST /api/chat
Content-Type: application/json

{
  "messages": [
    {
      "role": "user",
      "content": "<instruction>",
      "platform_context": {
        "tenant_name": "test",
        "permissions": [
          {
            "layer": "global",
            "list": "deny",
            "rules": ["Bash(kubectl delete *)", "Bash(kubectl exec *)"]
          },
          {
            "layer": "global",
            "list": "allow",
            "rules": ["Bash(kubectl get *)", "Bash(kubectl describe *)"]
          }
        ]
      }
    }
  ]
}
```

---

## Response Fields to Assert

| Field | Deny | Allow | HITL |
|-------|------|-------|------|
| `data.tool_calls[].status` | `rejected` | absent / executed | `pending` |
| `data.tool_calls[].rejection_reason` | contains `"deny"` or `"blocked"` | — | — |
| `data.executed_tool_calls` | empty | has entry | empty |
| `has_pending_approvals` | `false` | `false` | `true` |
| `is_complete` | `true` | `true` | `false` |

---

## Test Cases

### 1. Deny Rule — Tool Call Blocked

**Goal:** A tool call matching a deny rule is rejected immediately, without going to HITL.

```json
{
  "messages": [{
    "role": "user",
    "content": "Delete all pods in the default namespace",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"] },
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"] }
      ]
    }
  }]
}
```

**Assert:**
- `data.tool_calls[0].status` == `"rejected"`
- `data.tool_calls[0].rejection_reason` contains `"deny"` or `"blocked"`
- `has_pending_approvals` == `false`
- `is_complete` == `true`

---

### 2. Allow Rule — Tool Call Executes Without HITL

**Goal:** A tool call matching an allow rule executes immediately — no approval dialog.

```json
{
  "messages": [{
    "role": "user",
    "content": "List all pods in the default namespace",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"] },
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"] }
      ]
    }
  }]
}
```

**Assert:**
- `data.tool_calls` is empty or all entries have `status != "pending"`
- `data.executed_tool_calls` contains the `kubectl get pods` call
- `has_pending_approvals` == `false`

---

### 3. HITL Fallback — No Matching Rule

**Goal:** A tool call with no matching rule in either chain surfaces for user approval (step 11).

```json
{
  "messages": [{
    "role": "user",
    "content": "Run helm upgrade for my-release",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"] },
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"] }
      ]
    }
  }]
}
```

**Assert:**
- `data.tool_calls[0].status` == `"pending"`
- `data.tool_calls[0].requires_approval` == `true`
- `has_pending_approvals` == `true`
- `is_complete` == `false`

---

### 4. Layer Priority — Lower-Layer Deny Cannot Be Bypassed by Higher-Layer Allow

**Goal:** A global allow rule does NOT override an agent-level deny rule.

```json
{
  "messages": [{
    "role": "user",
    "content": "Apply the deployment manifest",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl apply *)"] },
        { "layer": "agent",  "list": "deny",  "rules": ["Bash(kubectl apply *)"] }
      ]
    }
  }]
}
```

**Assert:**
- `data.tool_calls[0].status` == `"rejected"`
- `data.tool_calls[0].rejection_reason` contains `"agent"`

---

### 5. Ticket-Level Allow — One-Off Permission Grant

**Goal:** A ticket-scoped allow permits a specific command that would otherwise go to HITL.

```json
{
  "messages": [{
    "role": "user",
    "content": "Scale the worker deployment to 3 replicas",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"] },
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"] },
        { "layer": "ticket", "list": "allow",  "rules": ["Bash(kubectl scale deployment/worker --replicas=3)"] }
      ]
    }
  }]
}
```

**Assert:**
- Tool executes without HITL (`has_pending_approvals` == `false`)
- `data.executed_tool_calls` contains the scale command

---

### 6. No Permissions Field — Backwards Compatibility

**Goal:** When `permissions` is absent, `requires_approval` on the tool governs (legacy behaviour).

```json
{
  "messages": [{
    "role": "user",
    "content": "List pods",
    "platform_context": {
      "tenant_name": "prod"
    }
  }]
}
```

**Assert:**
- Tools with `requires_approval=False` auto-execute
- Tools with `requires_approval=True` surface as HITL pending
- No regression in existing behaviour

---

### 7. Empty Permissions Array — Backwards Compatibility

**Goal:** `permissions: []` is equivalent to no permissions field.

```json
{
  "messages": [{
    "role": "user",
    "content": "List pods",
    "platform_context": {
      "permissions": []
    }
  }]
}
```

**Assert:** Identical outcome to Test 6.

---

### 8. Deny Reason Layer Accuracy

**Goal:** `rejection_reason` names the specific layer that fired the deny — not just a generic message.

Run five separate requests, each with a deny rule at a different layer (`global`, `project`, `agent`, `skill`, `ticket`), and a command that matches only that layer's rule.

**Assert for each:** `rejection_reason` contains the layer name used (e.g., `"project"`, `"skill"`).

---

### 9. Bare Tool Name Rule (No Argument Pattern)

**Goal:** A rule with no parentheses matches any call to that tool regardless of arguments.

```json
{
  "messages": [{
    "role": "user",
    "content": "Run any kubectl command",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny", "rules": ["Bash"] }
      ]
    }
  }]
}
```

**Assert:**
- Any `Bash` tool call is `rejected`, regardless of arguments

---

### 10. Case-Insensitive Tool Name Matching

**Goal:** Rule `"bash(kubectl get *)"` (lowercase) matches a `Bash` tool call.

```json
{
  "messages": [{
    "role": "user",
    "content": "List pods",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "allow", "rules": ["bash(kubectl get *)"] }
      ]
    }
  }]
}
```

**Assert:** `kubectl get pods` executes without HITL.

---

### 11. Mixed Tool Call Response — One Blocked, One Allowed, One HITL

**Goal:** When the LLM emits multiple tool calls in a single turn, each resolves independently.

Configure permissions so that in a single response:
- Tool call A matches a deny rule → `rejected`
- Tool call B matches an allow rule → executes
- Tool call C matches no rule → `pending`

**Assert:**
- Tool call A: `status == "rejected"`
- Tool call B: appears in `data.executed_tool_calls`
- Tool call C: `status == "pending"`
- `has_pending_approvals` == `true` (because C is pending)

---

### 12. Permissions Override `requires_approval` Tool Flag

**Goal:** When permissions are present, a tool configured `requires_approval=True` that matches
an allow rule should execute immediately (permissions take precedence over the tool flag).

```json
{
  "messages": [{
    "role": "user",
    "content": "List pods",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"] }
      ]
    }
  }]
}
```

Trigger this against a tool that has `requires_approval=True` in its definition.

**Assert:**
- Tool executes without HITL (`has_pending_approvals` == `false`)
- The tool's `requires_approval` flag is not consulted when permissions are present

---

### 13. Empty `rules` Array in a Layer — No-Op

**Goal:** A layer with an empty rules list should not affect evaluation.

```json
{
  "messages": [{
    "role": "user",
    "content": "List pods",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny",  "rules": [] },
        { "layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"] }
      ]
    }
  }]
}
```

**Assert:** `kubectl get pods` executes normally — empty deny layer is a no-op.

---

### 14. Streaming Endpoint Parity (`POST /api/chat-stream`)

**Goal:** Deny and HITL behaviour is identical on the streaming path.

Repeat Test 1 (deny) and Test 3 (HITL) against `POST /api/chat-stream`.

**Assert:**
- NDJSON event stream terminates with a `done` event
- For deny: no `tool_calls` event with `status == "pending"`; a rejection is surfaced
- For HITL: a `tool_calls` event with `requires_approval == true` is emitted

---

### 15. Post-HITL Approval Continuation — Permissions Re-Evaluated

**Goal:** After a user approves a pending tool call, the follow-up turn's permissions still apply.

**Step 1 — Trigger HITL** (no matching rule):
```json
{
  "messages": [{
    "role": "user",
    "content": "Run helm upgrade",
    "platform_context": {
      "permissions": [
        { "layer": "global", "list": "deny", "rules": ["Bash(kubectl delete *)"] }
      ]
    }
  }]
}
```
Response: `data.tool_calls[0].status == "pending"`, `id == "tc-1"`.

**Step 2 — User approves and re-submits:**
```json
{
  "messages": [
    { "role": "user", "content": "Run helm upgrade" },
    { "role": "assistant", "content": "...(prior response)..." },
    {
      "role": "user",
      "content": "",
      "platform_context": {
        "permissions": [
          { "layer": "global", "list": "deny", "rules": ["Bash(kubectl delete *)"] }
        ]
      },
      "data": {
        "tool_calls": [{ "id": "tc-1", "name": "Bash", "input": { "command": "helm upgrade ..." }, "execute": true }]
      }
    }
  ]
}
```

**Assert:** Approved tool call executes; subsequent new tool calls in this turn are still evaluated against the permissions in the new message's `platform_context`.

---

### 16. Full Chain Smoke Test (Document Example)

End-to-end test using the full 10-layer permission config from the design document.
See `tests/core/test_approval_policy.py::TestApprovalPolicyDocumentExample` for the
permission payload.

| Command | Expected outcome |
|---------|-----------------|
| `kubectl get pods` | Executed (global allow, step 6) |
| `kubectl delete pods` | Rejected (global deny, step 1) |
| `kubectl exec -it my-pod -- bash` | Rejected (global deny, step 1) |
| `helm upgrade my-chart ./chart` | HITL pending (step 11) |

---

## Quick curl Reference

```bash
# Test 1 — Deny
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Delete all pods",
      "platform_context": {
        "permissions": [
          {"layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"]},
          {"layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"]}
        ]
      }
    }]
  }' | jq '.data.tool_calls[0] | {status, rejection_reason}'

# Test 3 — HITL
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "role": "user",
      "content": "Run helm upgrade for my-release",
      "platform_context": {
        "permissions": [
          {"layer": "global", "list": "deny",  "rules": ["Bash(kubectl delete *)"]},
          {"layer": "global", "list": "allow", "rules": ["Bash(kubectl get *)"]}
        ]
      }
    }]
  }' | jq '{has_pending_approvals, tool_calls: .data.tool_calls}'
```
