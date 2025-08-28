"""
Bedrock LLM implementation using AWS Bedrock Converse API.
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html

Provides a unified interface for all Bedrock-supported models.
"""

import boto3
import time
import logging
import os
from typing import Dict, Any, Optional, List, Union
from botocore.config import Config
from botocore.exceptions import ClientError
from dcaf.llm.base import LLM

logger = logging.getLogger(__name__)

class BedrockLLM(LLM):
    """
    A class for interacting with AWS Bedrock LLMs using the Converse API.
    Provides consistent interface across all Bedrock models.
    """
    
    def __init__(self, region_name: str = 'us-east-1'):
        """
        Initialize the BedrockLLM client.
        
        Args:
            region_name: AWS region name (default: 'us-east-1')
        """
        app_env = os.getenv("APP_ENV", "duplo")
        logger.info(f"Initializing Bedrock client for APP_ENV: {app_env}")

        config = Config(
            read_timeout=1000
        )

        self.bedrock_runtime = boto3.client(
            'bedrock-runtime', 
            region_name=region_name, 
            config=config
        )
    
    def invoke(
        self,
        messages: List[Dict[str, Any]],
        model_id: str,
        max_tokens: int = 1000,
        temperature: float = 0.0,
        top_p: float = 0.9,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        additional_model_request_fields: Optional[Dict[str, Any]] = None,
        performance_config: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Invoke an AWS Bedrock LLM using the Converse API.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            model_id: The Bedrock model ID (e.g., 'anthropic.claude-3-5-sonnet-20240620-v1:0')
            max_tokens: Maximum number of tokens to generate
            temperature: Controls randomness (0-1)
            top_p: Controls diversity via nucleus sampling (0-1)
            system_prompt: Optional system prompt to guide model behavior
            tools: Optional list of tool specifications (JSON schemas)
            tool_choice: Optional tool choice strategy ('auto', 'any', or specific tool dict)
            additional_model_request_fields: Model-specific parameters
            performance_config: Performance configuration (e.g., {'latency': 'optimized'})
            **kwargs: Additional parameters for compatibility
            
        Returns:
            The raw response from the Converse API
        """
        
        logger.info(f"Invoking model {model_id} with Converse API")
        logger.debug(f"Messages: {messages}")
        
        # Normalize messages to ensure proper role alternation
        messages = self.normalize_message_roles(messages)
        
        # Build the request
        request = {
            'modelId': model_id,
            'messages': self._format_messages(messages)
        }
        
        # Add system prompt if provided
        if system_prompt:
            request['system'] = [{'text': system_prompt}]
        
        # Add inference configuration
        inference_config = {
            'maxTokens': max_tokens,
            'temperature': temperature,
            'topP': top_p
        }
        request['inferenceConfig'] = inference_config
        
        # Add tool configuration if provided
        if tools:
            tool_config = self._format_tool_config(tools, tool_choice)
            request['toolConfig'] = tool_config
        
        # Add additional model-specific fields if provided
        if additional_model_request_fields:
            request['additionalModelRequestFields'] = additional_model_request_fields
        
        # Add performance configuration if provided
        if performance_config:
            # Note: performanceConfig is passed differently in SDK vs direct API
            # This may need adjustment based on boto3 version
            if 'latency' in performance_config:
                request['performanceConfig'] = {'latency': performance_config['latency']}
        
        start_time = time.perf_counter()
        
        try:
            # Invoke the model using Converse API
            response = self.bedrock_runtime.converse(**request)
            
            elapsed = time.perf_counter() - start_time
            logger.info(f"Model {model_id} call completed in {elapsed:.2f} seconds")
            logger.debug(f"Response: {response}")
            
            return response
            
        except ClientError as e:
            logger.error(f"Error invoking model: {e}")
            raise
    
    def normalize_message_roles(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize message roles by merging consecutive messages with the same role.
        
        Bedrock Converse API requires strict role alternation between 'user' and 'assistant'.
        This method merges adjacent messages with the same role.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Normalized list of messages with proper role alternation
        """
        if not messages:
            return messages
        
        # Remove empty messages
        messages = [msg for msg in messages if msg.get("content", "").strip()]
        
        if len(messages) <= 1:
            return messages.copy()
        
        # Merge adjacent messages with the same role
        merged = []
        i = 0
        while i < len(messages):
            current = messages[i].copy()
            merged.append(current)
            
            # Look ahead for consecutive messages with the same role
            j = i + 1
            while j < len(messages) and messages[j].get("role") == current.get("role"):
                # Merge content from the next message into the current one
                self._merge_message_content(current, messages[j])
                j += 1
            
            # Skip all messages that were merged
            i = j
        
        # Recursively normalize if any merges were performed
        if len(merged) < len(messages):
            return self.normalize_message_roles(merged)
        else:
            return merged
    
    def _merge_message_content(self, target_msg: Dict[str, Any], source_msg: Dict[str, Any]) -> None:
        """
        Helper method to merge content from source message into target message.
        
        Args:
            target_msg: Message to merge content into
            source_msg: Message to merge content from
        """
        prev_content = target_msg.get("content", "")
        curr_content = source_msg.get("content", "")
        
        # Handle different content formats
        if isinstance(prev_content, list) and isinstance(curr_content, list):
            target_msg["content"] = prev_content + curr_content
        elif isinstance(prev_content, list):
            if isinstance(curr_content, str):
                target_msg["content"] = prev_content + [{"text": curr_content}]
            else:
                target_msg["content"] = prev_content + [curr_content]
        elif isinstance(curr_content, list):
            if isinstance(prev_content, str):
                target_msg["content"] = [{"text": prev_content}] + curr_content
            else:
                target_msg["content"] = [prev_content] + curr_content
        else:  # both strings
            target_msg["content"] = f"{prev_content}\n{curr_content}"
    
    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format messages for Converse API.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Formatted messages for Converse API
        """
        formatted = []
        for msg in messages:
            formatted_msg = {
                'role': msg['role']
            }
            
            content = msg.get('content', '')
            
            # Handle different content formats
            if isinstance(content, str):
                formatted_msg['content'] = [{'text': content}]
            elif isinstance(content, list):
                # Content is already formatted as list
                formatted_content = []
                for item in content:
                    if isinstance(item, str):
                        formatted_content.append({'text': item})
                    elif isinstance(item, dict):
                        # Already formatted content block
                        formatted_content.append(item)
                formatted_msg['content'] = formatted_content
            elif isinstance(content, dict):
                # Single content block
                formatted_msg['content'] = [content]
            
            formatted.append(formatted_msg)
        
        return formatted
    
    def _format_tool_config(
        self, 
        tools: List[Dict[str, Any]], 
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Format tool configuration for Converse API.
        
        Args:
            tools: List of tool specifications (JSON schemas)
            tool_choice: Tool choice strategy
            
        Returns:
            Formatted tool configuration
        """
        tool_config = {'tools': []}
        
        for tool in tools:
            # Format each tool specification
            tool_spec = {
                'toolSpec': {
                    'name': tool['name'],
                    'description': tool.get('description', ''),
                    'inputSchema': {
                        'json': tool.get('input_schema', tool.get('parameters', {}))
                    }
                }
            }
            tool_config['tools'].append(tool_spec)
        
        # Add tool choice if specified
        if tool_choice:
            if isinstance(tool_choice, str):
                if tool_choice == 'auto':
                    # Default behavior, can be omitted or explicitly set
                    tool_config['toolChoice'] = {'auto': {}}
                elif tool_choice == 'any':
                    # Model must use at least one tool
                    tool_config['toolChoice'] = {'any': {}}
            elif isinstance(tool_choice, dict):
                # Specific tool choice (for Anthropic models)
                if 'name' in tool_choice:
                    tool_config['toolChoice'] = {
                        'tool': {
                            'name': tool_choice['name']
                        }
                    }
        
        return tool_config