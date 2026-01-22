# test_comprehensive_tools.py - Complete test suite for tool system

import json

from dcaf.tools import create_tool, tool

print("=" * 60)
print("COMPREHENSIVE TOOL SYSTEM TEST SUITE")
print("=" * 60)

# ============================================================================
# SECTION 1: BASIC TOOL CREATION
# ============================================================================
print("\n1. BASIC TOOL CREATION")
print("-" * 40)


# 1.1: Simple tool without platform_context
@tool(
    schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "First number"},
            "y": {"type": "integer", "description": "Second number"},
        },
        "required": ["x", "y"],
    }
)
def add(x: int, y: int) -> str:
    """Add two numbers."""
    return f"{x} + {y} = {x + y}"


print("1.1 Simple tool (no context):")
print(f"  Name: {add.name}")
print(f"  Has platform_context: {add.requires_platform_context}")
print(f"  Execution: {add.execute({'x': 5, 'y': 3})}")


# 1.2: Tool with platform_context
@tool(
    schema={
        "type": "object",
        "properties": {"message": {"type": "string", "description": "Message to log"}},
        "required": ["message"],
    }
)
def log_message(message: str, platform_context: dict) -> str:
    """Log a message with user context."""
    user = platform_context.get("user_id", "anonymous")
    return f"[{user}] {message}"


print("\n1.2 Tool with platform_context:")
print(f"  Has platform_context: {log_message.requires_platform_context}")
print(f"  With context: {log_message.execute({'message': 'Hello'}, {'user_id': 'alice'})}")

# ============================================================================
# SECTION 2: APPROVAL REQUIRED TOOLS
# ============================================================================
print("\n\n2. APPROVAL REQUIRED TOOLS")
print("-" * 40)


@tool(
    schema={
        "type": "object",
        "properties": {
            "resource": {"type": "string", "description": "Resource to delete"},
            "force": {"type": "boolean", "description": "Force deletion", "default": False},
        },
        "required": ["resource"],
    },
    requires_approval=True,
)
def delete_resource(resource: str, force: bool = False, platform_context: dict = None) -> str:
    """Delete a critical resource."""
    user = platform_context.get("user_id", "system") if platform_context else "system"
    mode = "force-deleted" if force else "deleted"
    return f"Resource '{resource}' {mode} by {user}"


print("2.1 Approval-required tool:")
print(f"  Requires approval: {delete_resource.requires_approval}")
print(f"  Has platform_context: {delete_resource.requires_platform_context}")
print(
    f"  Test execution: {delete_resource.execute({'resource': 'database', 'force': True}, {'user_id': 'admin'})}"
)

# ============================================================================
# SECTION 3: ALL PARAMETER TYPES
# ============================================================================
print("\n\n3. ALL JSON SCHEMA TYPES")
print("-" * 40)


@tool(
    schema={
        "type": "object",
        "properties": {
            # Basic types
            "text": {"type": "string", "description": "String parameter"},
            "count": {"type": "integer", "description": "Integer parameter"},
            "price": {"type": "number", "description": "Float/decimal parameter"},
            "active": {"type": "boolean", "description": "Boolean parameter"},
            # Array type
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Array of strings",
            },
            # Nested object
            "config": {
                "type": "object",
                "description": "Configuration object",
                "properties": {"timeout": {"type": "integer"}, "retries": {"type": "integer"}},
            },
            # Enum
            "level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Priority level",
            },
            # Optional with default
            "format": {"type": "string", "description": "Output format", "default": "json"},
        },
        "required": ["text", "count"],  # Only these are required
    }
)
def process_complex(
    text: str,
    count: int,
    price: float = 0.0,
    active: bool = True,
    tags: list = None,
    config: dict = None,
    level: str = "medium",
    format: str = "json",
) -> str:
    """Process data with all parameter types."""
    tags = tags or []
    config = config or {}
    return f"Processed {count}x '{text}' with {len(tags)} tags, level={level}, format={format}"


print("3.1 Complex schema tool:")
test_input = {
    "text": "sample",
    "count": 3,
    "price": 19.99,
    "active": True,
    "tags": ["urgent", "important"],
    "config": {"timeout": 30, "retries": 3},
    "level": "high",
    "format": "xml",
}
print(f"  Full execution: {process_complex.execute(test_input)}")
print(f"  Minimal execution: {process_complex.execute({'text': 'test', 'count': 1})}")

# ============================================================================
# SECTION 4: CUSTOM NAME AND DESCRIPTION
# ============================================================================
print("\n\n4. CUSTOM NAME AND DESCRIPTION")
print("-" * 40)


@tool(
    schema={
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
    },
    name="search_database",
    description="Search the database for matching records",
)
def db_search(query: str) -> str:
    """This docstring is overridden by custom description."""
    return f"Found 5 results for '{query}'"


print("4.1 Custom metadata:")
print("  Function name: db_search")
print(f"  Tool name: {db_search.name}")
print(f"  Tool description: {db_search.description}")

# ============================================================================
# SECTION 5: PROGRAMMATIC TOOL CREATION
# ============================================================================
print("\n\n5. PROGRAMMATIC TOOL CREATION")
print("-" * 40)


# 5.1: Function without decorator
def multiply(a: int, b: int) -> str:
    return f"{a} × {b} = {a * b}"


multiply_tool = create_tool(
    func=multiply,
    schema={
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "First number"},
            "b": {"type": "integer", "description": "Second number"},
        },
        "required": ["a", "b"],
    },
    name="multiply_numbers",
    description="Multiply two integers",
    requires_approval=False,
)

print("5.1 Programmatic creation:")
print(f"  Tool name: {multiply_tool.name}")
print(f"  Execution: {multiply_tool.execute({'a': 6, 'b': 7})}")


# 5.2: With platform_context
def audit_log(action: str, details: str, platform_context: dict) -> str:
    user = platform_context.get("user_id", "system")
    ip = platform_context.get("ip_address", "unknown")
    return f"AUDIT: [{user}@{ip}] {action}: {details}"


audit_tool = create_tool(
    func=audit_log,
    schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Action performed"},
            "details": {"type": "string", "description": "Action details"},
        },
        "required": ["action", "details"],
    },
    requires_approval=False,
)

print("\n5.2 Programmatic with context:")
print(f"  Has platform_context: {audit_tool.requires_platform_context}")
context = {"user_id": "admin", "ip_address": "192.168.1.1"}
print(f"  Execution: {audit_tool.execute({'action': 'LOGIN', 'details': 'successful'}, context)}")

# ============================================================================
# SECTION 6: TOOL INSPECTION METHODS
# ============================================================================
print("\n\n6. TOOL INSPECTION METHODS")
print("-" * 40)

print("6.1 Tool.describe() method:")
print()
delete_resource.describe()

print("\n6.2 Tool.get_schema() method (LLM format):")
schema = delete_resource.get_schema()
print(json.dumps(schema, indent=2))

print("\n6.3 Tool.__repr__() method:")
print(f"  {delete_resource}")

# ============================================================================
# SECTION 7: ERROR CASES
# ============================================================================
print("\n\n7. ERROR HANDLING")
print("-" * 40)

# 7.1: Test with wrong input types
print("7.1 Type coercion (tool handles string conversion):")
try:
    # Pass string instead of int - should work because we convert to str
    result = add.execute({"x": "5", "y": "3"})
    print(f"  String inputs: {result}")
except Exception as e:
    print(f"  Error: {e}")

# 7.2: Missing required parameters
print("\n7.2 Missing required parameters:")
try:
    result = process_complex.execute({"text": "test"})  # Missing 'count'
    print(f"  Result: {result}")
except TypeError as e:
    print(f"  Expected error: {e}")


# ============================================================================
# SECTION 8: EDGE CASES
# ============================================================================
print("\n\n8. EDGE CASES")
print("-" * 40)


# 8.1: No parameters tool
@tool(schema={"type": "object", "properties": {}, "required": []})
def get_random() -> str:
    """Get a random number."""
    import random

    return f"Random: {random.randint(1, 100)}"


print("8.1 No parameters tool:")
print(f"  Result: {get_random.execute({})}")


# 8.2: Optional platform_context with default
@tool(schema={"type": "object", "properties": {"data": {"type": "string"}}, "required": ["data"]})
def flexible_tool(data: str, platform_context: dict = None) -> str:
    """Tool with optional platform_context."""
    if platform_context:
        user = platform_context.get("user_id", "unknown")
        return f"User {user} processed: {data}"
    return f"Processed: {data}"


print("\n8.2 Optional platform_context:")
print(f"  Has platform_context: {flexible_tool.requires_platform_context}")
print(f"  With context: {flexible_tool.execute({'data': 'test'}, {'user_id': 'bob'})}")
print(f"  Without context: {flexible_tool.execute({'data': 'test'})}")


# 8.3: Return non-string (auto-converted)
@tool(
    schema={
        "type": "object",
        "properties": {"numbers": {"type": "array", "items": {"type": "integer"}}},
        "required": ["numbers"],
    }
)
def sum_list(numbers: list) -> int:  # Returns int, not str
    """Sum a list of numbers."""
    return sum(numbers)


print("\n8.3 Non-string return (auto-converted):")
result = sum_list.execute({"numbers": [1, 2, 3, 4, 5]})
print(f"  Result: {result} (type: {type(result).__name__})")

# ============================================================================
# SECTION 9: TOOL REGISTRY PATTERN
# ============================================================================
print("\n\n9. TOOL REGISTRY PATTERN")
print("-" * 40)

# Create a registry of tools
tools_registry = [
    add,
    log_message,
    delete_resource,
    process_complex,
    db_search,
    multiply_tool,
    audit_tool,
    get_random,
    flexible_tool,
    sum_list,
]

print("9.1 Registry summary:")
for t in tools_registry:
    ctx = "✓" if t.requires_platform_context else "✗"
    app = "✓" if t.requires_approval else "✗"
    print(f"  [{ctx}] [{app}] {t.name:20} - {t.description[:40]}...")

print("\n9.2 Tools requiring approval:")
approval_tools = [t for t in tools_registry if t.requires_approval]
for t in approval_tools:
    print(f"  - {t.name}")

print("\n9.3 Tools using platform_context:")
context_tools = [t for t in tools_registry if t.requires_platform_context]
for t in context_tools:
    print(f"  - {t.name}")

# ============================================================================
# SECTION 10: LLM INTEGRATION FORMAT
# ============================================================================
print("\n\n10. LLM INTEGRATION FORMAT")
print("-" * 40)

print("10.1 All tool schemas for LLM:")
all_schemas = [t.get_schema() for t in tools_registry[:3]]  # First 3 for brevity
print(json.dumps(all_schemas, indent=2))

# ============================================================================
print("\n" + "=" * 60)
print("TEST SUITE COMPLETE")
print("=" * 60)
