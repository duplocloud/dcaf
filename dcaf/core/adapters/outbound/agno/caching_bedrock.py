"""
AWS Bedrock model with prompt caching support.

TEMPORARY IMPLEMENTATION: This module extends Agno's AwsBedrock class to add 
cache checkpoints to system prompts. This is a workaround until Agno adds 
native prompt caching support (expected in future release).

Once Agno supports caching natively, this module should be removed.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

from agno.models.aws import AwsBedrock
from agno.models.message import Message

logger = logging.getLogger(__name__)


class CachingAwsBedrock(AwsBedrock):
    """
    AWS Bedrock model with prompt caching support.
    
    This class extends AwsBedrock to add cache checkpoints to the system
    prompt, enabling Bedrock's prompt caching feature for reduced latency
    and cost.
    
    TEMPORARY: Remove once Agno adds native caching support.
    
    Attributes:
        cache_system_prompt: Whether to add cache checkpoint to system prompt
        static_system: Static portion of system prompt (cached)
        dynamic_system: Dynamic portion of system prompt (not cached)
        
    Example:
        model = CachingAwsBedrock(
            id="anthropic.claude-3-7-sonnet-20250219-v1:0",
            cache_system_prompt=True,
            static_system="You are a helpful assistant...",
            dynamic_system="Tenant: acme-corp",
        )
    """
    
    # Minimum tokens required for caching (varies by model)
    # Claude 3.7 Sonnet: 1024, Claude 3.5 Haiku: 2048
    MIN_CACHE_TOKENS = 1024
    
    def __init__(
        self,
        cache_system_prompt: bool = False,
        static_system: Optional[str] = None,
        dynamic_system: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the caching Bedrock model.
        
        Args:
            cache_system_prompt: Whether to add cache checkpoint to system prompt
            static_system: Static portion (cached)
            dynamic_system: Dynamic portion (not cached)
            **kwargs: Passed to parent AwsBedrock class
        """
        super().__init__(**kwargs)
        self._cache_system_prompt = cache_system_prompt
        self._static_system = static_system
        self._dynamic_system = dynamic_system
        
        if cache_system_prompt:
            logger.info(
                f"CachingAwsBedrock: Prompt caching enabled for model {self.id}"
            )
    
    def _format_messages(
        self, 
        messages: List[Message], 
        compress_tool_results: bool = False
    ) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """
        Format messages for the request, adding cache checkpoints.
        
        This overrides the parent method to add a cachePoint to the
        system message when caching is enabled.
        
        Note: This override may be fragile if Agno updates their implementation.
        Last verified compatible with: agno==0.6.x
        
        Args:
            messages: List of messages to format
            compress_tool_results: Whether to compress tool results
            
        Returns:
            Tuple of (formatted_messages, system_message_with_cache)
        """
        # Get the base formatted messages from parent
        formatted_messages, system_message = super()._format_messages(
            messages, compress_tool_results
        )
        
        # If we have static/dynamic parts, build custom system message
        if self._static_system or self._dynamic_system:
            system_message = self._build_cached_system_message()
        elif self._cache_system_prompt and system_message:
            # Just add checkpoint to existing system message
            system_message = self._add_cache_checkpoint(system_message)
        
        return formatted_messages, system_message
    
    def _build_cached_system_message(self) -> Optional[List[Dict[str, Any]]]:
        """
        Build system message with cache checkpoint between static and dynamic parts.
        
        Structure:
        [
            {"text": "static content..."},
            {"cachePoint": {"type": "default"}},  # ← Cache everything above
            {"text": "dynamic content..."}
        ]
        
        Returns:
            System message content blocks, or None if no content
        """
        parts = []
        
        # Add static part
        if self._static_system:
            # Check if it meets minimum token threshold
            if self._cache_system_prompt and not self._check_token_threshold(self._static_system):
                logger.warning(
                    "Static system prompt below minimum token threshold for caching. "
                    "Caching disabled for this request."
                )
                # Disable caching for this request, just concatenate
                combined = "\n\n".join([p for p in [self._static_system, self._dynamic_system] if p])
                return [{"text": combined}] if combined else None
            
            parts.append({"text": self._static_system})
        
        # Add cache checkpoint (only if we have static content to cache)
        if self._static_system and self._cache_system_prompt:
            parts.append({"cachePoint": {"type": "default"}})
            logger.debug(
                f"Added cache checkpoint after static system prompt "
                f"(~{len(self._static_system)//4} tokens)"
            )
        
        # Add dynamic part
        if self._dynamic_system:
            parts.append({"text": self._dynamic_system})
            logger.debug(
                f"Added dynamic system context "
                f"(~{len(self._dynamic_system)//4} tokens)"
            )
        
        return parts if parts else None
    
    def _add_cache_checkpoint(
        self, 
        system_message: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add a cache checkpoint to the system message.
        
        The checkpoint is added after the text content, marking everything
        before it as cacheable.
        
        Args:
            system_message: The system message content blocks
            
        Returns:
            System message with cache checkpoint appended
            
        Example:
            Input:  [{"text": "You are a helpful assistant..."}]
            Output: [{"text": "You are a helpful assistant..."}, 
                     {"cachePoint": {"type": "default"}}]
        """
        # Create a copy to avoid mutating the original
        cached_system = list(system_message)
        
        # Add the cache checkpoint at the end
        cached_system.append({
            "cachePoint": {
                "type": "default"
            }
        })
        
        logger.debug(
            f"Added cache checkpoint to system message "
            f"({len(system_message)} content blocks)"
        )
        
        return cached_system
    
    def _check_token_threshold(self, text: str) -> bool:
        """
        Check if text meets minimum caching threshold.
        
        Args:
            text: The text to check
            
        Returns:
            True if text is long enough to cache, False otherwise
        """
        # Rough estimate: 4 chars ≈ 1 token
        estimated_tokens = len(text) // 4
        
        if estimated_tokens < self.MIN_CACHE_TOKENS:
            logger.warning(
                f"System prompt (~{estimated_tokens} tokens) below minimum "
                f"threshold ({self.MIN_CACHE_TOKENS} tokens). "
                f"Consider longer instructions or disable caching."
            )
            return False
        
        logger.info(
            f"System prompt (~{estimated_tokens} tokens) meets caching threshold"
        )
        return True
    
    def _log_cache_metrics(self, response: Dict[str, Any]) -> None:
        """
        Log cache performance metrics from Bedrock response.
        
        Bedrock returns cache metrics in the response under 'usage':
        - cacheReadInputTokens: Tokens retrieved from cache (cache HIT)
        - cacheCreationInputTokens: Tokens cached for first time (cache MISS)
        
        Args:
            response: The Bedrock API response
        """
        usage = response.get("usage", {})
        cache_hit = usage.get("cacheReadInputTokens", 0)
        cache_miss = usage.get("cacheCreationInputTokens", 0)
        
        if cache_hit > 0:
            logger.info(
                f"✅ Cache HIT: {cache_hit} tokens reused "
                f"(~{cache_hit * 0.9:.0f}% cost reduction)"
            )
        elif cache_miss > 0:
            logger.info(
                f"📝 Cache MISS: {cache_miss} tokens cached for next request "
                f"(cache created)"
            )
        elif self._cache_system_prompt:
            logger.warning(
                "⚠️ Caching enabled but no cache metrics in response. "
                "Possible reasons: system prompt too short, caching not supported "
                "by this model, or Bedrock API change."
            )


# Note: We intentionally don't export a create_caching_model() factory
# to keep the public API simple. Adapter handles instantiation.

