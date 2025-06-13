# duplo_monitoring_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class DuploMonitoringRemediator(BaseRemediator):
    """
    Remediator for DuploCloud monitoring settings.
    Enables monitoring for a tenant.
    """
    
    # List of supported monitoring types
    SUPPORTED_MONITORING_TYPES = [
        'cloudwatch',
        'prometheus'
    ]
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable monitoring for a tenant.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - monitoring_type: Type of monitoring to enable (cloudwatch, prometheus)
            
        Returns:
            Dictionary with execution results
        """
        # Extract parameters
        monitoring_type = action_params.get("monitoring_type", "cloudwatch").lower()
        
        if monitoring_type not in self.SUPPORTED_MONITORING_TYPES:
            return {
                "success": False,
                "message": f"Unsupported monitoring type: {monitoring_type}. Supported types: {', '.join(self.SUPPORTED_MONITORING_TYPES)}",
                "details": {"tenant": tenant, "monitoring_type": monitoring_type}
            }
        
        logger.info(f"Enabling {monitoring_type} monitoring for tenant {tenant}")
        
        # Get current monitoring configuration
        current_config = self.get_resources(tenant, "duplo_monitoring")
        
        # Check if monitoring is already enabled for this tenant
        monitoring_enabled = False
        if isinstance(current_config, list) and len(current_config) > 0:
            monitoring_enabled = any(config.get("TenantId") == tenant for config in current_config)
        
        if monitoring_enabled:
            logger.info(f"Monitoring is already enabled for tenant {tenant}")
            return {
                "success": True,
                "message": "Monitoring is already enabled for this tenant",
                "details": {"tenant": tenant, "monitoring_type": monitoring_type}
            }
        
        # Prepare payload based on monitoring type
        payload = {"TenantId": tenant}
        
        # Enable monitoring
        try:
            if monitoring_type == "cloudwatch":
                self.duplo_client.post("admin/EnableCloudWatchAgentOnAllHosts", payload)
            elif monitoring_type == "prometheus":
                self.duplo_client.post("admin/EnablePrometheusMonitoring", payload)
            
            logger.info(f"Successfully enabled {monitoring_type} monitoring for tenant {tenant}")
            return {
                "success": True,
                "message": f"Successfully enabled {monitoring_type} monitoring",
                "details": {"tenant": tenant, "monitoring_type": monitoring_type}
            }
        except Exception as e:
            logger.error(f"Failed to enable {monitoring_type} monitoring for tenant {tenant}: {e}")
            return {
                "success": False,
                "message": f"Failed to enable monitoring: {str(e)}",
                "details": {"tenant": tenant, "monitoring_type": monitoring_type, "error": str(e)}
            }