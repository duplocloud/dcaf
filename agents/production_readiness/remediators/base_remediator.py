"""
Base remediator class for the Production Readiness Agent.
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BaseRemediator(ABC):
    """
    Abstract base class for all production readiness remediators.
    """
    
    def __init__(self, duplo_client):
        """
        Initialize the remediator with a DuploClient instance.
        
        Args:
            duplo_client: An instance of DuploClient for API calls
        """
        self.duplo_client = duplo_client
    
    @abstractmethod
    def remediate(self, tenant: str, params: str) -> str:
        """
        Remediate a production readiness issue.
        
        Args:
            tenant: Tenant name or ID
            params: Parameters for the remediation action
            
        Returns:
            String with the result of the remediation action
        """
        pass
    
    def _parse_params(self, params: str) -> Dict[str, Any]:
        """
        Parse parameters from a string in the format "key1=value1:key2=value2".
        
        Args:
            params: Parameter string
            
        Returns:
            Dictionary of parsed parameters
        """
        result = {}
        
        if not params:
            return result
            
        parts = params.split(":")
        
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                
                # Convert string values to appropriate types
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value.isdigit():
                    value = int(value)
                    
                result[key.strip()] = value
            else:
                # Handle cases where there's no value, just a key
                result[part.strip()] = True
                
        return result
    
    def _get_tenant_id(self, tenant_name: str) -> Optional[str]:
        """
        Get tenant ID from tenant name.
        
        Args:
            tenant_name: Name of the tenant
            
        Returns:
            Tenant ID or None if not found
        """
        try:
            tenants = self.duplo_client.list_tenants()
            
            for t in tenants:
                if t.get("Name") == tenant_name or t.get("TenantId") == tenant_name:
                    return t.get("TenantId")
                    
            logger.warning(f"Tenant not found: {tenant_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting tenant ID: {str(e)}")
            return None
