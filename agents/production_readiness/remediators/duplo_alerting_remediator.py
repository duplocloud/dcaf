# duplo_alerting_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class DuploAlertingRemediator(BaseRemediator):
    """
    Remediator for DuploCloud alerting settings.
    Configures alerting channels for a tenant.
    """
    
    # List of supported alerting channels
    SUPPORTED_CHANNELS = [
        'pagerduty',
        'sentry',
        'newrelic',
        'opsgenie'
    ]
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Configure alerting for a tenant.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - channel_type: Type of alerting channel (pagerduty, sentry, newrelic, opsgenie)
                - endpoint: Endpoint URL or API key for the alerting channel
                - alert_frequency: Optional frequency for alert publishing in minutes (default: 5)
            
        Returns:
            Dictionary with execution results
        """
        # Extract parameters
        channel_type = action_params.get("channel_type", "").lower()
        endpoint = action_params.get("endpoint", "")
        alert_frequency = action_params.get("alert_frequency", 5)
        
        if not channel_type:
            return {
                "success": False,
                "message": "Channel type is required",
                "details": {"tenant": tenant}
            }
        
        if not endpoint:
            return {
                "success": False,
                "message": "Endpoint is required",
                "details": {"tenant": tenant, "channel_type": channel_type}
            }
        
        if channel_type not in self.SUPPORTED_CHANNELS:
            return {
                "success": False,
                "message": f"Unsupported channel type: {channel_type}. Supported types: {', '.join(self.SUPPORTED_CHANNELS)}",
                "details": {"tenant": tenant, "channel_type": channel_type}
            }
        
        logger.info(f"Configuring {channel_type} alerting for tenant {tenant}")
        
        # Get current alerting configuration
        current_config = self.get_resources(tenant, "duplo_alerting")
        
        # Check if this channel is already configured
        channel_configured = False
        if isinstance(current_config, dict):
            # Map channel types to their configuration keys
            channel_keys = {
                'pagerduty': 'PagerDutyIntegrationKey',
                'sentry': 'SentryDsn',
                'newrelic': 'NewRelicApiKey',
                'opsgenie': 'OpsGenieApiKey'
            }
            
            key = channel_keys.get(channel_type)
            if key and key in current_config and current_config[key]:
                channel_configured = True
        
        if channel_configured:
            logger.info(f"{channel_type.capitalize()} alerting is already configured for tenant {tenant}")
            return {
                "success": True,
                "message": f"{channel_type.capitalize()} alerting is already configured for this tenant",
                "details": {"tenant": tenant, "channel_type": channel_type}
            }
        
        # Prepare payload based on channel type
        payload = {
            "TenantId": tenant,
            "AlertPublishFrequencyInMinutes": alert_frequency
        }
        
        # Set the appropriate field based on channel type
        if channel_type == "pagerduty":
            payload["PagerDutyIntegrationKey"] = endpoint
        elif channel_type == "sentry":
            payload["SentryDsn"] = endpoint
        elif channel_type == "newrelic":
            payload["NewRelicApiKey"] = endpoint
        elif channel_type == "opsgenie":
            payload["OpsGenieApiKey"] = endpoint
        
        # Configure alerting
        try:
            self.duplo_client.post("v2/admin/UpdateTenantMonConfig", payload)
            logger.info(f"Successfully configured {channel_type} alerting for tenant {tenant}")
            
            # Mask the endpoint for security in logs and response
            masked_endpoint = "*" * (len(endpoint) - 4) + endpoint[-4:] if len(endpoint) > 4 else "****"
            
            return {
                "success": True,
                "message": f"Successfully configured {channel_type} alerting",
                "details": {
                    "tenant": tenant, 
                    "channel_type": channel_type, 
                    "endpoint": masked_endpoint,
                    "alert_frequency": alert_frequency
                }
            }
        except Exception as e:
            logger.error(f"Failed to configure {channel_type} alerting for tenant {tenant}: {e}")
            return {
                "success": False,
                "message": f"Failed to configure alerting: {str(e)}",
                "details": {"tenant": tenant, "channel_type": channel_type, "error": str(e)}
            }