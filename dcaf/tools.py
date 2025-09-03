"""
Tool system for creating LLM-powered agents with approval workflows.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Callable, Dict, Any, Optional
import json


class Tool(BaseModel):
    """Container for tool metadata and configuration."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    func: Callable
    name: str
    description: str
    schema: Dict[str, Any]
    requires_approval: bool = False
    
    def __repr__(self):
        """Pretty representation showing key attributes."""
        return (
            f"Tool(name='{self.name}', "
            f"requires_approval={self.requires_approval})"
        )
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the tool's JSON schema for LLM consumption."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema
        }
    
    def describe(self):
        """Print detailed description of the tool."""
        print(f"Tool: {self.name}")
        print(f"Description: {self.description}")
        print(f"Requires Approval: {self.requires_approval}")
        print(f"Schema: {json.dumps(self.schema, indent=2)}")
    
    def execute(self, input_data: Dict[str, Any], platform_context: Dict[str, Any]) -> str:
        """
        Execute the tool with given input and platform context.
        
        Args:
            input_data: The input parameters for the tool
            platform_context: Runtime context from the platform
            
        Returns:
            String output from the tool
        """
        # Add platform_context to the input
        return str(self.func(**input_data, platform_context=platform_context))


def tool(
    schema: Dict[str, Any],
    requires_approval: bool = False,
    name: Optional[str] = None,
    description: Optional[str] = None
):
    """
    Decorator to create a tool from a function.
    
    Args:
        schema: JSON schema for the tool's input parameters
        requires_approval: Whether tool needs user approval before execution
        name: Override the function name as tool name
        description: Override the function docstring as description
    
    Example:
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
            return f"Deleted {tenant_name}"
    """
    def decorator(func: Callable) -> Tool:
        # Get function metadata
        func_name = func.__name__
        func_doc = func.__doc__ or ""
        
        # Create the Tool
        return Tool(
            func=func,
            name=name or func_name,
            description=description or func_doc.split('\n')[0].strip() or f"Execute {func_name}",
            schema=schema,
            requires_approval=requires_approval
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
        my_tool = create_tool(
            func=delete_tenant_func,
            schema={"type": "object", "properties": {...}},
            requires_approval=True
        )
    """
    func_name = func.__name__
    func_doc = func.__doc__ or ""
    
    return Tool(
        func=func,
        name=name or func_name,
        description=description or func_doc.split('\n')[0].strip() or f"Execute {func_name}",
        schema=schema,
        requires_approval=requires_approval
    )