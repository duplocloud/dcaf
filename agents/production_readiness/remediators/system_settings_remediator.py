# system_settings_remediator.py
from typing import Dict, List, Any, Optional
from .base_remediator import BaseRemediator
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class SystemSettingsRemediator(BaseRemediator):
    """
    Remediator for DuploCloud system settings.
    Updates system settings like token expiration and notification emails.
    """
    
    # List of supported system settings
    SUPPORTED_SETTINGS = [
        'user_token_expiration',
        'token_expiration_notification_email'
    ]
    
    def execute(self, tenant: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a DuploCloud system setting.
        
        Args:
            tenant: Tenant name or ID
            action_params: Parameters for the remediation action
                - setting_name: Name of the setting to update
                - value: Value to set for the setting
            
        Returns:
            Dictionary with execution results
        """
        # Extract parameters
        setting_name = action_params.get("setting_name")
        value = action_params.get("value")
        
        if not setting_name:
            return {
                "success": False,
                "message": "Setting name is required",
                "details": {"tenant": tenant}
            }
        
        if value is None:
            return {
                "success": False,
                "message": "Setting value is required",
                "details": {"tenant": tenant, "setting_name": setting_name}
            }
        
        if setting_name not in self.SUPPORTED_SETTINGS:
            return {
                "success": False,
                "message": f"Unsupported setting: {setting_name}. Supported settings: {', '.join(self.SUPPORTED_SETTINGS)}",
                "details": {"tenant": tenant, "setting_name": setting_name}
            }
        
        logger.info(f"Updating system setting {setting_name} to {value}")
        
        # Get current system settings
        system_settings = self.get_resources(tenant, "system_settings")
        
        # Map setting name to API field name
        setting_mapping = {
            'user_token_expiration': 'UserTokenExpirationInDays',
            'token_expiration_notification_email': 'TokenExpirationNotificationEmail'
        }
        
        api_field = setting_mapping.get(setting_name)
        if not api_field:
            return {
                "success": False,
                "message": f"API field mapping not found for setting: {setting_name}",
                "details": {"tenant": tenant, "setting_name": setting_name}
            }
        
        # Check if the setting is already set to the desired value
        current_value = system_settings.get(api_field)
        if current_value == value:
            return {
                "success": True,
                "message": f"System setting {setting_name} is already set to {value}",
                "details": {"tenant": tenant, "setting_name": setting_name, "value": value}
            }
        
        # Prepare update payload
        update_payload = {api_field: value}
        
        # Update the system setting
        try:
            self.duplo_client.post("v3/admin/systemSettings/config", update_payload)
            logger.info(f"Successfully updated system setting {setting_name} to {value}")
            
            return {
                "success": True,
                "message": f"Successfully updated system setting {setting_name} to {value}",
                "details": {"tenant": tenant, "setting_name": setting_name, "value": value}
            }
        except Exception as e:
            logger.error(f"Failed to update system setting {setting_name}: {e}")
            return {
                "success": False,
                "message": f"Failed to update system setting: {str(e)}",
                "details": {"tenant": tenant, "setting_name": setting_name, "error": str(e)}
            }