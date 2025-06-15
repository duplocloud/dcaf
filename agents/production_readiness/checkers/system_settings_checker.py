"""
DuploCloud system settings checker for the Production Readiness Agent.
"""
import logging
from typing import List, Dict, Any
from .base_checker import BaseChecker

logger = logging.getLogger(__name__)

class SystemSettingsProductionReadinessChecker(BaseChecker):
    """
    Checker for DuploCloud system settings production readiness.
    """
    
    def check(self, tenant: str, resources: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check DuploCloud system settings for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: Dictionary containing system settings configuration
            
        Returns:
            Dictionary with check results
        """
        # Convert the dictionary to a list with a single item for the generic checker
        resource_list = [resources] if resources else []
        
        system_settings_checks = [
            {
                'name': 'user_token_expiration',
                'attribute_path': ['UserTokenExpirationDays'],
                'condition': lambda val: (val is not None and val <= 90, 
                    f"User token expiration is set to {val} days" if val is not None else 
                    "User token expiration is not set"),
                'severity': 'warning',
                'recommendation': "Set user token expiration to 90 days or less"
            },
            {
                'name': 'token_expiration_notification_email',
                'attribute_path': ['TokenExpirationNotificationEmail'],
                'condition': lambda val: (val is not None and len(val) > 0, 
                    "Token expiration notification email is configured" if val is not None and len(val) > 0 else 
                    "Token expiration notification email is not configured"),
                'severity': 'warning',
                'recommendation': "Configure token expiration notification email"
            }
        ]

        return self._generic_resource_check(tenant, resource_list, system_settings_checks)
