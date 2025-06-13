# integration.py
import logging
from typing import Dict, List, Any, Optional

from services.llm import BedrockAnthropicLLM
from services.duplo_client import DuploClient
from schemas.messages import AgentMessage, Data, Command, ExecutedCommand

from .agent import ProductionReadinessAgent
from .system_prompt import SystemPromptHandler

logger = logging.getLogger(__name__)

class ProductionReadinessAgentBridge:
    """
    Bridge class that connects the modular ProductionReadinessAgent implementation
    with the original agent interface expected by the agent_server.
    """
    
    def __init__(self, llm: BedrockAnthropicLLM, system_prompt: Optional[str] = None):
        """
        Initialize the ProductionReadinessAgentBridge.
        
        Args:
            llm: An instance of BedrockAnthropicLLM for generating responses
            system_prompt: Optional custom system prompt to override the default
        """
        self.llm = llm
        self.system_prompt_handler = SystemPromptHandler()
        self.system_prompt = system_prompt
        self.agent = None  # Will be initialized when needed with the DuploClient
        
    def _initialize_agent(self, duplo_client: DuploClient) -> ProductionReadinessAgent:
        """
        Initialize the modular ProductionReadinessAgent with a DuploClient.
        
        Args:
            duplo_client: DuploClient instance for API interactions
            
        Returns:
            Initialized ProductionReadinessAgent
        """
        if not self.agent or self.agent.duplo_client != duplo_client:
            self.agent = ProductionReadinessAgent(duplo_client)
        return self.agent
    
    def check_production_readiness(self, tenant: str, duplo_client: DuploClient) -> Dict[str, Any]:
        """
        Check production readiness for a tenant using the modular agent.
        
        Args:
            tenant: Tenant name or ID
            duplo_client: DuploClient instance
            
        Returns:
            Dictionary with production readiness check results
        """
        agent = self._initialize_agent(duplo_client)
        return agent.check_production_readiness(tenant)
    
    def execute_remediation(self, tenant: str, action: str, duplo_client: DuploClient, approved: bool = False) -> Dict[str, Any]:
        """
        Execute a remediation action using the modular agent.
        
        Args:
            tenant: Tenant name or ID
            action: Remediation action string
            duplo_client: DuploClient instance
            approved: Whether the action has been approved
            
        Returns:
            Dictionary with remediation execution results
        """
        agent = self._initialize_agent(duplo_client)
        return agent.execute_remediation(tenant, action, approved)
    
    def extract_remediation_actions(self, llm_response: str) -> List[str]:
        """
        Extract remediation actions from an LLM response using the modular agent.
        
        Args:
            llm_response: LLM response text
            
        Returns:
            List of remediation action strings
        """
        # This doesn't require an initialized agent
        if not self.agent:
            # Create a temporary agent with None as duplo_client just for extraction
            temp_agent = ProductionReadinessAgent(None)
            return temp_agent.extract_remediation_actions(llm_response)
        return self.agent.extract_remediation_actions(llm_response)
    
    def generate_system_prompt(self, tenant: str) -> str:
        """
        Generate a system prompt for the specified tenant.
        
        Args:
            tenant: Tenant name or ID
            
        Returns:
            System prompt string
        """
        # If a custom system prompt was provided during initialization, use that
        if self.system_prompt:
            return self.system_prompt
            
        # Otherwise, use the SystemPromptHandler to generate the system prompt
        # The SystemPromptHandler now uses the exact same system prompt as in production_readiness_agent.py
        return self.system_prompt_handler.generate_system_prompt(tenant)
