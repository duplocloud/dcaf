"""
RDS database checker for the Production Readiness Agent.
"""
import logging
from typing import List, Dict, Any
from .base_checker import BaseChecker

logger = logging.getLogger(__name__)

class RDSProductionReadinessChecker(BaseChecker):
    """
    Checker for RDS database production readiness.
    """
    
    def check(self, tenant: str, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check RDS instances for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: List of RDS instance resources to check
            
        Returns:
            Dictionary with check results
        """
        rds_checks = [
            {
                'name': 'multi_az',
                'attribute_path': ['MultiAZ'],
                'condition': lambda val: (val is True, 
                    "Multi-AZ is enabled" if val is True else 
                    "Multi-AZ is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Multi-AZ for high availability"
            },
            {
                'name': 'backup_retention',
                'attribute_path': ['BackupRetentionPeriod'],
                'condition': lambda val: (val >= 7 if val is not None else False, 
                    f"Backup retention period is {val} days" if val is not None else 
                    "Backup retention period is not set"),
                'severity': 'critical',
                'recommendation': "Set backup retention period to at least 7 days"
            },
            {
                'name': 'encryption',
                'attribute_path': ['StorageEncrypted'],
                'condition': lambda val: (val is True, 
                    "Storage encryption is enabled" if val is True else 
                    "Storage encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable storage encryption"
            },
            {
                'name': 'deletion_protection',
                'attribute_path': ['DeletionProtection'],
                'condition': lambda val: (val is True, 
                    "Deletion protection is enabled" if val is True else 
                    "Deletion protection is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable deletion protection"
            },
            {
                'name': 'monitoring',
                'attribute_path': ['EnhancedMonitoringResourceArn'],
                'condition': lambda val: (val is not None, 
                    "Enhanced monitoring is enabled" if val is not None else 
                    "Enhanced monitoring is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable enhanced monitoring"
            }
        ]

        return self._generic_resource_check(tenant, resources, rds_checks)
