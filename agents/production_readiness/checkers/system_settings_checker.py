# system_settings_checker.py
from typing import Dict, List, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class SystemSettingsProductionReadinessChecker(BaseChecker):
    """
    Checker for DuploCloud system settings production readiness.
    Verifies that system settings are properly configured for security and operational stability.
    """
    
    def check(self, tenant: str, resources: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Check production readiness for DuploCloud system settings.
        
        Args:
            tenant: Tenant name or ID
            resources: Optional system settings resources. If not provided, will be fetched.
            
        Returns:
            List of check results for system settings
        """
        logger.info(f"Checking system settings production readiness for tenant {tenant}")
        
        # Get system settings if not provided
        if resources is None:
            resources = self.get_resources(tenant, "system_settings")
        
        # Create a synthetic resource to represent system settings
        system_resource = {
            'identifier': f"system-settings",
            'Name': f"system-settings"
        }
        
        # Extract system settings
        token_expiration_notification_enabled = False
        token_expiration_notification_days = 0
        token_expiration_notification_emails = ""
        
        if "system_settings" in resources and resources["system_settings"] and isinstance(resources["system_settings"], list):
            for setting in resources["system_settings"]:
                if setting.get("Type") == "AppConfig" and setting.get("Key") == "EnableUserTokenExpirationNotification":
                    try:
                        days = int(setting.get("Value", "0"))
                        if days > 0:
                            token_expiration_notification_enabled = True
                            token_expiration_notification_days = days
                    except (ValueError, TypeError):
                        pass
                
                if setting.get("Type") == "AppConfig" and setting.get("Key") == "UserTokenExpirationNotificationEmails":
                    token_expiration_notification_emails = setting.get("Value", "")
        
        # Add settings to resource
        system_resource["TokenExpirationNotificationEnabled"] = token_expiration_notification_enabled
        system_resource["TokenExpirationNotificationDays"] = token_expiration_notification_days
        system_resource["TokenExpirationNotificationEmails"] = token_expiration_notification_emails
        system_resource["HasTokenExpirationEmails"] = bool(token_expiration_notification_emails)
        
        # Define checks for system settings
        system_checks = [
            {
                'name': 'token_expiration_notification',
                'attribute_path': ['TokenExpirationNotificationEnabled'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"User token expiration notification is enabled ({resource.get('TokenExpirationNotificationDays', 0)} days)" if val is True 
                    else "User token expiration notification is not enabled"
                ),
                'severity': 'warning',
                'recommendation': "Enable user token expiration notification to alert users before their tokens expire"
            },
            {
                'name': 'token_expiration_emails',
                'attribute_path': ['HasTokenExpirationEmails'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"Token expiration notification emails are configured" if val is True 
                    else "Token expiration notification emails are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure token expiration notification emails to ensure notifications are delivered"
            }
        ]

        return self._generic_resource_check(tenant, [system_resource], system_checks)
        