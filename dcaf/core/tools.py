"""
Tool system for creating LLM-powered agents with approval workflows.

Supports three usage patterns:

1. Simple (auto-schema from function signature):

   @tool(description="Get weather for a city")
   def get_weather(city: str, units: str = "celsius") -> str:
       return f"Weather in {city}: 72°F"

2. Dict schema (for full JSON Schema control):

   @tool(
       schema={
           "type": "object",
           "properties": {
               "city": {"type": "string", "enum": ["NYC", "LA", "CHI"]}
           },
           "required": ["city"]
       },
       description="Get weather for specific cities"
   )
   def get_weather(city: str) -> str:
       return f"Weather in {city}: 72°F"

3. Pydantic model (for type-safe schema with IDE support):

   from pydantic import BaseModel, Field
   from typing import Literal

   class WeatherInput(BaseModel):
       city: Literal["NYC", "LA", "CHI"] = Field(..., description="City")

   @tool(schema=WeatherInput, description="Get weather")
   def get_weather(city: str) -> str:
       return f"Weather in {city}: 72°F"
"""

import inspect
import json
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict

# Type mapping from Python types to JSON Schema types
PYTHON_TO_JSON_TYPE = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _normalize_schema(schema: Any) -> dict[str, Any]:
    """
    Normalize a schema to a JSON Schema dict.

    Accepts:
    - Dict: returned as-is
    - Pydantic model class: converted via model_json_schema()
    - Pydantic model instance: converted via model_json_schema()

    This allows agent authors to use whichever approach they prefer:

        # Dict (explicit control)
        @tool(schema={"type": "object", "properties": {...}})
        def my_tool(): ...

        # Pydantic model (type-safe, IDE support)
        @tool(schema=MyInputModel)
        def my_tool(): ...

    Args:
        schema: A dict, Pydantic model class, or Pydantic model instance

    Returns:
        JSON Schema as a dict

    Raises:
        TypeError: If schema is not a supported type
    """
    if schema is None:
        return {}

    # Already a dict - return as-is
    if isinstance(schema, dict):
        return schema

    # Check if it's a Pydantic model class or instance
    # Pydantic v2: has model_json_schema (class method)
    if hasattr(schema, "model_json_schema"):
        # It's a Pydantic v2 model class
        return dict(schema.model_json_schema())

    # Check if it's a Pydantic model instance
    if hasattr(schema, "__class__") and hasattr(schema.__class__, "model_json_schema"):
        # It's a Pydantic v2 model instance - get schema from class
        return dict(schema.__class__.model_json_schema())

    # Pydantic v1 fallback: has .schema() class method
    if hasattr(schema, "schema") and callable(getattr(schema, "schema", None)):
        return dict(schema.schema())

    # Unknown type
    raise TypeError(
        f"schema must be a dict or Pydantic model, got {type(schema).__name__}. "
        f"Examples:\n"
        f"  @tool(schema={{'type': 'object', ...}})\n"
        f"  @tool(schema=MyPydanticModel)"
    )


def _get_json_type(python_type: type) -> str:
    """Convert Python type to JSON Schema type."""
    # Handle Optional types (Union[X, None])
    origin = get_origin(python_type)
    if origin is Union:
        args = get_args(python_type)
        # Filter out NoneType for Optional
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1:
            return _get_json_type(non_none_args[0])
        # Multiple types - just use string as fallback
        return "string"

    # Handle List[X]
    if origin is list:
        return "array"

    # Handle Dict[X, Y]
    if origin is dict:
        return "object"

    # Basic types
    return PYTHON_TO_JSON_TYPE.get(python_type, "string")


def _generate_schema_from_function(func: Callable) -> dict[str, Any]:
    """
    Generate JSON Schema from function signature.

    Args:
        func: The function to analyze

    Returns:
        JSON Schema dict compatible with Anthropic's tool format
    """
    sig = inspect.signature(func)

    # Try to get type hints
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        # Skip platform_context - it's injected at runtime
        if param_name == "platform_context":
            continue

        # Skip *args and **kwargs
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        # Get type from hints or default to string
        param_type = hints.get(param_name, str)
        json_type = _get_json_type(param_type)

        # Build property schema
        prop_schema: dict[str, Any] = {"type": json_type}

        # Add description from docstring if available
        # (Could parse docstring for param descriptions, but keeping it simple)
        prop_schema["description"] = f"The {param_name} parameter"

        # Handle default values
        if param.default is not inspect.Parameter.empty:
            prop_schema["default"] = param.default
        else:
            # No default = required
            required.append(param_name)

        # Handle List[X] - add items schema
        origin = get_origin(param_type)
        if origin is list:
            args = get_args(param_type)
            if args:
                item_type = _get_json_type(args[0])
                prop_schema["items"] = {"type": item_type}

        properties[param_name] = prop_schema

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


class Tool(BaseModel):
    """Container for tool metadata and configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    func: Callable
    name: str
    description: str
    input_schema: dict[str, Any]
    requires_approval: bool = False
    requires_platform_context: bool = False

    def __init__(self, **data: Any):
        """
        Initialize Tool with backwards compatibility for 'schema' field.

        V1 used `schema` containing the full tool spec:
            Tool(schema={"name": "...", "description": "...", "input_schema": {...}})

        V2 uses `input_schema` containing just the input schema:
            Tool(input_schema={"type": "object", "properties": {...}})

        This constructor accepts both for backwards compatibility.
        """
        # Handle backwards compatibility: 'schema' field -> 'input_schema'
        if "schema" in data and "input_schema" not in data:
            schema_value = data.pop("schema")

            if isinstance(schema_value, dict):
                # V1 style: schema contains full tool spec with input_schema inside
                if "input_schema" in schema_value:
                    data["input_schema"] = schema_value["input_schema"]
                    # Also extract name/description if not provided
                    if "name" not in data and "name" in schema_value:
                        data["name"] = schema_value["name"]
                    if "description" not in data and "description" in schema_value:
                        data["description"] = schema_value["description"]
                else:
                    # Schema is already the input schema (just properties, type, etc.)
                    data["input_schema"] = schema_value
            else:
                # Could be a Pydantic model or other type
                data["input_schema"] = _normalize_schema(schema_value)

        super().__init__(**data)

    def get_input_schema(self) -> dict[str, Any]:
        """Get the tool's schema (alias for input_schema)."""
        return self.input_schema

    def __repr__(self) -> str:
        """Pretty representation showing key attributes."""
        return (
            f"Tool(name='{self.name}', "
            f"requires_approval={self.requires_approval}, "
            f"requires_platform_context={self.requires_platform_context})"
        )

    def get_schema(self) -> dict[str, Any]:
        """Get the full tool specification for LLM consumption."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def describe(self) -> None:
        """Print detailed description of the tool."""
        print(f"Tool: {self.name}")
        print(f"Description: {self.description}")
        print(f"Requires Approval: {self.requires_approval}")
        print(f"Has Platform Context: {self.requires_platform_context}")
        print(f"Schema: {json.dumps(self.input_schema, indent=2)}")

    def execute(
        self, input_args: dict[str, Any], platform_context: dict[str, Any] | None = None
    ) -> str:
        """
        Execute the tool with given input and optional platform context.

        Args:
            input_args: The input parameters for the tool
            platform_context: Runtime context from the platform (only passed if tool needs it)

        Returns:
            String output from the tool
        """
        if self.requires_platform_context:
            if platform_context is None:
                raise ValueError("Platform context is required for this tool")
            return str(self.func(**input_args, platform_context=platform_context))
        else:
            return str(self.func(**input_args))


def tool(
    func: Callable | None = None,
    *,
    description: str | None = None,
    name: str | None = None,
    requires_approval: bool = True,  # V1 default: True (safe by default)
    schema: dict[str, Any] | type[BaseModel] | Any | None = None,
) -> Tool | Callable[[Callable], Tool]:
    """
    Decorator to create a tool from a function.

    Supports three usage patterns:

    1. Simple (auto-schema) - auto-generates schema from function signature:

        @tool(description="Get weather for a city")
        def get_weather(city: str, units: str = "celsius") -> str:
            '''Get current weather.'''
            return f"Weather in {city}"

    2. Dict schema - for full control over JSON Schema:

        @tool(
            description="Get weather",
            schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "enum": ["NYC", "LA"]}
                },
                "required": ["city"]
            }
        )
        def get_weather(city: str) -> str:
            return f"Weather in {city}"

    3. Pydantic model - for type-safe schema with IDE support:

        from pydantic import BaseModel, Field
        from typing import Literal

        class WeatherInput(BaseModel):
            city: Literal["NYC", "LA"] = Field(..., description="City name")
            units: str = Field(default="celsius")

        @tool(description="Get weather", schema=WeatherInput)
        def get_weather(city: str, units: str = "celsius") -> str:
            return f"Weather in {city}"

    Args:
        func: The function to wrap (auto-provided when used as @tool without parens)
        description: Description shown to the LLM. Defaults to function docstring.
        name: Tool name. Defaults to function name.
        requires_approval: If True, tool execution requires user approval.
        schema: Input schema - can be a JSON Schema dict OR a Pydantic model class.
                If not provided, auto-generated from function signature.

    Returns:
        Tool: A Tool object that wraps the function

    Examples:
        # Minimal usage
        @tool(description="Add two numbers")
        def add(a: int, b: int) -> str:
            return str(a + b)

        # With approval required
        @tool(description="Delete a file", requires_approval=True)
        def delete_file(path: str) -> str:
            os.remove(path)
            return f"Deleted {path}"

        # With platform context
        @tool(description="Get user info")
        def get_user(user_id: str, platform_context: dict) -> str:
            tenant = platform_context.get("tenant")
            return f"User {user_id} in tenant {tenant}"
    """

    def decorator(fn: Callable) -> Tool:
        # Get function metadata
        func_name = fn.__name__
        func_doc = fn.__doc__ or ""

        # Determine description
        tool_description = description
        if tool_description is None:
            # Use first line of docstring, or generate default
            tool_description = func_doc.split("\n")[0].strip() or f"Execute {func_name}"

        # Determine schema - supports dict OR Pydantic model
        if schema is None:
            # Auto-generate from function signature
            tool_schema = _generate_schema_from_function(fn)
        else:
            # Normalize: convert Pydantic model to dict if needed
            tool_schema = _normalize_schema(schema)

        # Check if function has platform_context parameter
        sig = inspect.signature(fn)
        requires_platform_context = "platform_context" in sig.parameters

        # Create the Tool
        return Tool(
            func=fn,
            name=name or func_name,
            description=tool_description,
            input_schema=tool_schema,
            requires_approval=requires_approval,
            requires_platform_context=requires_platform_context,
        )

    # Handle both @tool and @tool(...) usage
    if func is not None:
        # Called as @tool without parentheses
        return decorator(func)
    else:
        # Called as @tool(...) with arguments
        return decorator


def create_tool(
    func: Callable,
    description: str | None = None,
    name: str | None = None,
    requires_approval: bool = False,
    schema: dict[str, Any] | Any | None = None,
) -> Tool:
    """
    Create a tool programmatically without decorator.

    Args:
        func: The function to wrap as a tool
        description: Tool description (defaults to function docstring)
        name: Tool name (defaults to function name)
        requires_approval: Whether tool needs user approval
        schema: Input schema - can be a JSON Schema dict OR a Pydantic model.
                If None, auto-generated from function signature.

    Example:
        def add(x: int, y: int) -> str:
            '''Add two numbers.'''
            return str(x + y)

        my_tool = create_tool(add, description="Add numbers")

        # With explicit dict schema
        my_tool = create_tool(
            add,
            schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "minimum": 0},
                    "y": {"type": "integer", "minimum": 0}
                },
                "required": ["x", "y"]
            }
        )

        # With Pydantic model
        class AddInput(BaseModel):
            x: int = Field(..., ge=0)
            y: int = Field(..., ge=0)

        my_tool = create_tool(add, schema=AddInput)
    """
    func_name = func.__name__
    func_doc = func.__doc__ or ""

    # Determine description
    tool_description = description
    if tool_description is None:
        tool_description = func_doc.split("\n")[0].strip() or f"Execute {func_name}"

    # Determine schema - supports dict OR Pydantic model
    if schema is None:
        tool_schema = _generate_schema_from_function(func)
    else:
        # Normalize: convert Pydantic model to dict if needed
        tool_schema = _normalize_schema(schema)

    # Check if function has platform_context parameter
    sig = inspect.signature(func)
    requires_platform_context = "platform_context" in sig.parameters

    return Tool(
        func=func,
        name=name or func_name,
        description=tool_description,
        input_schema=tool_schema,
        requires_approval=requires_approval,
        requires_platform_context=requires_platform_context,
    )
