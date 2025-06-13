# rds_checker.py
from typing import List, Dict, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class RDSProductionReadinessChecker(BaseChecker):
    """Checker for RDS instance production readiness"""
    
    def check(self, tenant: str, instances: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # Fetch RDS instances if not provided
        if instances is None:
            instances = self.get_resources(tenant, "rds")
        """
        Check RDS instances for production readiness
        
        Args:
            tenant: Tenant name or ID
            instances: List of RDS instances to check
            
        Returns:
            Dictionary with check results
        """
        # Define checks for RDS instances
        rds_checks = [
            {
                'name': 'encryption',
                'attribute_path': ['EncryptStorage'],
                'condition': lambda val: (val is True, 
                                         "Storage encryption is enabled" if val is True else 
                                         "Storage encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable storage encryption for data protection"
            },
            {
                'name': 'multi_az',
                'attribute_path': ['MultiAZ'],
                'condition': lambda val: (val is True, 
                                         "Multi-AZ deployment is enabled" if val is True else 
                                         "Multi-AZ deployment is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Multi-AZ deployment for high availability"
            },
            {
                'name': 'backup_retention',
                'attribute_path': ['BackupRetentionPeriod'],
                'condition': lambda val: (val >= 0 if isinstance(val, (int, float)) else False,
                                         f"Backup retention period is {val} days" if isinstance(val, (int, float)) else
                                         "Backup retention period not set"),
                'severity': 'critical',
                'recommendation': "Set backup retention period to at least 7 days"
            },
            {
                'name': 'deletion_protection',
                'attribute_path': ['DeletionProtection'],
                'condition': lambda val: (val is True, 
                                         "Deletion protection is enabled" if val is True else 
                                         "Deletion protection is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable deletion protection to prevent accidental deletion"
            },
            {
                'name': 'logging',
                'attribute_path': ['EnableLogging'],
                'condition': lambda val: (val is True, 
                                         "Logging is enabled" if val is True else 
                                         "Logging is not enabled"),
                'severity': 'warning',
                'recommendation': "Enabling logging is crucial for observability, performance tuning, security auditing, and troubleshooting"
            },
            {
                'name': 'performance_insights',
                'attribute_path': ['EnablePerformanceInsights'],
                'condition': lambda val: (val is True, 
                                         "Performance insights is enabled" if val is True else 
                                         "Performance insights is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable performance insights for better database performance over time"
            }
        ]
        
        return self._generic_resource_check(tenant, instances, rds_checks)