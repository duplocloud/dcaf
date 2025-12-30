"""
Diagram Styling Service

Injects custom styling into Mermaid diagrams based on customer-specific ConfigMaps.

APPROACH: Use Mermaid's %%init%% directive with themeVariables
  - Leverages Mermaid.js built-in theming system
  - Mermaid automatically distributes colors across nodes
  - No parsing, no node detection, no class assignments needed
  - Just define theme colors - Mermaid does the rest!

Reference: https://mermaid.js.org/config/theming.html
"""

import copy
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# Default styling configuration (fallback if no customer-specific config)
# Uses Mermaid's built-in theming system: https://mermaid.js.org/config/theming.html
#
# ACCESSIBILITY: Colors chosen for high contrast and color-blind friendliness
# Based on WCAG 2.1 guidelines and colorblind-safe palettes
DEFAULT_STYLING_CONFIG = {
    "theme": "base",  # Use 'base' theme for customization
    "themeVariables": {
        # Core colors - High contrast, accessible palette
        # Colors chosen to be distinguishable for colorblind users (deuteranopia, protanopia, tritanopia)
        
        "primaryColor": "#4285F4",        # Blue - clear, accessible blue
        "primaryTextColor": "#FFFFFF",    # White text for contrast
        "primaryBorderColor": "#1A56DB",  # Darker blue border

        "secondaryColor": "#FF9800",      # Orange/Amber - warm, distinct from blue
        "secondaryTextColor": "#000000",  # Black text for contrast
        "secondaryBorderColor": "#E65100", # Darker orange border

        "tertiaryColor": "#0F9D58",       # Green - accessible green (not too yellow)
        "tertiaryTextColor": "#FFFFFF",   # White text for contrast
        "tertiaryBorderColor": "#0B7A45", # Darker green border

        # Additional colors for larger diagrams
        "quaternaryColor": "#9C27B0",     # Purple - distinct from other colors
        
        # Background and text
        "background": "#FFFFFF",
        "mainBkg": "#FFFFFF",
        
        # Typography - larger for readability
        "fontFamily": "Segoe UI, Roboto, Arial, sans-serif",
        "fontSize": "14px",

        # Lines and connections - darker for visibility
        "lineColor": "#333333",
        "edgeLabelBackground": "#FFFFFF",
    }
}


# Cached contents of MERMAID_STYLE_FILE (if provided)
_STYLE_CACHE: Optional[Dict] = None
_STYLE_CACHE_MTIME: Optional[float] = None
_STYLE_CACHE_PATH: Optional[Path] = None


# Example customer-specific configs (would be loaded from ConfigMap/database)
# Using Mermaid's themeVariables: https://mermaid.js.org/config/theming.html
# All configs designed with accessibility in mind
CUSTOMER_CONFIGS = {
    # Dark theme - high contrast for dark mode UIs
    "customer-dark-theme": {
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#64B5F6",      # Light blue on dark
            "primaryTextColor": "#000000",
            "primaryBorderColor": "#1976D2",
            "secondaryColor": "#FFB74D",    # Light orange on dark
            "secondaryTextColor": "#000000",
            "secondaryBorderColor": "#F57C00",
            "tertiaryColor": "#81C784",     # Light green on dark
            "tertiaryTextColor": "#000000",
            "tertiaryBorderColor": "#388E3C",
            "background": "#1E1E1E",
            "mainBkg": "#2D2D2D",
            "fontFamily": "Segoe UI, Roboto, Arial, sans-serif",
            "fontSize": "14px",
            "lineColor": "#FFFFFF",
        }
    },
    # High contrast - maximum accessibility
    "customer-high-contrast": {
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#0066CC",      # Strong blue
            "primaryTextColor": "#FFFFFF",
            "primaryBorderColor": "#003366",
            "secondaryColor": "#CC6600",    # Strong orange
            "secondaryTextColor": "#FFFFFF",
            "secondaryBorderColor": "#663300",
            "tertiaryColor": "#006633",     # Strong green
            "tertiaryTextColor": "#FFFFFF",
            "tertiaryBorderColor": "#003319",
            "fontSize": "16px",             # Larger text
            "fontFamily": "Arial, sans-serif",
            "lineColor": "#000000",
        }
    },
    # Corporate blue - professional look
    "customer-corporate": {
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#1976D2",      # Corporate blue
            "primaryTextColor": "#FFFFFF",
            "primaryBorderColor": "#0D47A1",
            "secondaryColor": "#455A64",    # Blue-gray
            "secondaryTextColor": "#FFFFFF",
            "secondaryBorderColor": "#263238",
            "tertiaryColor": "#00897B",     # Teal
            "tertiaryTextColor": "#FFFFFF",
            "tertiaryBorderColor": "#004D40",
            "fontSize": "14px",
            "fontFamily": "Segoe UI, Roboto, Arial, sans-serif",
            "lineColor": "#37474F",
        }
    }
}


def _load_style_file() -> Optional[Dict]:
    """Load style configuration from MERMAID_STYLE_FILE if set."""
    path_str = os.getenv("MERMAID_STYLE_FILE")
    if not path_str:
        return None

    file_path = Path(path_str).expanduser()

    global _STYLE_CACHE, _STYLE_CACHE_MTIME, _STYLE_CACHE_PATH

    try:
        stat = file_path.stat()
    except FileNotFoundError:
        logger.warning("MERMAID_STYLE_FILE=%s not found; falling back to defaults", file_path)
        return None
    except OSError as exc:
        logger.warning(
            "Unable to stat MERMAID_STYLE_FILE=%s (%s); falling back to defaults",
            file_path,
            exc,
        )
        return None

    if (
        _STYLE_CACHE is not None
        and _STYLE_CACHE_PATH == file_path
        and _STYLE_CACHE_MTIME == stat.st_mtime
    ):
        return _STYLE_CACHE

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Failed to read MERMAID_STYLE_FILE=%s (%s); falling back to defaults",
            file_path,
            exc,
        )
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(
            "MERMAID_STYLE_FILE=%s is not valid JSON (%s); falling back to defaults",
            file_path,
            exc,
        )
        return None

    if not isinstance(data, dict):
        logger.error(
            "MERMAID_STYLE_FILE=%s must contain a JSON object at the top level; falling back to defaults",
            file_path,
        )
        return None

    _STYLE_CACHE = data
    _STYLE_CACHE_MTIME = stat.st_mtime
    _STYLE_CACHE_PATH = file_path
    logger.info("Loaded Mermaid style configuration from %s", file_path)
    return data


def _remove_meta_keys(config: Dict) -> Optional[Dict]:
    """Return a copy of config without control keys like 'tenants' or 'default'."""
    if not isinstance(config, dict):
        return None
    cleaned = {k: v for k, v in config.items() if k not in {"tenants", "default"}}
    return copy.deepcopy(cleaned) if cleaned else None


def _config_from_env(customer_id: Optional[str]) -> Optional[Dict]:
    """Resolve style config from MERMAID_STYLE_FILE for a given customer."""
    env_data = _load_style_file()
    if not env_data:
        return None

    tenants = env_data.get("tenants") if isinstance(env_data, dict) else None
    if isinstance(tenants, dict) and customer_id:
        tenant_cfg = tenants.get(customer_id)
        cfg = _remove_meta_keys(tenant_cfg) if isinstance(tenant_cfg, dict) else None
        if cfg:
            logger.debug("Using MERMAID_STYLE_FILE config for tenant '%s'", customer_id)
            return cfg

    default_cfg = env_data.get("default") if isinstance(env_data, dict) else None
    if isinstance(default_cfg, dict):
        cfg = _remove_meta_keys(default_cfg)
        if cfg:
            logger.debug("Using MERMAID_STYLE_FILE default config")
            return cfg

    cfg = _remove_meta_keys(env_data)
    if cfg:
        logger.debug("Using MERMAID_STYLE_FILE root config")
        return cfg

    logger.warning(
        "MERMAID_STYLE_FILE is set but no usable configuration was found for tenant '%s'",
        customer_id,
    )
    return None


def initialize_mermaid_styling() -> None:
    """
    Preload Mermaid styling configuration at application startup.

    Attempts to read MERMAID_STYLE_FILE once so that any configuration issues
    are surfaced early in logs. Falls back to defaults automatically if the
    file is missing or invalid.
    """
    try:
        data = _load_style_file()
        if data:
            logger.info(
                "Mermaid styling preloaded successfully (keys=%s)",
                ", ".join(sorted(data.keys())),
            )
        else:
            logger.info("Mermaid styling preload skipped (using default styling)")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Mermaid styling preload failed: %s", exc)


def get_customer_styling_config(customer_id: Optional[str] = None) -> Optional[Dict]:
    """
    Get styling configuration for a specific customer.

    Returns None if no MERMAID_STYLE_FILE is configured, allowing the UI
    to handle styling instead of the server.

    Args:
        customer_id: Customer/tenant identifier

    Returns:
        Styling configuration dict, or None if no server-side styling configured
    """
    env_config = _config_from_env(customer_id)
    if env_config:
        return env_config

    # Check if MERMAID_STYLE_FILE is set but config wasn't found for this tenant
    # In that case, fall back to built-in configs
    if os.getenv("MERMAID_STYLE_FILE"):
        if customer_id and customer_id in CUSTOMER_CONFIGS:
            logger.info("Using built-in styling config for customer: %s", customer_id)
            return copy.deepcopy(CUSTOMER_CONFIGS[customer_id])
        # File was set but no matching config - use default
        logger.debug("Using default styling config (MERMAID_STYLE_FILE set but no tenant match)")
        return copy.deepcopy(DEFAULT_STYLING_CONFIG)

    # No MERMAID_STYLE_FILE set - let UI handle styling
    logger.debug("No MERMAID_STYLE_FILE configured; skipping server-side styling (UI will handle)")
    return None


def _build_init_directive(config: Dict) -> str:
    """
    Build Mermaid %%init%% directive from config.

    Supports ALL mermaid.initialize() options: https://mermaid.js.org/config/theming.html

    Args:
        config: Dict with any mermaid.initialize() options:
                - theme: Theme name ("base", "dark", "forest", "neutral")
                - themeVariables: Theme customization variables
                - flowchart: Flowchart-specific settings
                - sequence: Sequence diagram settings
                - gantt: Gantt chart settings
                - etc.

    Returns:
        %%init%% directive string
    """

    if not config:
        return ""

    # Build init object - can include ANY mermaid.initialize() options
    init_obj = {}

    # Theme (required for customization)
    if "theme" in config:
        init_obj["theme"] = config["theme"]

    # Theme variables (colors, fonts, etc)
    if "themeVariables" in config and config["themeVariables"]:
        init_obj["themeVariables"] = config["themeVariables"]

    # Flowchart settings (curve, padding, spacing)
    if "flowchart" in config:
        init_obj["flowchart"] = config["flowchart"]

    # Sequence diagram settings
    if "sequence" in config:
        init_obj["sequence"] = config["sequence"]

    # Gantt settings
    if "gantt" in config:
        init_obj["gantt"] = config["gantt"]

    # Security level
    if "securityLevel" in config:
        init_obj["securityLevel"] = config["securityLevel"]

    # Any other mermaid config options
    # (pass through anything else in config)
    for key, value in config.items():
        if key not in ["theme", "themeVariables", "flowchart", "sequence", "gantt", "securityLevel"]:
            init_obj[key] = value

    if not init_obj:
        return ""

    # Convert to JSON (Mermaid expects this format)
    init_json = json.dumps(init_obj)

    return f"%%{{init: {init_json}}}%%"


def inject_diagram_styling(
    mermaid_code: str,
    customer_id: Optional[str] = None,
    enabled: bool = True
) -> str:
    """
    Inject styling into a Mermaid diagram using %%init%% directive.

    Uses Mermaid's built-in theming system: https://mermaid.js.org/config/theming.html

    This function:
    1. Loads customer-specific styling config (theme + themeVariables)
    2. Builds %%init%% directive
    3. Injects it at the start of the diagram
    4. Mermaid automatically applies colors to nodes

    Args:
        mermaid_code: Plain Mermaid diagram code from LLM
        customer_id: Customer/tenant identifier for custom styling
        enabled: Whether to inject styling (allows opt-out)

    Returns:
        Mermaid code with %%init%% directive
    """
    if not enabled or not mermaid_code.strip():
        return mermaid_code

    # Skip if diagram already has init directive
    if "%%{init:" in mermaid_code or "%%init" in mermaid_code:
        logger.debug("Diagram already has init directive, skipping injection")
        return mermaid_code

    # Get customer styling config - returns None if no server-side styling configured
    config = get_customer_styling_config(customer_id)
    if config is None:
        # No server-side styling - let UI handle it
        return mermaid_code

    # Build %%init%% directive
    init_directive = _build_init_directive(config)
    if not init_directive:
        logger.warning("No theme variables configured, skipping styling")
        return mermaid_code

    lines = mermaid_code.split('\n')

    # Find flowchart/graph declaration line
    flowchart_idx = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('flowchart') or stripped.startswith('graph'):
            flowchart_idx = idx
            break

    if flowchart_idx is None:
        logger.warning("No flowchart/graph declaration found, skipping styling")
        return mermaid_code

    # Inject %%init%% directive right before flowchart declaration
    result_lines = (
        lines[:flowchart_idx] +  # Everything before flowchart
        [init_directive] +  # %%init%% directive
        lines[flowchart_idx:]  # flowchart declaration + rest
    )

    result = '\n'.join(result_lines)

    logger.info(f"Injected %%init%% directive with theme styling (customer: {customer_id or 'default'})")

    return result


def inject_styling_in_content(
    content: str,
    customer_id: Optional[str] = None,
    enabled: bool = True
) -> str:
    """
    Find all Mermaid code blocks in content and inject styling.

    Args:
        content: Response content that may contain ```mermaid blocks
        customer_id: Customer/tenant identifier
        enabled: Whether to inject styling

    Returns:
        Content with styled Mermaid blocks
    """
    if not enabled or not content or '```mermaid' not in content:
        return content

    # Find all mermaid blocks
    pattern = r'```mermaid\s+([\s\S]*?)```'

    def replace_block(match):
        original_code = match.group(1).strip()
        styled_code = inject_diagram_styling(original_code, customer_id, enabled)
        return f"```mermaid\n{styled_code}\n```"

    result = re.sub(pattern, replace_block, content, flags=re.IGNORECASE)

    return result

