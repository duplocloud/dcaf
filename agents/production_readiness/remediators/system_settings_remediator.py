"""
DuploCloud system settings remediator for the Production Readiness Agent.
"""
import logging
from typing import Dict, Any
from .base_remediator import BaseRemediator

logger = logging.getLogger(__name__)

class SystemSettingsRemediator(BaseRemediator):
    """
    Remediator for DuploCloud system settings production readiness issues.
    """
    
    def remediate(self, tenant: str, params: str) -> str:
        """
        Remediate DuploCloud system settings production readiness issues.
        
        Args:
            tenant: Tenant name or ID
            params: Parameters in the format "setting_name=value"
            
        Returns:
            String with the result of the remediation action
        """
        # Parse settings
        settings = self._parse_params(params)
        if not settings:
            return f"Invalid parameters: {params}. Format should be 'setting_name=value'"
            
        # Validate settings
        valid_settings = ["user_token_expiration", "token_expiration_notification_email"]
        
        for setting in settings:
            if setting not in valid_settings:
                return f"Invalid setting: {setting}. Valid settings are: {', '.join(valid_settings)}"
                
        try:
            # Map setting names to API field names
            setting_map = {
                "user_token_expiration": "UserTokenExpirationDays",
                "token_expiration_notification_email": "TokenExpirationNotificationEmail"
            }
            
            # Prepare payload
            payload = {}
            for setting, value in settings.items():
                api_field = setting_map.get(setting)
                if api_field:
                    payload[api_field] = value
                    
            # Call API to update system settings
            self.duplo_client.post("v3/admin/systemSettings/config", payload)
            
            # Format the applied settings for the response
            settings_applied = []
            for setting, value in settings.items():
                settings_applied.append(f"{setting}={value}")
                
            return f"Successfully updated DuploCloud system settings: {', '.join(settings_applied)}"
            
        except Exception as e:
            logger.error(f"Error updating DuploCloud system settings: {str(e)}")
            return f"Failed to update DuploCloud system settings: {str(e)}"
