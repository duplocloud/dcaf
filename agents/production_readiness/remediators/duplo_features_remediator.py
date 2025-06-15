"""
DuploCloud features remediator for the Production Readiness Agent.
"""
import logging
from typing import Dict, Any
from .base_remediator import BaseRemediator

logger = logging.getLogger(__name__)

class DuploFeaturesRemediator(BaseRemediator):
    """
    Remediator for DuploCloud features production readiness issues.
    """
    
    def remediate(self, tenant: str, params: str) -> str:
        """
        Remediate DuploCloud features production readiness issues.
        
        Args:
            tenant: Tenant name or ID
            params: Parameters for the remediation action
            
        Returns:
            String with the result of the remediation action
        """
        # Get tenant ID
        tenant_id = self._get_tenant_id(tenant)
        if not tenant_id:
            return f"Tenant not found: {tenant}"
            
        # For simple enable actions, the params might just be "true"
        if params.lower() == "true":
            return self._enable_feature(tenant_id, "all")
            
        # Otherwise, parse the parameters
        settings = self._parse_params(params)
        
        # Handle notification channel configuration
        if any(channel in settings for channel in ["pagerduty", "sentry", "newrelic", "opsgenie"]):
            return self._configure_notification_channel(tenant_id, settings)
            
        # Handle specific feature enablement
        feature = next(iter(settings.keys()), None)
        if feature:
            return self._enable_feature(tenant_id, feature)
            
        return f"Invalid parameters: {params}"
    
    def _enable_feature(self, tenant_id: str, feature: str) -> str:
        """
        Enable a DuploCloud feature for a tenant.
        
        Args:
            tenant_id: Tenant ID
            feature: Feature to enable (monitoring, logging, alerting, or all)
            
        Returns:
            String with the result of the action
        """
        try:
            if feature == "monitoring" or feature == "all":
                self.duplo_client.post(f"v3/subscriptions/{tenant_id}/monitoring", {"Enable": True})
                
            if feature == "logging" or feature == "all":
                self.duplo_client.post(f"v3/subscriptions/{tenant_id}/logging", {"Enable": True})
                
            if feature == "alerting" or feature == "all":
                self.duplo_client.post(f"v3/subscriptions/{tenant_id}/alerting", {"Enable": True})
                
            return f"Successfully enabled DuploCloud feature(s): {feature}"
            
        except Exception as e:
            logger.error(f"Error enabling DuploCloud feature: {str(e)}")
            return f"Failed to enable DuploCloud feature: {str(e)}"
    
    def _configure_notification_channel(self, tenant_id: str, settings: Dict[str, Any]) -> str:
        """
        Configure a notification channel for a tenant.
        
        Args:
            tenant_id: Tenant ID
            settings: Dictionary with channel type and endpoint
            
        Returns:
            String with the result of the action
        """
        try:
            # Determine channel type and endpoint
            channel_type = None
            endpoint = None
            
            for channel in ["pagerduty", "sentry", "newrelic", "opsgenie"]:
                if channel in settings:
                    channel_type = channel
                    endpoint = settings[channel]
                    break
                    
            if not channel_type or not endpoint:
                return "Invalid notification channel configuration"
                
            # Map channel type to API value
            channel_map = {
                "pagerduty": "PagerDuty",
                "sentry": "Sentry",
                "newrelic": "NewRelic",
                "opsgenie": "OpsGenie"
            }
            
            api_channel = channel_map.get(channel_type)
            if not api_channel:
                return f"Unsupported notification channel: {channel_type}"
                
            # Prepare payload
            payload = {
                "Type": api_channel,
                "Endpoint": endpoint
            }
            
            # Call API to configure notification channel
            self.duplo_client.post(f"v3/subscriptions/{tenant_id}/faultnotification", payload)
            
            return f"Successfully configured {channel_type} notification channel"
            
        except Exception as e:
            logger.error(f"Error configuring notification channel: {str(e)}")
            return f"Failed to configure notification channel: {str(e)}"
