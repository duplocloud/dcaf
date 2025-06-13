# base_remediator.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from services.duplo_client import DuploClient
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class BaseRemediator(ABC):
    """
    Base class for all remediators.
    Remediators are responsible for executing remediation actions for production readiness issues.
    """
    
    def __init__(self, duplo_client: DuploClient, resource_provider: Optional[ResourceProvider] = None):
        """
        Initialize the remediator with a DuploClient instance.
        
        Args:
            duplo_client: DuploClient instance for API calls
            resource_provider: Optional ResourceProvider instance
        """
        self.duplo_client = duplo_client
        self.resource_provider = resource_provider or ResourceProvider(duplo_client)
    
    def get_resources(self, tenant: str, resource_type: str) -> List[Dict[str, Any]]:
        """
        Get resources of a specific type for a tenant.
        
        Args:
            tenant: Tenant name or ID
            resource_type: Type of resource to fetch
            
        Returns:
            List of resources of the specified type
        """
        return self.resource_provider.get_resource_by_type(tenant, resource_type)
    
    @abstractmethod
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a remediation action.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
            
        Returns:
            Dictionary with execution results
        """
        pass