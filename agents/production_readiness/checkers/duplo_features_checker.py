"""
DuploCloud features checker for the Production Readiness Agent.
"""
import logging
from typing import List, Dict, Any
from .base_checker import BaseChecker

logger = logging.getLogger(__name__)

class DuploFeaturesProductionReadinessChecker(BaseChecker):
    """
    Checker for DuploCloud features production readiness.
    """
    
    def check(self, tenant: str, resources: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check DuploCloud features for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: Dictionary containing DuploCloud features configuration
            
        Returns:
            Dictionary with check results
        """
        # Convert the dictionary to a list with a single item for the generic checker
        resource_list = [resources] if resources else []
        
        duplo_features_checks = [
            {
                'name': 'monitoring',
                'attribute_path': ['Monitoring'],
                'condition': lambda val: (val is True, 
                    "Monitoring is enabled" if val is True else 
                    "Monitoring is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable monitoring for the tenant"
            },
            {
                'name': 'logging',
                'attribute_path': ['Logging'],
                'condition': lambda val: (val is True, 
                    "Logging is enabled" if val is True else 
                    "Logging is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable logging for the tenant"
            },
            {
                'name': 'alerting',
                'attribute_path': ['Alerting'],
                'condition': lambda val: (val is True, 
                    "Alerting is enabled" if val is True else 
                    "Alerting is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable alerting for the tenant"
            },
            {
                'name': 'notification_channels',
                'attribute_path': ['NotificationChannels'],
                'condition': lambda val: (val is not None and len(val) > 0, 
                    "Notification channels are configured" if val is not None and len(val) > 0 else 
                    "Notification channels are not configured"),
                'severity': 'warning',
                'recommendation': "Configure notification channels for alerts"
            }
        ]

        return self._generic_resource_check(tenant, resource_list, duplo_features_checks)
