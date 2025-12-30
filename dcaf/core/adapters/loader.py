"""
Adapter Loader - Dynamic discovery and loading of framework adapters.

This module provides convention-based discovery of LLM framework adapters.
New frameworks can be added by simply creating a new module following
the naming convention - no registration or manifest required.

Convention:
    1. Adapter location: dcaf/core/adapters/outbound/{framework}/
    2. Required export: create_adapter(**kwargs) function in __init__.py
    3. The adapter must implement RuntimeAdapter protocol

Usage:
    from dcaf.core.adapters.loader import load_adapter, list_frameworks
    
    # Load a specific framework
    adapter = load_adapter("agno", model_id="claude-3...", provider="bedrock")
    
    # List available frameworks
    frameworks = list_frameworks()  # ["agno", "strands", ...]
"""

import importlib
import logging
import os
from pathlib import Path
from typing import Any, List

from .runtime_protocol import RuntimeAdapter

logger = logging.getLogger(__name__)

# Base package for outbound adapters
ADAPTERS_PACKAGE = "dcaf.core.adapters.outbound"


def load_adapter(framework: str, **kwargs) -> RuntimeAdapter:
    """
    Dynamically load an adapter by framework name.
    
    This function uses convention-based discovery:
    - Looks for module: dcaf.core.adapters.outbound.{framework}
    - Calls: module.create_adapter(**kwargs)
    
    Args:
        framework: Name of the framework (e.g., "agno", "strands", "langchain")
        **kwargs: Arguments passed to the adapter constructor:
                 - model_id: Model identifier
                 - provider: Provider name (for multi-provider frameworks)
                 - aws_profile: AWS profile name
                 - aws_region: AWS region
                 - api_key: API key for direct providers
                 - ... (framework-specific options)
    
    Returns:
        An adapter instance implementing RuntimeAdapter
        
    Raises:
        ValueError: If framework not found or missing create_adapter()
        
    Example:
        adapter = load_adapter(
            "agno",
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            provider="bedrock",
            aws_profile="production",
        )
    """
    framework = framework.lower().strip()
    module_path = f"{ADAPTERS_PACKAGE}.{framework}"
    
    logger.debug(f"Loading adapter for framework: {framework}")
    
    # Try to import the module
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        available = list_frameworks()
        if available:
            available_str = ", ".join(available)
            raise ValueError(
                f"Unknown framework: '{framework}'. "
                f"Available frameworks: {available_str}"
            ) from e
        else:
            raise ValueError(
                f"Unknown framework: '{framework}'. "
                f"No frameworks found in {ADAPTERS_PACKAGE}"
            ) from e
    
    # Check for create_adapter function
    if not hasattr(module, "create_adapter"):
        raise ValueError(
            f"Framework '{framework}' is missing the required create_adapter() function. "
            f"Each adapter module must export: def create_adapter(**kwargs) -> Adapter"
        )
    
    # Call the factory function
    factory = getattr(module, "create_adapter")
    
    try:
        adapter = factory(**kwargs)
    except TypeError as e:
        raise ValueError(
            f"Failed to create adapter for '{framework}': {e}. "
            f"Check that the kwargs match the adapter's constructor."
        ) from e
    
    # Verify it implements the protocol (runtime check)
    if not isinstance(adapter, RuntimeAdapter):
        logger.warning(
            f"Adapter '{framework}' does not fully implement RuntimeAdapter protocol. "
            f"It may be missing some required methods."
        )
    
    logger.info(f"Loaded adapter: {framework} -> {type(adapter).__name__}")
    
    return adapter


def list_frameworks() -> List[str]:
    """
    List all available framework adapters.
    
    Scans the outbound adapters directory for valid framework modules.
    A valid framework module must have a create_adapter() function.
    
    Returns:
        List of framework names (e.g., ["agno", "strands", "langchain"])
        
    Example:
        >>> list_frameworks()
        ['agno', 'strands']
    """
    frameworks = []
    
    # Get the path to the outbound adapters directory
    try:
        outbound_module = importlib.import_module(ADAPTERS_PACKAGE)
        if hasattr(outbound_module, "__path__"):
            adapters_path = Path(outbound_module.__path__[0])
        else:
            return frameworks
    except ModuleNotFoundError:
        return frameworks
    
    # Scan for subdirectories that look like framework modules
    if adapters_path.exists():
        for item in adapters_path.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                # Check if it has __init__.py with create_adapter
                init_file = item / "__init__.py"
                if init_file.exists():
                    # Quick check: try to import and verify create_adapter exists
                    try:
                        module = importlib.import_module(
                            f"{ADAPTERS_PACKAGE}.{item.name}"
                        )
                        if hasattr(module, "create_adapter"):
                            frameworks.append(item.name)
                    except Exception:
                        # Skip modules that fail to import
                        pass
    
    return sorted(frameworks)


def get_framework_info(framework: str) -> dict:
    """
    Get information about a specific framework adapter.
    
    Args:
        framework: Name of the framework
        
    Returns:
        Dict with framework info:
        - name: Framework name
        - module: Full module path
        - docstring: Module docstring
        - available: Whether it's properly configured
        
    Example:
        >>> get_framework_info("agno")
        {
            'name': 'agno',
            'module': 'dcaf.core.adapters.outbound.agno',
            'docstring': 'Agno SDK adapter...',
            'available': True
        }
    """
    framework = framework.lower().strip()
    module_path = f"{ADAPTERS_PACKAGE}.{framework}"
    
    info = {
        "name": framework,
        "module": module_path,
        "docstring": None,
        "available": False,
    }
    
    try:
        module = importlib.import_module(module_path)
        info["docstring"] = module.__doc__
        info["available"] = hasattr(module, "create_adapter")
    except ModuleNotFoundError:
        pass
    
    return info
