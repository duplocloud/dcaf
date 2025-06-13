# fault_notification_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class FaultNotificationRemediator(BaseRemediator):
    """
    Remediator for fault notification settings.
    Enables and configures fault notifications for a tenant.
    """
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable fault notifications for a tenant.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - notification_email: Email address for notifications
                - notification_sns: SNS topic ARN for notifications
                - enable_alerting: Whether to enable alerting
            
        Returns:
            Dictionary with execution results
        """
        logger.info(f"Enabling fault notifications for tenant {tenant}")
        
        # Get current notification configuration
        current_config = self.get_resources(tenant, "duplo_notification")
        
        # Extract parameters
        notification_email = action_params.get("notification_email")
        notification_sns = action_params.get("notification_sns")
        enable_alerting = action_params.get("enable_alerting", True)
        
        # Prepare update payload
        update_payload = {}
        
        if notification_email:
            update_payload["NotificationEmail"] = notification_email
            
        if notification_sns:
            update_payload["NotificationSNS"] = notification_sns
        
        # Update notification configuration
        if update_payload:
            try:
                self.duplo_client.post(f"subscriptions/{tenant}/UpdateTenantMonConfig", update_payload)
                logger.info(f"Updated notification configuration for tenant {tenant}")
            except Exception as e:
                logger.error(f"Failed to update notification configuration for tenant {tenant}: {e}")
                return {"success": False, "message": f"Failed to update notification configuration: {str(e)}"}
        
        # Enable alerting if requested
        if enable_alerting:
            try:
                self.duplo_client.post(f"v3/admin/tenant/{tenant}/metadata/enable_alerting", {"Value": "true"})
                logger.info(f"Enabled alerting for tenant {tenant}")
            except Exception as e:
                logger.error(f"Failed to enable alerting for tenant {tenant}: {e}")
                return {"success": False, "message": f"Failed to enable alerting: {str(e)}"}
        
        return {
            "success": True,
            "message": "Successfully configured fault notifications",
            "details": {
                "notification_email": notification_email,
                "notification_sns": notification_sns,
                "enable_alerting": enable_alerting
            }
        }