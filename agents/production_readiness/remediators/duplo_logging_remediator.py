# duplo_logging_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class DuploLoggingRemediator(BaseRemediator):
    """
    Remediator for DuploCloud logging settings.
    Enables logging for a tenant.
    """
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable logging for a tenant.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - log_retention_days: Number of days to retain logs (default: 30)
            
        Returns:
            Dictionary with execution results
        """
        logger.info(f"Enabling logging for tenant {tenant}")
        
        # Get current logging configuration
        current_config = self.get_resources(tenant, "duplo_logging")
        
        # Check if logging is already enabled for this tenant
        logging_enabled = False
        if isinstance(current_config, list):
            logging_enabled = any(config.get("TenantId") == tenant for config in current_config)
        
        if logging_enabled:
            logger.info(f"Logging is already enabled for tenant {tenant}")
            return {
                "success": True,
                "message": "Logging is already enabled for this tenant",
                "details": {"tenant": tenant}
            }
        
        # Extract parameters
        log_retention_days = action_params.get("log_retention_days", 30)
        
        # Prepare payload
        payload = {
            "TenantId": tenant,
            "RetentionInDays": log_retention_days
        }
        
        # Enable logging
        try:
            self.duplo_client.post("admin/EnableLogging", payload)
            logger.info(f"Successfully enabled logging for tenant {tenant} with {log_retention_days} days retention")
            return {
                "success": True,
                "message": f"Successfully enabled logging with {log_retention_days} days retention",
                "details": {"tenant": tenant, "log_retention_days": log_retention_days}
            }
        except Exception as e:
            logger.error(f"Failed to enable logging for tenant {tenant}: {e}")
            return {
                "success": False,
                "message": f"Failed to enable logging: {str(e)}",
                "details": {"tenant": tenant, "error": str(e)}
            }