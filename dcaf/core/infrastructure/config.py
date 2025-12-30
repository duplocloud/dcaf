"""Configuration management for DCAF Core."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import os


@dataclass
class CoreConfig:
    """
    Configuration for the DCAF Core framework.
    
    This class holds all configuration options for the core abstraction layer.
    Values can be provided directly or loaded from environment variables.
    
    Attributes:
        model_id: The default LLM model ID
        provider: The default LLM provider
        max_tokens: Default maximum tokens in responses
        temperature: Default sampling temperature
        high_risk_tools: List of tool names that always require approval
        enable_streaming: Whether streaming is enabled by default
        log_level: Logging level
        
    Example:
        # Create with defaults
        config = CoreConfig()
        
        # Create with custom values
        config = CoreConfig(
            model_id="anthropic.claude-3-opus",
            max_tokens=8192,
        )
        
        # Load from environment
        config = CoreConfig.from_env()
    """
    
    # LLM Configuration
    model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    provider: str = "bedrock"
    max_tokens: int = 4096
    temperature: float = 0.7
    
    # Approval Configuration
    high_risk_tools: List[str] = field(default_factory=list)
    always_require_approval: bool = False
    
    # Runtime Configuration
    enable_streaming: bool = True
    conversation_ttl_seconds: int = 3600  # 1 hour
    
    # Logging Configuration
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Additional configuration
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_env(cls, prefix: str = "DCAF_") -> "CoreConfig":
        """
        Load configuration from environment variables.
        
        Environment variables are prefixed with DCAF_ by default.
        
        Args:
            prefix: Prefix for environment variables
            
            Returns:
            CoreConfig instance with values from environment
            
        Example:
            # Set environment variables
            export DCAF_MODEL_ID=anthropic.claude-3-opus
            export DCAF_MAX_TOKENS=8192
            
            # Load config
            config = V2Config.from_env()
        """
        def get_env(key: str, default: Any = None) -> Optional[str]:
            return os.environ.get(f"{prefix}{key}", default)
        
        def get_bool(key: str, default: bool = False) -> bool:
            value = get_env(key)
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes")
        
        def get_int(key: str, default: int = 0) -> int:
            value = get_env(key)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default
        
        def get_float(key: str, default: float = 0.0) -> float:
            value = get_env(key)
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                return default
        
        def get_list(key: str, default: List[str] = None) -> List[str]:
            value = get_env(key)
            if value is None:
                return default or []
            return [item.strip() for item in value.split(",") if item.strip()]
        
        return cls(
            model_id=get_env("MODEL_ID", cls.model_id),
            provider=get_env("PROVIDER", cls.provider),
            max_tokens=get_int("MAX_TOKENS", cls.max_tokens),
            temperature=get_float("TEMPERATURE", cls.temperature),
            high_risk_tools=get_list("HIGH_RISK_TOOLS", []),
            always_require_approval=get_bool("ALWAYS_REQUIRE_APPROVAL", False),
            enable_streaming=get_bool("ENABLE_STREAMING", True),
            conversation_ttl_seconds=get_int("CONVERSATION_TTL", 3600),
            log_level=get_env("LOG_LEVEL", "INFO"),
        )
    
    def with_overrides(self, **kwargs: Any) -> "CoreConfig":
        """
        Create a new config with overrides.
        
        Args:
            **kwargs: Values to override
            
        Returns:
            New CoreConfig with overrides applied
        """
        return CoreConfig(
            model_id=kwargs.get("model_id", self.model_id),
            provider=kwargs.get("provider", self.provider),
            max_tokens=kwargs.get("max_tokens", self.max_tokens),
            temperature=kwargs.get("temperature", self.temperature),
            high_risk_tools=kwargs.get("high_risk_tools", self.high_risk_tools),
            always_require_approval=kwargs.get("always_require_approval", self.always_require_approval),
            enable_streaming=kwargs.get("enable_streaming", self.enable_streaming),
            conversation_ttl_seconds=kwargs.get("conversation_ttl_seconds", self.conversation_ttl_seconds),
            log_level=kwargs.get("log_level", self.log_level),
            log_format=kwargs.get("log_format", self.log_format),
            extra={**self.extra, **kwargs.get("extra", {})},
        )
