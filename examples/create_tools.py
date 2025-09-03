# test_simple_tools.py

from dcaf.tools import tool, create_tool

# Test 1: Simple tool with explicit schema
@tool(
    schema={
        "type": "object",
        "properties": {
            "x": {"type": "integer", "description": "First number"},
            "y": {"type": "integer", "description": "Second number"}
        },
        "required": ["x", "y"]
    }
)
def add_numbers(x: int, y: int, platform_context: dict) -> str:
    """Add two numbers together."""
    return f"Result: {x + y}"

print("=== Test 1: Basic Tool ===")
result = add_numbers.execute({"x": 5, "y": 3}, {"user": "alice"})
print(f"Result: {result}")
add_numbers.describe()
print()

# Test 2: Tool with approval
@tool(
    schema={
        "type": "object",
        "properties": {
            "tenant_name": {"type": "string", "description": "Tenant to delete"}
        },
        "required": ["tenant_name"]
    },
    requires_approval=True
)
def delete_tenant(tenant_name: str, platform_context: dict) -> str:
    """Delete a tenant from the system."""
    user = platform_context.get("user_id", "unknown")
    return f"Tenant '{tenant_name}' deleted by {user}"

print("=== Test 2: Approval Tool ===")
print(f"Requires approval: {delete_tenant.requires_approval}")
result = delete_tenant.execute({"tenant_name": "test"}, {"user_id": "admin"})
print(f"Result: {result}")
print()

# Test 3: Tool with no parameters
@tool(
    schema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_time(platform_context: dict) -> str:
    """Get current time."""
    return "2024-01-01 12:00:00"

print("=== Test 3: No Parameters ===")
result = get_time.execute({}, {})
print(f"Result: {result}")
print()

# Test 4: Programmatic creation
def my_function(name: str, age: int, platform_context: dict) -> str:
    return f"User {name} is {age} years old"

my_tool = create_tool(
    func=my_function,
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "User name"},
            "age": {"type": "integer", "description": "User age"}
        },
        "required": ["name", "age"]
    },
    name="create_user",
    description="Create a new user",
    requires_approval=True
)

print("=== Test 4: Programmatic ===")
print(f"Tool name: {my_tool.name}")
print(f"Description: {my_tool.description}")
result = my_tool.execute({"name": "Bob", "age": 25}, {})
print(f"Result: {result}")
print()

# Test 5: Using platform context
@tool(
    schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Action to perform"}
        },
        "required": ["action"]
    }
)
def perform_action(action: str, platform_context: dict) -> str:
    """Perform an action with context."""
    user = platform_context.get("user_id", "anonymous")
    role = platform_context.get("role", "user")
    return f"[{role}] {user} performed: {action}"

print("=== Test 5: Platform Context ===")
result = perform_action.execute(
    {"action": "delete_file"},
    {"user_id": "alice", "role": "admin"}
)
print(f"Result: {result}")
print()

# Test 6: Complex schema with optional params
@tool(
    schema={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to send"},
            "recipients": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of recipients"
            },
            "urgent": {
                "type": "boolean",
                "description": "Mark as urgent",
                "default": False
            }
        },
        "required": ["message", "recipients"]
    }
)
def send_message(platform_context: dict, message: str, recipients: list, urgent: bool = False) -> str:
    """Send a message to multiple recipients."""
    prefix = "URGENT: " if urgent else ""
    return f"{prefix}Sent '{message}' to {len(recipients)} recipients"

print("=== Test 6: Complex Schema ===")
result = send_message.execute(
    {"message": "Hello", "recipients": ["alice", "bob"], "urgent": True},
    {}
)
print(f"Result: {result}")
print(f"Schema: {send_message.get_schema()}")