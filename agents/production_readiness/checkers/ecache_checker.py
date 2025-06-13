# ecache_checker.py
from typing import List, Dict, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class ElastiCacheProductionReadinessChecker(BaseChecker):
    """Checker for ElastiCache cluster production readiness"""
    
    def check(self, tenant: str, clusters: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        # Fetch ElastiCache clusters if not provided
        if clusters is None:
            clusters = self.get_resources(tenant, "ecache")
        """
        Check ElastiCache clusters for production readiness
        
        Args:
            tenant: Tenant name or ID
            clusters: List of ElastiCache clusters to check
            
        Returns:
            Dictionary with check results
        """
        # Define checks for ElastiCache clusters
        ecache_checks = [
            {
                'name': 'encryption_at_rest',
                'attribute_path': ['EnableEncryptionAtRest'],
                'condition': lambda val: (val is True, 
                                         "Encryption at rest is enabled" if val is True else 
                                         "Encryption at rest is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable encryption at rest for data protection"
            },
            {
                'name': 'encryption_at_transit',
                'attribute_path': ['EnableEncryptionAtTransit'],
                'condition': lambda val: (val is True, 
                                         "Encryption at transit is enabled" if val is True else 
                                         "Encryption at transit is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable encryption at transit for data protection"
            },
            {
                'name': 'multi_az',
                'attribute_path': ['MultiAZEnabled'],
                'condition': lambda val: (val is True, 
                                         "Multi-AZ deployment is enabled" if val is True else 
                                         "Multi-AZ deployment is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable Multi-AZ deployment for high availability"
            },
            {
                'name': 'automatic_failover',
                'attribute_path': ['AutomaticFailoverEnabled'],
                'condition': lambda val: (val is True, 
                                         "Automatic failover is enabled" if val is True else 
                                         "Automatic failover is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable automatic failover for high availability"
            }
        ]
        
        return self._generic_resource_check(tenant, clusters, ecache_checks)