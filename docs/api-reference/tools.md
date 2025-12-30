# Tools API Reference

The Tools module provides a powerful system for creating callable functions that LLM agents can use. It supports JSON Schema validation, approval workflows, and platform context injection.

---

## Table of Contents

1. [Overview](#overview)
2. [Class: Tool](#class-tool)
3. [Decorator: @tool](#decorator-tool)
4. [Function: create_tool](#function-create_tool)
5. [Schema Format](#schema-format)
6. [Platform Context](#platform-context)
7. [Approval Workflows](#approval-workflows)
8. [Examples](#examples)
9. [Best Practices](#best-practices)

---

## Overview

The Tools module provides two ways to create tools:

1. **`@tool` decorator** - Transform a function into a Tool object
2. **`create_tool()` function** - Programmatically create tools

### Import

```python
from dcaf.tools import tool, create_tool, Tool
```

### Key Features

- **JSON Schema validation** for tool inputs
- **Automatic platform context detection**
- **Approval workflow support**
- **LLM-ready schema generation**
- **Tool inspection and debugging**

---

## Class: Tool

The `Tool` class is a Pydantic model that represents a callable tool.

```python
class Tool(BaseModel):
    """Container for tool metadata and configuration."""
    
    func: Callable           # The wrapped function
    name: str                # Tool name for LLM
    description: str         # Tool description
    schema: Dict[str, Any]   # JSON schema for inputs
    requires_approval: bool  # Whether approval is needed
    requires_platform_context: bool  # Whether context is needed
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `func` | `Callable` | The underlying Python function |
| `name` | `str` | Tool name (used by LLM) |
| `description` | `str` | Human-readable description |
| `schema` | `Dict` | Full JSON schema specification |
| `requires_approval` | `bool` | If `True`, requires user approval |
| `requires_platform_context` | `bool` | If `True`, expects platform context |

### Methods

#### `get_schema() -> Dict[str, Any]`

Returns the tool's JSON schema in LLM-ready format.

```python
schema = my_tool.get_schema()
# {
#     "name": "my_tool",
#     "description": "Tool description",
#     "input_schema": {...}
# }
```

#### `execute(input_args: Dict, platform_context: Dict = None) -> str`

Execute the tool with given inputs.

```python
# Without platform context
result = my_tool.execute({"param": "value"})

# With platform context
result = my_tool.execute(
    {"param": "value"},
    {"user_id": "alice", "tenant": "prod"}
)
```

#### `describe() -> None`

Print detailed information about the tool.

```python
my_tool.describe()
# Tool: my_tool
# Description: Tool description
# Requires Approval: False
# Has Platform Context: True
# Schema: {...}
```

#### `__repr__() -> str`

Pretty representation for debugging.

```python
print(my_tool)
# Tool(name='my_tool', requires_approval=False, requires_platform_context=True)
```

---

## Decorator: @tool

Transform a function into a Tool object.

```python
def tool(
    schema: Dict[str, Any],
    requires_approval: bool = True,
    name: Optional[str] = None,
    description: Optional[str] = None
) -> Callable[[Callable], Tool]
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `schema` | `Dict` | Required | JSON schema for tool inputs |
| `requires_approval` | `bool` | `True` | Require user approval before execution |
| `name` | `str` | Function name | Override the tool name |
| `description` | `str` | Docstring | Override the description |

### Basic Usage

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "greet",
        "description": "Generate a greeting message",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the person to greet"
                }
            },
            "required": ["name"]
        }
    },
    requires_approval=False
)
def greet(name: str) -> str:
    """Generate a greeting."""
    return f"Hello, {name}!"

# Use the tool
result = greet.execute({"name": "Alice"})
print(result)  # "Hello, Alice!"
```

### With Platform Context

If your function has a `platform_context` parameter, DCAF automatically detects it:

```python
@tool(
    schema={
        "name": "log_action",
        "description": "Log an action with user context",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to log"
                }
            },
            "required": ["action"]
        }
    }
)
def log_action(action: str, platform_context: dict) -> str:
    """Log an action with the current user."""
    user = platform_context.get("user_id", "unknown")
    tenant = platform_context.get("tenant_name", "default")
    return f"[{tenant}/{user}] Action: {action}"

# Verify detection
print(log_action.requires_platform_context)  # True

# Execute with context
result = log_action.execute(
    {"action": "login"},
    {"user_id": "alice", "tenant_name": "prod"}
)
print(result)  # "[prod/alice] Action: login"
```

### With Approval Required

```python
@tool(
    schema={
        "name": "delete_resource",
        "description": "Delete a resource (requires approval)",
        "input_schema": {
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "ID of resource to delete"
                },
                "force": {
                    "type": "boolean",
                    "description": "Force deletion",
                    "default": False
                }
            },
            "required": ["resource_id"]
        }
    },
    requires_approval=True  # User must approve
)
def delete_resource(resource_id: str, force: bool = False) -> str:
    """Delete a resource from the system."""
    mode = "force-deleted" if force else "deleted"
    return f"Resource {resource_id} has been {mode}"

# This tool will require approval before execution
print(delete_resource.requires_approval)  # True
```

### Custom Name and Description

```python
@tool(
    schema={
        "name": "search_db",
        "description": "Search the database",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    name="database_search",           # Override name
    description="Search for records"  # Override docstring
)
def internal_search(query: str) -> str:
    """This docstring is overridden."""
    return f"Found 5 results for: {query}"

print(internal_search.name)  # "database_search"
print(internal_search.description)  # "Search for records"
```

---

## Function: create_tool

Create a tool programmatically without using a decorator.

```python
def create_tool(
    func: Callable,
    schema: Dict[str, Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
    requires_approval: bool = False
) -> Tool
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `func` | `Callable` | Required | Function to wrap |
| `schema` | `Dict` | Required | JSON schema for inputs |
| `name` | `str` | Function name | Tool name |
| `description` | `str` | Docstring | Tool description |
| `requires_approval` | `bool` | `False` | Require approval |

### Usage

```python
from dcaf.tools import create_tool

# Define a function
def multiply(a: int, b: int) -> str:
    """Multiply two numbers."""
    return f"{a} × {b} = {a * b}"

# Create the tool
multiply_tool = create_tool(
    func=multiply,
    schema={
        "name": "multiply",
        "description": "Multiply two integers",
        "input_schema": {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"}
            },
            "required": ["a", "b"]
        }
    }
)

# Use the tool
result = multiply_tool.execute({"a": 6, "b": 7})
print(result)  # "6 × 7 = 42"
```

### When to Use create_tool

- Creating tools from existing functions you can't modify
- Dynamic tool generation at runtime
- Building tools from configuration files
- Testing and mocking

---

## Schema Format

Tools use JSON Schema to define their input parameters.

### Required Structure

```python
schema = {
    "name": "tool_name",              # Required: Unique identifier
    "description": "What it does",     # Required: LLM-readable description
    "input_schema": {                  # Required: Parameter schema
        "type": "object",              # Must be "object"
        "properties": {...},           # Parameter definitions
        "required": [...]              # Required parameters
    }
}
```

### Parameter Types

#### String

```python
"username": {
    "type": "string",
    "description": "The username",
    "minLength": 3,
    "maxLength": 50
}
```

#### Integer

```python
"count": {
    "type": "integer",
    "description": "Number of items",
    "minimum": 1,
    "maximum": 100
}
```

#### Number (Float)

```python
"price": {
    "type": "number",
    "description": "Price in dollars",
    "minimum": 0
}
```

#### Boolean

```python
"active": {
    "type": "boolean",
    "description": "Whether the item is active",
    "default": True
}
```

#### Enum

```python
"status": {
    "type": "string",
    "enum": ["pending", "active", "completed"],
    "description": "Current status"
}
```

#### Array

```python
"tags": {
    "type": "array",
    "items": {"type": "string"},
    "description": "List of tags"
}
```

#### Nested Object

```python
"config": {
    "type": "object",
    "description": "Configuration options",
    "properties": {
        "timeout": {"type": "integer"},
        "retries": {"type": "integer"}
    }
}
```

### Complete Example

```python
@tool(
    schema={
        "name": "create_user",
        "description": "Create a new user account",
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Unique username",
                    "minLength": 3,
                    "maxLength": 30
                },
                "email": {
                    "type": "string",
                    "description": "Email address",
                    "format": "email"
                },
                "role": {
                    "type": "string",
                    "enum": ["user", "admin", "moderator"],
                    "description": "User role",
                    "default": "user"
                },
                "permissions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of permissions"
                },
                "profile": {
                    "type": "object",
                    "description": "User profile data",
                    "properties": {
                        "display_name": {"type": "string"},
                        "bio": {"type": "string"}
                    }
                }
            },
            "required": ["username", "email"]
        }
    },
    requires_approval=True
)
def create_user(
    username: str,
    email: str,
    role: str = "user",
    permissions: list = None,
    profile: dict = None
) -> str:
    """Create a new user account."""
    return f"Created user {username} with role {role}"
```

---

## Platform Context

Platform context allows tools to access runtime information like user identity, tenant, and credentials.

### How It Works

1. If your function has a `platform_context` parameter, DCAF sets `requires_platform_context=True`
2. When the tool is executed, the agent passes context from the request
3. Your function receives the context and can use it

### Available Context Fields

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | `str` | Current user identifier |
| `tenant_name` | `str` | DuploCloud tenant name |
| `k8s_namespace` | `str` | Kubernetes namespace |
| `duplo_base_url` | `str` | DuploCloud API URL |
| `duplo_token` | `str` | DuploCloud API token |
| `kubeconfig` | `str` | Base64-encoded kubeconfig |
| `aws_credentials` | `Dict` | AWS credential information |

### Example with Context

```python
@tool(
    schema={
        "name": "deploy_service",
        "description": "Deploy a service to the current tenant",
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service to deploy"
                },
                "image": {
                    "type": "string",
                    "description": "Docker image to deploy"
                }
            },
            "required": ["service_name", "image"]
        }
    },
    requires_approval=True
)
def deploy_service(
    service_name: str,
    image: str,
    platform_context: dict
) -> str:
    """Deploy a service using platform context."""
    tenant = platform_context.get("tenant_name", "unknown")
    namespace = platform_context.get("k8s_namespace", "default")
    user = platform_context.get("user_id", "system")
    
    # Use context for deployment
    return f"Deployed {service_name} ({image}) to {tenant}/{namespace} by {user}"
```

### Optional Platform Context

You can make platform context optional with a default value:

```python
@tool(
    schema={...}
)
def flexible_tool(data: str, platform_context: dict = None) -> str:
    """Tool that works with or without context."""
    if platform_context:
        user = platform_context.get("user_id", "unknown")
        return f"User {user} processed: {data}"
    return f"Processed: {data}"

# Works both ways
result1 = flexible_tool.execute({"data": "test"})
result2 = flexible_tool.execute({"data": "test"}, {"user_id": "alice"})
```

---

## Approval Workflows

Tools that modify state or perform sensitive operations should require approval.

### How Approval Works

1. Agent calls tool with `requires_approval=True`
2. Instead of executing, the agent returns a `ToolCall` object
3. Client presents the tool call to the user for approval
4. User approves or rejects (with optional reason)
5. Client sends the decision back to the agent
6. If approved, agent executes the tool

### Marking Tools for Approval

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
                    "description": "EC2 instance ID"
                }
            },
            "required": ["instance_id"]
        }
    },
    requires_approval=True  # This is the key!
)
def terminate_instance(instance_id: str) -> str:
    """Terminate an EC2 instance."""
    # This only runs after user approval
    return f"Instance {instance_id} terminated"
```

### Approval Response Format

When a tool requires approval, the agent returns:

```python
AgentMessage(
    content="I need your approval to execute the following tools:",
    data=Data(
        tool_calls=[
            ToolCall(
                id="unique-tool-use-id",
                name="terminate_instance",
                input={"instance_id": "i-1234567890abcdef0"},
                tool_description="Terminate an EC2 instance",
                input_description={
                    "instance_id": {
                        "type": "string",
                        "description": "EC2 instance ID"
                    }
                },
                execute=False  # Not yet approved
            )
        ]
    )
)
```

### Sending Approval

```python
# Client sends back with execute=True or rejection_reason
messages = {
    "messages": [
        {
            "role": "user",
            "content": "Terminate the instance",
            "data": {
                "tool_calls": [
                    {
                        "id": "unique-tool-use-id",
                        "name": "terminate_instance",
                        "input": {"instance_id": "i-1234567890abcdef0"},
                        "execute": True  # Approved!
                        # OR
                        # "rejection_reason": "Wrong instance"
                    }
                ]
            }
        }
    ]
}
```

---

## Examples

### Example 1: Simple Calculator

```python
from dcaf.tools import tool

@tool(
    schema={
        "name": "calculate",
        "description": "Perform arithmetic operations",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["add", "subtract", "multiply", "divide"],
                    "description": "The operation to perform"
                },
                "a": {"type": "number", "description": "First operand"},
                "b": {"type": "number", "description": "Second operand"}
            },
            "required": ["operation", "a", "b"]
        }
    },
    requires_approval=False
)
def calculate(operation: str, a: float, b: float) -> str:
    ops = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else "undefined"
    }
    result = ops[operation](a, b)
    return f"{a} {operation} {b} = {result}"

# Test
print(calculate.execute({"operation": "multiply", "a": 7, "b": 8}))
# "7 multiply 8 = 56"
```

### Example 2: Database Query Tool

```python
@tool(
    schema={
        "name": "query_database",
        "description": "Execute a read-only database query",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": ["users", "orders", "products"],
                    "description": "Table to query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100
                },
                "filters": {
                    "type": "object",
                    "description": "Filter conditions"
                }
            },
            "required": ["table"]
        }
    },
    requires_approval=False
)
def query_database(
    table: str,
    limit: int = 10,
    filters: dict = None,
    platform_context: dict = None
) -> str:
    """Query the database with optional filters."""
    tenant = platform_context.get("tenant_name", "default") if platform_context else "default"
    
    # Simulated query
    return f"Queried {table} in {tenant}, limit={limit}, filters={filters}"
```

### Example 3: Tool Registry

```python
from dcaf.tools import tool, Tool
from typing import List

# Create multiple tools
@tool(schema={...}, requires_approval=False)
def tool_a(x: str) -> str:
    return f"A: {x}"

@tool(schema={...}, requires_approval=True)
def tool_b(y: str, platform_context: dict) -> str:
    return f"B: {y}"

@tool(schema={...}, requires_approval=False)
def tool_c(z: int) -> str:
    return f"C: {z}"

# Create a registry
tools: List[Tool] = [tool_a, tool_b, tool_c]

# Analyze tools
print("Tool Analysis:")
print("-" * 50)
for t in tools:
    ctx = "✓" if t.requires_platform_context else "✗"
    app = "✓" if t.requires_approval else "✗"
    print(f"  {t.name:20} Context: {ctx}  Approval: {app}")

# Filter by requirements
approval_tools = [t for t in tools if t.requires_approval]
context_tools = [t for t in tools if t.requires_platform_context]
```

---

## Best Practices

### 1. Clear Descriptions

```python
# Good: Specific and actionable
"description": "Delete a user account and all associated data permanently"

# Bad: Vague
"description": "Delete user"
```

### 2. Appropriate Approval

```python
# Require approval for:
# - Destructive operations (delete, terminate, drop)
# - State changes (create, update, modify)
# - Cost-incurring actions (deploy, scale up)
# - Security-sensitive operations

# No approval needed for:
# - Read-only operations (get, list, describe)
# - Calculations
# - Information retrieval
```

### 3. Parameter Validation

```python
# Use constraints in schema
"count": {
    "type": "integer",
    "minimum": 1,
    "maximum": 1000,
    "description": "Number of items (1-1000)"
}
```

### 4. Helpful Error Messages

```python
def my_tool(param: str) -> str:
    if not param:
        return "Error: Parameter cannot be empty"
    if len(param) > 100:
        return f"Error: Parameter too long ({len(param)} > 100)"
    # ...
```

### 5. Use Enums for Fixed Options

```python
"status": {
    "type": "string",
    "enum": ["pending", "active", "completed"],
    "description": "One of: pending, active, completed"
}
```

---

## See Also

- [Agents API Reference](./agents.md)
- [Building Tools Guide](../guides/building-tools.md)
- [Examples](../examples/examples.md)

