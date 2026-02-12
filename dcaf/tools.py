"""
Tool system for creating LLM-powered agents with approval workflows.
"""

import inspect
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict


def _normalize_schema(
    schema: Any,
    tool_name: str,
    tool_description: str,
) -> dict[str, Any]:
    """
    Normalize a schema to a full Anthropic tool spec dict.

    Accepts:
    - Pydantic model class: converted via model_json_schema() and wrapped
    - Raw JSON schema dict (type/properties/required): wrapped with name/description
    - Full Anthropic tool spec (name/description/input_schema): passed through as-is

    Args:
        schema: A dict or Pydantic BaseModel class
        tool_name: The tool name to use when wrapping
        tool_description: The tool description to use when wrapping

    Returns:
        Full Anthropic tool spec dict with name, description, and input_schema

    Raises:
        TypeError: If schema is not a supported type
    """
    # Pydantic model class
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return {
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema.model_json_schema(),
        }

    # Already a dict
    if isinstance(schema, dict):
        # Full Anthropic tool spec — pass through
        if "input_schema" in schema and "name" in schema and "description" in schema:
            return schema
        # Raw JSON schema dict — wrap it
        return {
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
        }

    raise TypeError(
        f"schema must be a dict or Pydantic BaseModel class, got {type(schema).__name__}. "
        f"Examples:\n"
        f"  @tool(schema={{'type': 'object', ...}})\n"
        f"  @tool(schema=MyPydanticModel)"
    )


class Tool(BaseModel):
    """Container for tool metadata and configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    func: Callable
    name: str
    description: str
    schema: dict[str, Any]  # type: ignore[assignment]  # Intentionally shadows BaseModel.schema
    requires_approval: bool = False
    requires_platform_context: bool = False

    def __repr__(self):
        """Pretty representation showing key attributes."""
        return (
            f"Tool(name='{self.name}', "
            f"requires_approval={self.requires_approval}, "
            f"requires_platform_context={self.requires_platform_context})"
        )

    def get_schema(self) -> dict[str, Any]:
        """Get the full tool specification for LLM consumption."""
        # Schema is already a full tool spec (has input_schema key)
        if isinstance(self.schema, dict) and "input_schema" in self.schema:
            return {
                "name": self.schema.get("name", self.name),
                "description": self.schema.get("description", self.description),
                "input_schema": self.schema["input_schema"],
            }
        # Schema is a raw JSON schema dict — wrap it
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }

    def describe(self):
        """Print detailed description of the tool."""
        print(f"Tool: {self.name}")
        print(f"Description: {self.description}")
        print(f"Requires Approval: {self.requires_approval}")
        print(f"Has Platform Context: {self.requires_platform_context}")
        print(f"Schema: {json.dumps(self.schema, indent=2)}")

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
            # Tool expects platform_context
            if platform_context is None:
                raise ValueError("Platform context is required for this tool")
            return str(self.func(**input_args, platform_context=platform_context))
        else:
            # Tool doesn't need platform_context
            return str(self.func(**input_args))


def tool(
    schema: dict[str, Any] | type[BaseModel],
    requires_approval: bool = True,
    name: str | None = None,
    description: str | None = None,
):
    """
    Decorator to create a tool from a function.

    Args:
        schema: Tool input schema. Accepts three formats:
                - Pydantic BaseModel class (converted via model_json_schema())
                - Raw JSON schema dict (type/properties/required)
                - Full Anthropic tool spec dict (name/description/input_schema)
        requires_approval: Whether tool needs user approval before execution
        name: Override the function name as tool name
        description: Override the function docstring as description

    Examples:
        # With a Pydantic model
        from pydantic import BaseModel, Field

        class WeatherInput(BaseModel):
            city: str = Field(..., description="City name")

        @tool(schema=WeatherInput)
        def get_weather(city: str) -> str:
            '''Get weather for a city.'''
            return f"Weather in {city}: Sunny"

        # With a raw JSON schema dict
        @tool(
            schema={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        )
        def get_weather(location: str) -> str:
            return f"Weather in {location}: Sunny"

        # With a full Anthropic tool spec
        @tool(
            schema={
                "name": "get_weather",
                "description": "Get weather",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"}
                    },
                    "required": ["location"]
                }
            }
        )
        def get_weather(location: str) -> str:
            return f"Weather in {location}: Sunny"
    """

    def decorator(func: Callable) -> Tool:
        # Get function metadata
        func_name = func.__name__
        func_doc = func.__doc__ or ""

        tool_name = name or func_name
        tool_description = description or func_doc.split("\n")[0].strip() or f"Execute {func_name}"

        # Normalize schema to full Anthropic tool spec
        resolved_schema = _normalize_schema(schema, tool_name, tool_description)

        # Check if function has platform_context parameter
        sig = inspect.signature(func)
        requires_platform_context = "platform_context" in sig.parameters

        # Create the Tool
        return Tool(
            func=func,
            name=tool_name,
            description=tool_description,
            schema=resolved_schema,
            requires_approval=requires_approval,
            requires_platform_context=requires_platform_context,
        )

    return decorator


def create_tool(
    func: Callable,
    schema: dict[str, Any] | type[BaseModel],
    name: str | None = None,
    description: str | None = None,
    requires_approval: bool = False,
) -> Tool:
    """
    Create a tool programmatically without decorator.

    Args:
        func: The function to wrap as a tool
        schema: Tool input schema. Accepts Pydantic BaseModel class, raw JSON
                schema dict, or full Anthropic tool spec dict.
        name: Tool name (defaults to function name)
        description: Tool description (defaults to function docstring)
        requires_approval: Whether tool needs user approval

    Example:
        def add(x: int, y: int) -> str:
            return f"Sum: {x + y}"

        my_tool = create_tool(
            func=add,
            schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"}
                },
                "required": ["x", "y"]
            }
        )
    """
    func_name = func.__name__
    func_doc = func.__doc__ or ""

    tool_name = name or func_name
    tool_description = description or func_doc.split("\n")[0].strip() or f"Execute {func_name}"

    # Normalize schema to full Anthropic tool spec
    resolved_schema = _normalize_schema(schema, tool_name, tool_description)

    # Check if function has platform_context parameter
    sig = inspect.signature(func)
    requires_platform_context = "platform_context" in sig.parameters

    return Tool(
        func=func,
        name=tool_name,
        description=tool_description,
        schema=resolved_schema,
        requires_approval=requires_approval,
        requires_platform_context=requires_platform_context,
    )
