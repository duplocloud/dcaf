"""
Tool system for creating LLM-powered agents with approval workflows.
"""
from pydantic import BaseModel, ConfigDict
from typing import Callable, Dict, Any, Optional
import inspect
import json


class Tool(BaseModel):
    """Container for tool metadata and configuration."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    func: Callable
    name: str
    description: str
    schema: Dict[str, Any]
    requires_approval: bool = False
    requires_platform_context: bool = False
    
    def __repr__(self):
        """Pretty representation showing key attributes."""
        return (
            f"Tool(name='{self.name}', "
            f"requires_approval={self.requires_approval}, "
            f"requires_platform_context={self.requires_platform_context})"
        )
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the tool's JSON schema for LLM consumption."""
        # Check if self.schema is already a full tool specification
        if isinstance(self.schema, dict) and "input_schema" in self.schema and "name" in self.schema and "description" in self.schema:
            # Schema is already a full tool spec, return it as-is
            return self.schema
        else:
            raise Exception("The schema does not have all the necessary fields: ['name', 'description', 'input_schema']")
    
    def describe(self):
        """Print detailed description of the tool."""
        print(f"Tool: {self.name}")
        print(f"Description: {self.description}")
        print(f"Requires Approval: {self.requires_approval}")
        print(f"Has Platform Context: {self.requires_platform_context}")
        print(f"Schema: {json.dumps(self.schema, indent=2)}")
    
    def execute(self, input_args: Dict[str, Any], platform_context: Dict[str, Any] = None) -> str:
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
    schema: Dict[str, Any],
    requires_approval: bool = True,
    name: Optional[str] = None,
    description: Optional[str] = None
):
    """
    Decorator to create a tool from a function.
    
    Args:
        schema: JSON schema for the tool's input parameters (Anthropic format)
                Must be a valid JSON schema with "type": "object" at root
        requires_approval: Whether tool needs user approval before execution
        name: Override the function name as tool name
        description: Override the function docstring as description
    
    The schema should follow Anthropic's tool input_schema format:
    {
        "type": "object",
        "properties": {
            "param_name": {
                "type": "string|integer|number|boolean|array|object",
                "description": "Description of the parameter",
                "enum": ["option1", "option2"],  # Optional: for enums
                "items": {...},                   # Required for arrays
                "default": value                  # Optional: default value
            }
        },
        "required": ["param1", "param2"]  # List of required parameters
    }
    
    Examples:
        # Tool without platform_context
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
        
        # Tool with platform_context
        @tool(
            schema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File to delete"}
                },
                "required": ["filename"]
            },
            requires_approval=True
        )
        def delete_file(filename: str, platform_context: dict) -> str:
            user = platform_context.get("user_id", "unknown")
            return f"User {user} deleted {filename}"
    """
    def decorator(func: Callable) -> Tool:
        # Get function metadata
        func_name = func.__name__
        func_doc = func.__doc__ or ""
        
        # Check if function has platform_context parameter
        sig = inspect.signature(func)
        requires_platform_context = 'platform_context' in sig.parameters
        
        # Create the Tool
        return Tool(
            func=func,
            name=name or func_name,
            description=description or func_doc.split('\n')[0].strip() or f"Execute {func_name}",
            schema=schema,
            requires_approval=requires_approval,
            requires_platform_context=requires_platform_context
        )
    
    return decorator


def create_tool(
    func: Callable,
    schema: Dict[str, Any],
    name: Optional[str] = None,
    description: Optional[str] = None,
    requires_approval: bool = False
) -> Tool:
    """
    Create a tool programmatically without decorator.
    
    Args:
        func: The function to wrap as a tool
        schema: JSON schema for the tool's input
        name: Tool name (defaults to function name)
        description: Tool description (defaults to function docstring)
        requires_approval: Whether tool needs user approval
    
    Example:
        # Function without platform_context
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
    
    # Check if function has platform_context parameter
    sig = inspect.signature(func)
    requires_platform_context = 'platform_context' in sig.parameters
    
    return Tool(
        func=func,
        name=name or func_name,
        description=description or func_doc.split('\n')[0].strip() or f"Execute {func_name}",
        schema=schema,
        requires_approval=requires_approval,
        requires_platform_context=requires_platform_context
    )