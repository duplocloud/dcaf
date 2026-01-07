# Building Tools Guide

This guide covers everything you need to know about creating tools for DCAF agents, from basic tools to advanced patterns.

---

## Table of Contents

1. [Introduction](#introduction)
2. [Your First Tool](#your-first-tool)
3. [Schema Definition Options](#schema-definition-options)
4. [Platform Context](#platform-context)
5. [Approval Workflows](#approval-workflows)
6. [Advanced Patterns](#advanced-patterns)
7. [Testing Tools](#testing-tools)
8. [Best Practices](#best-practices)

---

## Introduction

Tools are functions that LLM agents can call to interact with external systems, perform calculations, or execute operations. In DCAF, tools are:

- **Flexibly defined**: Auto-generate schema, use dict, or use Pydantic models
- **Type-safe**: JSON Schema validates inputs
- **Context-aware**: Can access platform context
- **Approval-enabled**: Support human-in-the-loop workflows
- **LLM-ready**: Automatically formatted for LLM consumption

### When to Use Tools

✅ **Use tools for:**
- External API calls
- Database operations
- File system operations
- Calculations and transformations
- Any operation that needs structured input

❌ **Don't use tools for:**
- Simple text responses
- Information already in the prompt
- Operations the LLM can do directly (math, formatting)

---

## Your First Tool

### Step 1: Import the Decorator

```python
from dcaf.tools import tool
```

### Step 2: Create the Tool

The simplest approach is to let DCAF auto-generate the schema from your function signature:

```python
@tool(description="Generate a personalized greeting for a user")
def greet_user(name: str, language: str = "english") -> str:
    """Generate a personalized greeting."""
    greetings = {
        "english": f"Hello, {name}! Welcome!",
        "spanish": f"¡Hola, {name}! ¡Bienvenido!",
        "french": f"Bonjour, {name}! Bienvenue!"
    }
    return greetings.get(language, greetings["english"])
```

That's it! DCAF automatically creates the JSON schema from the function parameters.

### Step 3: Use the Tool

```python
# Test directly
result = greet_user.execute({"name": "Alice", "language": "spanish"})
print(result)  # ¡Hola, Alice! ¡Bienvenido!

# Add to agent
from dcaf.core import Agent

agent = Agent(
    tools=[greet_user],
    system_prompt="You are a friendly greeter."
)
```

---

## Schema Definition Options

DCAF supports three ways to define tool input schemas, giving you flexibility based on your needs.

### Option 1: Auto-Generate (Recommended for Simple Tools)

Let DCAF infer the schema from your function signature:

```python
@tool(description="Create a new Kubernetes deployment")
def create_deployment(
    name: str,
    image: str,
    replicas: int = 1,
    force: bool = False
) -> str:
    """Create a Kubernetes deployment."""
    return f"Created {name} with image {image}, {replicas} replicas"
```

DCAF automatically generates:

```json
{
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "image": {"type": "string"},
        "replicas": {"type": "integer", "default": 1},
        "force": {"type": "boolean", "default": false}
    },
    "required": ["name", "image"]
}
```

### Option 2: Dict Schema (Full JSON Schema Control)

For advanced validation (enums, patterns, min/max values):

```python
@tool(
    description="Create a new Kubernetes deployment",
    requires_approval=True,
    schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Deployment name",
                "minLength": 1,
                "maxLength": 63,
                "pattern": "^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
            },
            "image": {
                "type": "string",
                "description": "Docker image (e.g., nginx:latest)"
            },
            "replicas": {
                "type": "integer",
                "description": "Number of replicas",
                "minimum": 1,
                "maximum": 10,
                "default": 1
            },
            "namespace": {
                "type": "string",
                "enum": ["default", "production", "staging"],
                "description": "Target namespace"
            }
        },
        "required": ["name", "image"]
    }
)
def create_deployment(
    name: str,
    image: str,
    replicas: int = 1,
    namespace: str = "default"
) -> str:
    """Create a Kubernetes deployment."""
    return f"Created {name} in {namespace}"
```

### Option 3: Pydantic Model (Type-Safe with IDE Support)

For production tools with complex schemas, use Pydantic models:

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class CreateDeploymentInput(BaseModel):
    """Input schema for deployment creation."""
    
    name: str = Field(
        ...,
        description="Deployment name",
        min_length=1,
        max_length=63,
        pattern="^[a-z0-9]([-a-z0-9]*[a-z0-9])?$"
    )
    image: str = Field(
        ...,
        description="Docker image (e.g., nginx:latest)"
    )
    replicas: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of replicas"
    )
    namespace: Literal["default", "production", "staging"] = Field(
        default="default",
        description="Target namespace"
    )

@tool(
    description="Create a new Kubernetes deployment",
    requires_approval=True,
    schema=CreateDeploymentInput  # Just pass the model class!
)
def create_deployment(
    name: str,
    image: str,
    replicas: int = 1,
    namespace: str = "default"
) -> str:
    """Create a Kubernetes deployment."""
    return f"Created {name} in {namespace}"
```

!!! tip "Why Pydantic?"
    Pydantic models give you:
    
    - **IDE autocomplete** when defining the schema
    - **Type checking** at development time
    - **Reusable schemas** across multiple tools
    - **Input validation** - you can validate inputs in your tool:
      ```python
      def create_deployment(name: str, image: str, ...) -> str:
          # Optional: validate inputs
          validated = CreateDeploymentInput(name=name, image=image, ...)
          # Now you have type-safe access with IDE support
      ```

### Choosing the Right Approach

| Use Case | Recommended Approach |
|----------|---------------------|
| Quick prototyping | Auto-generate |
| Simple tools (few params) | Auto-generate |
| Need enums/constraints | Dict or Pydantic |
| Production tools | Pydantic model |
| Sharing schemas across tools | Pydantic model |
| Dynamic schema generation | Dict schema |

### JSON Schema Reference

When using dict schemas, these are the common JSON Schema features:

#### String Constraints

```python
"username": {
    "type": "string",
    "description": "The username",
    "minLength": 3,
    "maxLength": 50,
    "pattern": "^[a-z0-9_]+$"
}
```

#### Numeric Constraints

```python
"count": {
    "type": "integer",
    "minimum": 1,
    "maximum": 100
}

"temperature": {
    "type": "number",
    "minimum": -273.15
}
```

#### Enums

```python
"priority": {
    "type": "string",
    "enum": ["low", "medium", "high", "critical"]
}
```

#### Arrays

```python
"tags": {
    "type": "array",
    "items": {"type": "string"},
    "minItems": 1,
    "maxItems": 10
}
```

#### Nested Objects

```python
"config": {
    "type": "object",
    "properties": {
        "timeout": {"type": "integer"},
        "retries": {"type": "integer"}
    },
    "required": ["timeout"]
}
```

---

## Platform Context

Platform context allows tools to access runtime information about the user, tenant, and environment.

### Enabling Platform Context

Simply add `platform_context: dict` as a parameter:

```python
@tool(
    schema={
        "name": "list_user_resources",
        "description": "List resources for the current user",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_type": {
                    "type": "string",
                    "enum": ["pods", "services", "deployments"]
                }
            },
            "required": ["resource_type"]
        }
    }
)
def list_user_resources(
    resource_type: str,
    platform_context: dict  # DCAF auto-detects this
) -> str:
    """List resources in the user's namespace."""
    tenant = platform_context.get("tenant_name", "default")
    namespace = platform_context.get("k8s_namespace", "default")
    user_id = platform_context.get("user_id", "unknown")
    
    # Use context for filtered query
    return f"Found 5 {resource_type} in {tenant}/{namespace} for {user_id}"
```

### Available Context Fields

```python
platform_context = {
    "user_id": "alice123",           # Current user ID
    "tenant_name": "production",      # DuploCloud tenant
    "k8s_namespace": "my-app",        # Kubernetes namespace
    "duplo_base_url": "https://...",  # DuploCloud API URL
    "duplo_token": "eyJ...",          # DuploCloud token
    "kubeconfig": "base64...",        # Encoded kubeconfig
    "aws_credentials": {...}           # AWS credential info
}
```

### Using Context for Authorization

```python
@tool(
    schema={
        "name": "delete_resource",
        "description": "Delete a resource",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_id": {"type": "string"}
            },
            "required": ["resource_id"]
        }
    },
    requires_approval=True
)
def delete_resource(
    resource_id: str,
    platform_context: dict
) -> str:
    """Delete a resource with authorization check."""
    user_id = platform_context.get("user_id")
    tenant = platform_context.get("tenant_name")
    
    # Authorization check
    if not user_id:
        return "Error: User not authenticated"
    
    # Audit log
    print(f"AUDIT: {user_id} deleting {resource_id} in {tenant}")
    
    # Perform deletion
    return f"Deleted {resource_id}"
```

### Using Context for API Calls

```python
import requests

@tool(
    schema={
        "name": "get_tenant_services",
        "description": "List all services in the tenant",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
)
def get_tenant_services(platform_context: dict) -> str:
    """Get services from DuploCloud API."""
    base_url = platform_context.get("duplo_base_url")
    token = platform_context.get("duplo_token")
    tenant = platform_context.get("tenant_name")
    
    if not all([base_url, token, tenant]):
        return "Error: Missing DuploCloud credentials"
    
    response = requests.get(
        f"{base_url}/subscriptions/{tenant}/GetNativeServices",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        services = response.json()
        return f"Found {len(services)} services"
    else:
        return f"Error: {response.status_code}"
```

---

## Approval Workflows

### When to Require Approval

Require approval for operations that:

- **Modify state** (create, update, delete)
- **Cost money** (provision resources, scale up)
- **Are irreversible** (delete, terminate)
- **Affect security** (change permissions, expose ports)
- **Impact production** (deployments, rollbacks)

### Creating Approval-Required Tools

```python
@tool(
    schema={
        "name": "terminate_instance",
        "description": "Terminate an EC2 instance",
        "input_schema": {
            "type": "object",
            "properties": {
                "instance_id": {
                    "type": "string",
                    "description": "EC2 instance ID (e.g., i-1234567890abcdef0)"
                },
                "force": {
                    "type": "boolean",
                    "description": "Force termination even if instance is running",
                    "default": False
                }
            },
            "required": ["instance_id"]
        }
    },
    requires_approval=True  # <-- Key setting
)
def terminate_instance(
    instance_id: str,
    force: bool = False,
    platform_context: dict = None
) -> str:
    """Terminate an EC2 instance."""
    user = platform_context.get("user_id", "system") if platform_context else "system"
    
    # Only executes after user approval
    return f"Instance {instance_id} terminated by {user} (force={force})"
```

### User Approval Flow

1. **Agent calls tool** → DCAF creates `ToolCall` object
2. **Agent returns** → Client receives pending tool call
3. **User reviews** → Sees tool, inputs, and description
4. **User approves/rejects** → Sets `execute=True` or `rejection_reason`
5. **Client sends back** → Agent receives decision
6. **Tool executes** → If approved, runs and returns result

### Client-Side Display

```python
# Agent returns this for approval
{
    "content": "I need your approval to terminate the instance:",
    "data": {
        "tool_calls": [
            {
                "id": "toolu_abc123",
                "name": "terminate_instance",
                "input": {
                    "instance_id": "i-1234567890abcdef0",
                    "force": False
                },
                "tool_description": "Terminate an EC2 instance",
                "input_description": {
                    "instance_id": {
                        "type": "string",
                        "description": "EC2 instance ID"
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force termination"
                    }
                },
                "execute": False
            }
        ]
    }
}
```

### Sending Approval

```python
# User approves
{
    "messages": [
        {
            "role": "user",
            "content": "Terminate the instance",
            "data": {
                "tool_calls": [
                    {
                        "id": "toolu_abc123",
                        "name": "terminate_instance",
                        "input": {"instance_id": "i-123...", "force": False},
                        "execute": True  # Approved!
                    }
                ]
            }
        }
    ]
}

# User rejects
{
    "messages": [
        {
            "role": "user",
            "content": "Terminate the instance",
            "data": {
                "tool_calls": [
                    {
                        "id": "toolu_abc123",
                        "name": "terminate_instance",
                        "input": {"instance_id": "i-123...", "force": False},
                        "rejection_reason": "Wrong instance - I meant i-987..."
                    }
                ]
            }
        }
    ]
}
```

---

## Advanced Patterns

### Pattern 1: Tool Composition

```python
from dcaf.tools import tool, Tool
from typing import List

def create_crud_tools(resource_name: str, requires_delete_approval: bool = True) -> List[Tool]:
    """Generate CRUD tools for a resource."""
    
    @tool(
        schema={
            "name": f"create_{resource_name}",
            "description": f"Create a new {resource_name}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "config": {"type": "object"}
                },
                "required": ["name"]
            }
        },
        requires_approval=True
    )
    def create_resource(name: str, config: dict = None) -> str:
        return f"Created {resource_name}: {name}"
    
    @tool(
        schema={
            "name": f"get_{resource_name}",
            "description": f"Get a {resource_name} by name",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }
        },
        requires_approval=False
    )
    def get_resource(name: str) -> str:
        return f"Found {resource_name}: {name}"
    
    @tool(
        schema={
            "name": f"delete_{resource_name}",
            "description": f"Delete a {resource_name}",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }
        },
        requires_approval=requires_delete_approval
    )
    def delete_resource(name: str) -> str:
        return f"Deleted {resource_name}: {name}"
    
    return [create_resource, get_resource, delete_resource]

# Usage
project_tools = create_crud_tools("project")
user_tools = create_crud_tools("user", requires_delete_approval=True)
```

### Pattern 2: Async Tool Execution

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dcaf.tools import tool

executor = ThreadPoolExecutor(max_workers=4)

@tool(
    schema={
        "name": "long_running_operation",
        "description": "Execute a long-running operation",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation_id": {"type": "string"}
            },
            "required": ["operation_id"]
        }
    }
)
def long_running_operation(operation_id: str) -> str:
    """Execute a long operation with timeout handling."""
    import time
    
    def do_work():
        time.sleep(5)  # Simulated work
        return f"Operation {operation_id} completed"
    
    try:
        future = executor.submit(do_work)
        result = future.result(timeout=30)
        return result
    except TimeoutError:
        return f"Operation {operation_id} timed out"
```

### Pattern 3: Tool with Retry Logic

```python
import time
from dcaf.tools import tool

@tool(
    schema={
        "name": "api_call_with_retry",
        "description": "Make an API call with automatic retry",
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {"type": "string"},
                "max_retries": {"type": "integer", "default": 3}
            },
            "required": ["endpoint"]
        }
    }
)
def api_call_with_retry(endpoint: str, max_retries: int = 3) -> str:
    """Make API call with exponential backoff retry."""
    import requests
    
    for attempt in range(max_retries):
        try:
            response = requests.get(endpoint, timeout=10)
            response.raise_for_status()
            return f"Success: {response.json()}"
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # Exponential backoff
                time.sleep(wait)
            else:
                return f"Failed after {max_retries} attempts: {e}"
    
    return "Unexpected error"
```

### Pattern 4: Tool with Validation

```python
import re
from dcaf.tools import tool

@tool(
    schema={
        "name": "create_user",
        "description": "Create a new user account",
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {"type": "string"},
                "email": {"type": "string"},
                "role": {"type": "string", "enum": ["user", "admin"]}
            },
            "required": ["username", "email", "role"]
        }
    },
    requires_approval=True
)
def create_user(username: str, email: str, role: str) -> str:
    """Create user with validation."""
    # Validate username
    if not re.match(r'^[a-z0-9_]{3,20}$', username):
        return "Error: Username must be 3-20 lowercase alphanumeric characters"
    
    # Validate email
    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return "Error: Invalid email format"
    
    # Validate role
    if role not in ["user", "admin"]:
        return f"Error: Invalid role '{role}'"
    
    # Create user
    return f"Created user {username} ({email}) with role {role}"
```

---

## Testing Tools

### Unit Testing

```python
import pytest
from dcaf.tools import tool

@tool(
    schema={
        "name": "calculate",
        "description": "Perform calculation",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["add", "subtract"]},
                "a": {"type": "number"},
                "b": {"type": "number"}
            },
            "required": ["operation", "a", "b"]
        }
    }
)
def calculate(operation: str, a: float, b: float) -> str:
    if operation == "add":
        return str(a + b)
    elif operation == "subtract":
        return str(a - b)
    return "Unknown operation"

class TestCalculateTool:
    def test_add(self):
        result = calculate.execute({"operation": "add", "a": 5, "b": 3})
        assert result == "8"
    
    def test_subtract(self):
        result = calculate.execute({"operation": "subtract", "a": 10, "b": 4})
        assert result == "6"
    
    def test_tool_metadata(self):
        assert calculate.name == "calculate"
        assert calculate.requires_approval == False
        assert calculate.requires_platform_context == False
    
    def test_schema(self):
        schema = calculate.get_schema()
        assert schema["name"] == "calculate"
        assert "input_schema" in schema
```

### Testing with Platform Context

```python
@tool(
    schema={
        "name": "greet_user",
        "description": "Greet the current user",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
)
def greet_user(platform_context: dict) -> str:
    user = platform_context.get("user_id", "stranger")
    return f"Hello, {user}!"

class TestGreetUserTool:
    def test_with_context(self):
        context = {"user_id": "alice"}
        result = greet_user.execute({}, context)
        assert result == "Hello, alice!"
    
    def test_without_user(self):
        result = greet_user.execute({}, {})
        assert result == "Hello, stranger!"
    
    def test_requires_context(self):
        assert greet_user.requires_platform_context == True
```

### Integration Testing

```python
from dcaf.llm import BedrockLLM
from dcaf.agents import ToolCallingAgent
from dcaf.tools import tool

@tool(schema={...})
def my_tool(param: str) -> str:
    return f"Result: {param}"

def test_agent_uses_tool():
    llm = BedrockLLM()
    agent = ToolCallingAgent(
        llm=llm,
        tools=[my_tool],
        system_prompt="Use the tool when asked."
    )
    
    response = agent.invoke({
        "messages": [
            {"role": "user", "content": "Call my_tool with 'test'"}
        ]
    })
    
    # Check that tool was executed
    executed = response.data.executed_tool_calls
    assert len(executed) > 0
    assert executed[0].name == "my_tool"
```

---

## Best Practices

### 1. Clear, Descriptive Names

```python
# ✅ Good
"name": "delete_kubernetes_deployment"
"name": "get_user_email_by_id"
"name": "calculate_monthly_cost"

# ❌ Bad
"name": "delete"
"name": "do_thing"
"name": "process"
```

### 2. Comprehensive Descriptions

```python
# ✅ Good
"description": "Delete a Kubernetes deployment and all associated pods. This action is irreversible."

# ❌ Bad
"description": "Delete deployment"
```

### 3. Validate Early, Fail Fast

```python
@tool(schema={...})
def create_resource(name: str, config: dict) -> str:
    # Validate immediately
    if not name:
        return "Error: Name is required"
    if len(name) > 63:
        return "Error: Name must be 63 characters or less"
    if not name[0].isalpha():
        return "Error: Name must start with a letter"
    
    # Only proceed if valid
    return f"Created: {name}"
```

### 4. Return Informative Results

```python
# ✅ Good
return f"Created deployment '{name}' with {replicas} replicas in namespace '{namespace}'"

# ❌ Bad
return "Done"
```

### 5. Handle Errors Gracefully

```python
@tool(schema={...})
def api_call(endpoint: str) -> str:
    try:
        response = requests.get(endpoint)
        response.raise_for_status()
        return f"Success: {response.json()}"
    except requests.ConnectionError:
        return "Error: Could not connect to server"
    except requests.Timeout:
        return "Error: Request timed out"
    except requests.HTTPError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: Unexpected error - {str(e)}"
```

### 6. Use Appropriate Approval Settings

```python
# Read operations - no approval needed
@tool(schema={...}, requires_approval=False)
def list_resources(): ...

@tool(schema={...}, requires_approval=False)
def get_status(): ...

# Write operations - approval recommended
@tool(schema={...}, requires_approval=True)
def create_resource(): ...

@tool(schema={...}, requires_approval=True)
def delete_resource(): ...
```

### 7. Document Platform Context Usage

```python
@tool(
    schema={
        "name": "tenant_specific_action",
        "description": "Perform action in current tenant. Requires tenant_name and duplo_token in platform context.",
        "input_schema": {...}
    }
)
def tenant_specific_action(data: str, platform_context: dict) -> str:
    """
    Perform action in tenant.
    
    Platform context requirements:
    - tenant_name: Current tenant name
    - duplo_token: API authentication token
    """
    pass
```

---

## See Also

- [Tools API Reference](../api-reference/tools.md)
- [Agents API Reference](../api-reference/agents.md)
- [Creating Custom Agents](./creating-custom-agents.md)
- [Examples](../examples/examples.md)


