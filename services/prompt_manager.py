import os
import logging
import asyncio
import string
from typing import Dict, List, Optional, Any
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Manages dynamic prompts retrieved from S3 with background refresh capability.
    Supports layered prompts including system prompt, and hints.
    """
    
    def __init__(self):
        # S3 configuration
        self.s3_bucket = os.getenv("PROMPT_S3_BUCKET")
        self.agent_name = os.getenv("PROMPT_SYSTEM_NAME")
        
        # Version configurations
        self.system_prompt_version = os.getenv("PROMPT_SYSTEM_VERSION", "v1")
        
        # Parse hint files with their versions
        # Format: hint_name:version (e.g. kubernetes_troubleshooting:v2)
        self.hint_files = []
        raw_hints = os.getenv("PROMPT_HINTS", "").split(",")
        
        # Default version to use if not specified for a particular hint
        self.default_hint_version = os.getenv("PROMPT_DEFAULT_HINT_VERSION", "v1")
        
        for hint_config in raw_hints:
            hint_config = hint_config.strip()
            if not hint_config:
                continue
            
            # Parse hint name and version
            if ":" in hint_config:
                hint_name, version = hint_config.split(":", 1)
            else:
                hint_name = hint_config
                version = self.default_hint_version
            
            # Remove any existing version suffix if present in the hint name
            if "-v" in hint_name:
                hint_name = hint_name.split("-v")[0]
            
            # Create the versioned hint file name
            versioned_hint = f"{hint_name.strip()}-{version.strip()}"
            self.hint_files.append(versioned_hint)
            
        self.refresh_interval = int(os.getenv("PROMPT_REFRESH_INTERVAL_SECONDS", "300"))
        
        # Prompt layers
        self.system_prompt = ""
        self.hints = []
        
        # Default fallback prompts (will be used if S3 fetch fails)
        self._default_system_prompt = ""
        
        # S3 client
        self.s3_client = boto3.client('s3')
        
        # Background refresh task
        self.refresh_task = None
        
        logger.info(f"Initialized PromptManager with bucket: {self.s3_bucket}, agent: {self.agent_name}, "
                 f"system version: {self.system_prompt_version}, hint files: {self.hint_files}")

    def start_background_refresh(self):
        """Start the background refresh task"""
        if self.refresh_task is None:
            self.refresh_task = asyncio.create_task(self._refresh_loop())
            logger.info("Started background prompt refresh task")
    
    async def _refresh_loop(self):
        """Background task to periodically refresh prompts"""
        while True:
            try:
                await self.refresh_prompts()
                logger.info("Successfully refreshed prompts from S3")
            except Exception as e:
                logger.error(f"Failed to refresh prompts: {str(e)}")
            
            await asyncio.sleep(self.refresh_interval)
    
    async def refresh_prompts(self):
        """Refresh all prompt layers from S3"""
        # Fetch system prompt from the appropriate agent directory with version
        system_prompt = await self._fetch_from_s3(f"agents/{self.agent_name}/system_prompt-{self.system_prompt_version}.txt")
        if system_prompt:
            self.system_prompt = system_prompt
        
        # Fetch hints (including base knowledge that now uses the hints folder capability)
        new_hints = []
        for hint_file in self.hint_files:
            if hint_file.strip():
                # Hint files now include versioning in their names
                hint = await self._fetch_from_s3(f"hints/{hint_file.strip()}.txt")
                if hint:
                    new_hints.append(hint)
        
        # Only update hints if we got valid content
        if new_hints:
            self.hints = new_hints
        
        logger.info(f"Refreshed prompts: system prompt ({len(self.system_prompt)} chars), "
                   f"hints ({len(self.hints)} files)")
    
    async def _fetch_from_s3(self, key: str) -> str:
        """Fetch a file from S3"""
        try:
            response = await asyncio.to_thread(
                self.s3_client.get_object,
                Bucket=self.s3_bucket,
                Key=key
            )
            content = await asyncio.to_thread(
                lambda: response['Body'].read().decode('utf-8')
            )
            logger.info(f"Successfully fetched {key} from S3 bucket {self.s3_bucket}")
            return content
        except ClientError as e:
            logger.warning(f"Error fetching {key} from S3 bucket {self.s3_bucket}: {str(e)}")
            return ""
        except Exception as e:
            logger.warning(f"Unexpected error fetching {key} from S3 bucket {self.s3_bucket}: {str(e)}")
            return ""
    
    def set_default_prompts(self, system_prompt: str):
        """Set default prompts to use as fallbacks"""
        self._default_system_prompt = system_prompt
    
    def get_combined_prompt(self, variables: Optional[Dict[str, Any]] = None) -> str:
        """
        Combine all prompt layers and apply variable substitution
        
        Args:
            variables: Dictionary of variables to substitute in the prompts
            
        Returns:
            Combined prompt with variable substitution applied
        """
        variables = variables or {}
        
        # Use the S3 system prompt or fall back to default
        system_prompt = self.system_prompt or self._default_system_prompt
        
        # Combine the layers
        combined = system_prompt
        
        if self.hints:
            combined += "\n\n## Context Hints\n"
            for hint in self.hints:
                combined += f"{hint}\n"
        
        # Apply variable substitution using string.Template
        if variables:
            try:
                template = string.Template(combined)
                combined = template.safe_substitute(variables)
            except Exception as e:
                logger.error(f"Error applying variable substitution: {str(e)}")
        
        return combined
