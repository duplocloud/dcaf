# Message Protocol Guide

This guide explains the message protocol used by DCAF for communication between clients, agents, and the server.

---

## Table of Contents

1. [Overview](#overview)
2. [Message Structure](#message-structure)
3. [Request Format](#request-format)
4. [Response Format](#response-format)
5. [Tool Call Flow](#tool-call-flow)
6. [Command Flow](#command-flow)
7. [Platform Context](#platform-context)
8. [Examples](#examples)

---

## Overview

DCAF uses a structured message protocol for all agent interactions. This protocol supports:

- **Multi-turn conversations** with message history
- **Tool calling** with approval workflows
- **Terminal commands** with file creation
- **Platform context** for runtime information
- **Streaming** for real-time responses

### Communication Flow

```
┌──────────┐         ┌──────────┐         ┌───────┐
│  Client  │ ──────> │  Server  │ ──────> │ Agent │
│ (UI/API) │ <────── │ (FastAPI)│ <────── │       │
└──────────┘         └──────────┘         └───────┘
     │                    │                   │
     │  POST /api/        │   invoke()        │
     │  sendMessage       │                   │
     │ ─────────────────> │ ─────────────────>│
     │                    │                   │
     │   AgentMessage     │   AgentMessage    │
     │ <───────────────── │ <─────────────────│
     │                    │                   │
```

---

## Message Structure

### Base Message

```python
{
    "role": "user" | "assistant",
    "content": "Message text",
    "data": {
        "cmds": [...],
        "executed_cmds": [...],
        "tool_calls": [...],
        "executed_tool_calls": [...],
        "url_configs": [...]
    },
    "meta_data": {},
    "timestamp": "2024-01-15T10:30:00Z",
    "user": {"name": "Alice", "id": "user123"},
    "agent": {"name": "Bot", "id": "agent456"}
}
```

### User Message

User messages can include platform context:

```python
{
    "role": "user",
    "content": "Deploy my application",
    "data": {
        "cmds": [],         # Commands to approve/reject
        "tool_calls": []    # Tools to approve/reject
    },
    "platform_context": {
        "user_id": "alice123",
        "tenant_name": "production",
        "k8s_namespace": "my-app",
        "duplo_base_url": "https://api.duplocloud.net",
        "duplo_token": "eyJ...",
        "kubeconfig": "base64-encoded-kubeconfig"
    }
}
```

### Agent Message

Agent responses include response data:

```python
{
    "role": "assistant",
    "content": "I'll help you deploy. Please approve the following:",
    "data": {
        "cmds": [
            {
                "command": "kubectl apply -f deploy.yaml",
                "execute": false
            }
        ],
        "tool_calls": [
            {
                "id": "toolu_123",
                "name": "deploy_service",
                "input": {"name": "my-app", "image": "nginx:latest"},
                "execute": false,
                "tool_description": "Deploy a service",
                "input_description": {...}
            }
        ],
        "executed_tool_calls": [
            {
                "id": "toolu_456",
                "name": "check_status",
                "input": {"service": "my-app"},
                "output": "Service is running"
            }
        ]
    }
}
```

---

## Request Format

### Basic Request

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Hello, how can you help me?"
        }
    ]
}
```

### Multi-Turn Request

```json
{
    "messages": [
        {
            "role": "user",
            "content": "What is Kubernetes?"
        },
        {
            "role": "assistant",
            "content": "Kubernetes is a container orchestration platform..."
        },
        {
            "role": "user",
            "content": "How do I create a deployment?"
        }
    ]
}
```

### With Platform Context

```json
{
    "messages": [
        {
            "role": "user",
            "content": "List my pods",
            "platform_context": {
                "tenant_name": "production",
                "k8s_namespace": "web-app",
                "user_id": "alice"
            }
        }
    ]
}
```

### With Source Identifier

```json
{
    "messages": [...],
    "source": "slack"
}
```

Valid sources:
- `help-desk` (default)
- `slack`
- Custom values

---

## Response Format

### Simple Response

```json
{
    "role": "assistant",
    "content": "Here is the information you requested...",
    "data": {
        "cmds": [],
        "executed_cmds": [],
        "tool_calls": [],
        "executed_tool_calls": [],
        "url_configs": []
    }
}
```

### Response with Commands

```json
{
    "role": "assistant",
    "content": "I've analyzed the issue. Run this command to fix it:",
    "data": {
        "cmds": [
            {
                "command": "kubectl rollout restart deployment/web-app -n production",
                "execute": false,
                "files": null
            }
        ]
    }
}
```

### Response with Tool Calls

```json
{
    "role": "assistant",
    "content": "I need your approval to scale the deployment:",
    "data": {
        "tool_calls": [
            {
                "id": "toolu_scale_123",
                "name": "scale_deployment",
                "input": {
                    "deployment": "web-app",
                    "replicas": 5
                },
                "execute": false,
                "tool_description": "Scale a Kubernetes deployment",
                "input_description": {
                    "deployment": {
                        "type": "string",
                        "description": "Name of the deployment"
                    },
                    "replicas": {
                        "type": "integer",
                        "description": "Number of replicas"
                    }
                },
                "intent": "Increase capacity for traffic spike"
            }
        ]
    }
}
```

### Response with Executed Tools

```json
{
    "role": "assistant",
    "content": "I checked the status. Your deployment is healthy.",
    "data": {
        "executed_tool_calls": [
            {
                "id": "toolu_status_456",
                "name": "check_deployment_status",
                "input": {"deployment": "web-app"},
                "output": "Deployment web-app: 3/3 pods ready, healthy"
            }
        ]
    }
}
```

---

## Tool Call Flow

### Flow Diagram

```
┌────────┐       ┌───────┐       ┌───────┐       ┌────────┐
│ Client │       │ Agent │       │ Tool  │       │ Client │
└────┬───┘       └───┬───┘       └───┬───┘       └────┬───┘
     │               │               │                │
     │ "Delete pod"  │               │                │
     │ ─────────────>│               │                │
     │               │               │                │
     │               │ Needs         │                │
     │               │ approval      │                │
     │               │               │                │
     │  ToolCall     │               │                │
     │  (execute:    │               │                │
     │   false)      │               │                │
     │ <─────────────│               │                │
     │               │               │                │
     │ [User reviews and approves]   │                │
     │               │               │                │
     │ ToolCall      │               │                │
     │ (execute:true)│               │                │
     │ ─────────────>│               │                │
     │               │               │                │
     │               │ Execute       │                │
     │               │ ─────────────>│                │
     │               │               │                │
     │               │ Result        │                │
     │               │ <─────────────│                │
     │               │               │                │
     │ Response with │               │                │
     │ ExecutedTool  │               │                │
     │ <─────────────│               │                │
     │               │               │                │
```

### Step 1: Request

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Delete the pod called web-app-abc123"
        }
    ]
}
```

### Step 2: Approval Request

Agent returns tool call needing approval:

```json
{
    "role": "assistant",
    "content": "I need your approval to delete the pod:",
    "data": {
        "tool_calls": [
            {
                "id": "toolu_delete_789",
                "name": "delete_pod",
                "input": {"pod_name": "web-app-abc123", "namespace": "default"},
                "execute": false,
                "tool_description": "Delete a Kubernetes pod",
                "input_description": {...}
            }
        ]
    }
}
```

### Step 3a: Approval

Client sends back with `execute: true`:

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Delete the pod called web-app-abc123",
            "data": {
                "tool_calls": [
                    {
                        "id": "toolu_delete_789",
                        "name": "delete_pod",
                        "input": {"pod_name": "web-app-abc123", "namespace": "default"},
                        "execute": true
                    }
                ]
            }
        }
    ]
}
```

### Step 3b: Rejection

Client sends back with `rejection_reason`:

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Delete the pod called web-app-abc123",
            "data": {
                "tool_calls": [
                    {
                        "id": "toolu_delete_789",
                        "name": "delete_pod",
                        "input": {"pod_name": "web-app-abc123", "namespace": "default"},
                        "rejection_reason": "Wrong pod - I meant web-app-xyz789"
                    }
                ]
            }
        }
    ]
}
```

### Step 4: Result

Agent returns with executed tool:

```json
{
    "role": "assistant",
    "content": "Done! The pod has been deleted.",
    "data": {
        "executed_tool_calls": [
            {
                "id": "toolu_delete_789",
                "name": "delete_pod",
                "input": {"pod_name": "web-app-abc123", "namespace": "default"},
                "output": "Pod web-app-abc123 deleted successfully"
            }
        ]
    }
}
```

---

## Command Flow

### Step 1: Agent Suggests Command

```json
{
    "role": "assistant",
    "content": "To fix the issue, run this command:",
    "data": {
        "cmds": [
            {
                "command": "kubectl delete pod web-app-abc123 -n production",
                "execute": false
            }
        ]
    }
}
```

### Step 2: User Approves

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Fix my pod issue",
            "data": {
                "cmds": [
                    {
                        "command": "kubectl delete pod web-app-abc123 -n production",
                        "execute": true
                    }
                ]
            }
        }
    ]
}
```

### Step 3: Execution Result

```json
{
    "role": "assistant",
    "content": "Command executed successfully. The pod is restarting.",
    "data": {
        "executed_cmds": [
            {
                "command": "kubectl delete pod web-app-abc123 -n production",
                "output": "pod \"web-app-abc123\" deleted"
            }
        ]
    }
}
```

### Commands with Files

Some commands need files created first:

```json
{
    "data": {
        "cmds": [
            {
                "command": "helm install my-app ./chart",
                "execute": false,
                "files": [
                    {
                        "file_path": "chart/Chart.yaml",
                        "file_content": "apiVersion: v2\nname: my-app\n..."
                    },
                    {
                        "file_path": "chart/values.yaml",
                        "file_content": "replicaCount: 3\n..."
                    }
                ]
            }
        ]
    }
}
```

---

## Platform Context

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `string` | Current user identifier |
| `tenant_name` | `string` | DuploCloud tenant |
| `k8s_namespace` | `string` | Kubernetes namespace |
| `duplo_base_url` | `string` | DuploCloud API URL |
| `duplo_token` | `string` | DuploCloud API token |
| `kubeconfig` | `string` | Base64-encoded kubeconfig |
| `aws_credentials` | `object` | AWS credential info |

### Passing Context

Context is passed in user messages:

```json
{
    "role": "user",
    "content": "List my services",
    "platform_context": {
        "user_id": "alice",
        "tenant_name": "production",
        "k8s_namespace": "web-app"
    }
}
```

### Context in Multi-Turn

Context is typically included in the first message and the most recent message:

```json
{
    "messages": [
        {
            "role": "user",
            "content": "Show me my pods",
            "platform_context": {"tenant_name": "prod", "k8s_namespace": "app"}
        },
        {
            "role": "assistant",
            "content": "Here are your pods..."
        },
        {
            "role": "user",
            "content": "Now scale up the deployment",
            "platform_context": {"tenant_name": "prod", "k8s_namespace": "app"}
        }
    ]
}
```

---

## Examples

### Example 1: Simple Chat

**Request:**
```json
{
    "messages": [
        {"role": "user", "content": "What is DCAF?"}
    ]
}
```

**Response:**
```json
{
    "role": "assistant",
    "content": "DCAF (DuploCloud Agent Framework) is a Python framework for building LLM-powered AI agents...",
    "data": {
        "cmds": [],
        "tool_calls": [],
        "executed_tool_calls": []
    }
}
```

### Example 2: Tool Execution

**Request:**
```json
{
    "messages": [
        {
            "role": "user",
            "content": "Check the weather in San Francisco"
        }
    ]
}
```

**Response (tool runs automatically):**
```json
{
    "role": "assistant",
    "content": "The weather in San Francisco is 68°F and sunny.",
    "data": {
        "executed_tool_calls": [
            {
                "id": "toolu_weather_123",
                "name": "get_weather",
                "input": {"location": "San Francisco, CA"},
                "output": "68°F, sunny, humidity 45%"
            }
        ]
    }
}
```

### Example 3: Approval Workflow

**Initial Request:**
```json
{
    "messages": [
        {
            "role": "user",
            "content": "Delete my staging environment"
        }
    ]
}
```

**Response (needs approval):**
```json
{
    "role": "assistant",
    "content": "I found the staging environment. Please confirm deletion:",
    "data": {
        "tool_calls": [
            {
                "id": "toolu_delete_env_456",
                "name": "delete_environment",
                "input": {"environment": "staging", "tenant": "production"},
                "execute": false,
                "tool_description": "Delete an environment and all its resources",
                "intent": "Remove staging environment as requested"
            }
        ]
    }
}
```

**Follow-up (approved):**
```json
{
    "messages": [
        {
            "role": "user",
            "content": "Delete my staging environment",
            "data": {
                "tool_calls": [
                    {
                        "id": "toolu_delete_env_456",
                        "name": "delete_environment",
                        "input": {"environment": "staging", "tenant": "production"},
                        "execute": true
                    }
                ]
            }
        }
    ]
}
```

**Final Response:**
```json
{
    "role": "assistant",
    "content": "The staging environment has been deleted successfully.",
    "data": {
        "executed_tool_calls": [
            {
                "id": "toolu_delete_env_456",
                "name": "delete_environment",
                "input": {"environment": "staging", "tenant": "production"},
                "output": "Environment 'staging' deleted. 15 resources removed."
            }
        ]
    }
}
```

### Example 4: Command with Files

**Response with file creation:**
```json
{
    "role": "assistant",
    "content": "I'll create a Helm chart for your application. Please approve:",
    "data": {
        "cmds": [
            {
                "command": "helm install my-app ./my-app-chart --namespace production",
                "execute": false,
                "files": [
                    {
                        "file_path": "my-app-chart/Chart.yaml",
                        "file_content": "apiVersion: v2\nname: my-app\nversion: 1.0.0"
                    },
                    {
                        "file_path": "my-app-chart/values.yaml",
                        "file_content": "replicaCount: 3\nimage:\n  repository: nginx\n  tag: latest"
                    },
                    {
                        "file_path": "my-app-chart/templates/deployment.yaml",
                        "file_content": "apiVersion: apps/v1\nkind: Deployment\n..."
                    }
                ]
            }
        ]
    }
}
```

---

## See Also

- [Schemas API Reference](../api-reference/schemas.md)
- [Agent Server API Reference](../api-reference/agent-server.md)
- [Streaming Guide](./streaming.md)

