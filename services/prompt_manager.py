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
    Supports layered prompts including system prompt, base knowledge, and hints.
    """
    
    def __init__(self):
        # S3 configuration
        self.s3_bucket = os.getenv("PROMPT_S3_BUCKET")
        self.agent_name = os.getenv("PROMPT_AGENT_NAME")
        self.hint_files = os.getenv("PROMPT_HINT_FILES", "").split(",")
        self.refresh_interval = int(os.getenv("PROMPT_REFRESH_INTERVAL_SECONDS", "300"))
        
        # Prompt layers
        self.system_prompt = ""
        self.base_knowledge = ""
        self.hints = []
        
        # Default fallback prompts (will be used if S3 fetch fails)
        self._default_system_prompt = ""
        self._default_base_knowledge = ""
        
        # S3 client
        self.s3_client = boto3.client('s3')
        
        # Background refresh task
        self.refresh_task = None
        
        logger.info(f"Initialized PromptManager with bucket: {self.s3_bucket} and agent: {self.agent_name}")

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
        # Fetch system prompt from the appropriate agent directory
        system_prompt = await self._fetch_from_s3(f"agents/{self.agent_name}/system_prompt.txt")
        if system_prompt:
            self.system_prompt = system_prompt
        
        # Fetch base knowledge (now in base_duplo_knowedge subdirectory)
        base_knowledge = await self._fetch_from_s3(f"base_duplo_knowedge/base_knowledge.txt")
        if base_knowledge:
            self.base_knowledge = base_knowledge
        
        # Fetch hints (same path structure)
        new_hints = []
        for hint_file in self.hint_files:
            if hint_file.strip():
                hint = await self._fetch_from_s3(f"hints/{hint_file.strip()}")
                if hint:
                    new_hints.append(hint)
        
        # Only update hints if we got valid content
        if new_hints:
            self.hints = new_hints
        
        logger.info(f"Refreshed prompts: system prompt ({len(self.system_prompt)} chars), "
                   f"base knowledge ({len(self.base_knowledge)} chars), "
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
    
    def set_default_prompts(self, system_prompt: str, base_knowledge: str = ""):
        """Set default prompts to use as fallbacks"""
        self._default_system_prompt = system_prompt
        self._default_base_knowledge = base_knowledge
    
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
        base_knowledge = self.base_knowledge or self._default_base_knowledge
        
        # Combine the layers
        combined = system_prompt
        
        if base_knowledge:
            combined += f"\n\n## DuploCloud Base Knowledge\n{base_knowledge}"
        
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
