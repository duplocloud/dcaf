"""Tool converter for Agno framework."""

from typing import Dict, Any, List, Callable, Optional

from .types import AgnoToolDefinition


class AgnoToolConverter:
    """
    Converts dcaf Tool objects to Agno tool format.
    
    The Agno SDK expects tools in a specific format with:
    - name: Tool identifier
    - description: What the tool does
    - input_schema: JSON Schema for parameters
    
    This converter handles the translation from our Tool class
    to the Agno-expected format.
    
    Example:
        converter = AgnoToolConverter()
        
        dcaf_tool = Tool(
            func=kubectl_func,
            name="kubectl",
            description="Execute kubectl commands",
            schema={...},
            requires_approval=True,
        )
        
        agno_tool = converter.to_agno(dcaf_tool)
    """
    
    def to_agno(self, tool) -> AgnoToolDefinition:
        """
        Convert a dcaf Tool to Agno format.
        
        Args:
            tool: A dcaf Tool object
            
        Returns:
            AgnoToolDefinition dictionary
        """
        # Get the tool schema
        schema = tool.get_schema() if hasattr(tool, 'get_schema') else tool.schema
        
        # Build the Agno tool definition
        agno_tool: AgnoToolDefinition = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": self._extract_input_schema(schema),
        }
        
        return agno_tool
    
    def to_agno_list(self, tools: List) -> List[AgnoToolDefinition]:
        """
        Convert a list of dcaf Tools to Agno format.
        
        Args:
            tools: List of dcaf Tool objects
            
        Returns:
            List of AgnoToolDefinition dictionaries
        """
        return [self.to_agno(tool) for tool in tools]
    
    def to_agno_function(self, tool) -> Dict[str, Any]:
        """
        Convert a dcaf Tool to an Agno-compatible function wrapper.
        
        This creates a callable that can be registered with Agno
        while preserving our approval logic.
        
        Args:
            tool: A dcaf Tool object
            
        Returns:
            Dictionary with function and metadata
        """
        def wrapped_function(**kwargs) -> str:
            """Wrapper that executes the tool."""
            # Note: Actual execution happens in the use case layer
            # This is just for Agno's function registration
            return tool.execute(kwargs)
        
        return {
            "function": wrapped_function,
            "name": tool.name,
            "description": tool.description,
            "parameters": self._extract_input_schema(tool.schema),
        }
    
    def _extract_input_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract the input schema from a tool schema.
        
        The dcaf Tool schema may be in different formats:
        1. Full tool spec with input_schema key
        2. Just the JSON schema directly
        
        Args:
            schema: The tool schema
            
        Returns:
            JSON Schema for tool parameters
        """
        # If schema has input_schema key, extract it
        if isinstance(schema, dict) and "input_schema" in schema:
            return schema["input_schema"]
        
        # Otherwise, assume it's already the input schema
        return schema
    
    def create_tool_definition(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
    ) -> AgnoToolDefinition:
        """
        Create an Agno tool definition from components.
        
        Useful for creating tools programmatically without
        going through the dcaf Tool class.
        
        Args:
            name: Tool name
            description: Tool description
            parameters: JSON Schema for parameters
            
        Returns:
            AgnoToolDefinition dictionary
        """
        return {
            "name": name,
            "description": description,
            "input_schema": parameters,
        }


def create_agno_tools(tools: List) -> List[AgnoToolDefinition]:
    """
    Convenience function to convert tools to Agno format.
    
    Args:
        tools: List of dcaf Tool objects
        
    Returns:
        List of Agno tool definitions
    """
    converter = AgnoToolConverter()
    return converter.to_agno_list(tools)
