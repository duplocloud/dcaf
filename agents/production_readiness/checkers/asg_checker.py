# asg_checker.py
from typing import Dict, List, Any, Optional
from .base_checker import BaseChecker
from ..resource_provider import ResourceProvider
import logging

logger = logging.getLogger(__name__)

class ASGProductionReadinessChecker(BaseChecker):
    """
    Checker for AWS Auto Scaling Group production readiness.
    Verifies that ASGs are properly configured for high availability and resilience.
    """
    
    def check(self, tenant: str, resources: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Check production readiness for AWS Auto Scaling Groups.
        
        Args:
            tenant: Tenant name or ID
            resources: Optional list of ASG resources. If not provided, will be fetched.
            
        Returns:
            Dictionary with check results for each ASG
        """
        logger.info(f"Checking ASG production readiness for tenant {tenant}")
        
        # Get ASG resources if not provided
        if resources is None:
            resources = self.get_resources(tenant, "asg")
        
        if not resources:
            logger.info(f"No ASGs found for tenant {tenant}")
            return {}
        
        # Define checks for ASGs
        asg_checks = [
                {
                'name': 'is_cluster_autoscaled',
                'attribute_path': ['IsClusterAutoscaled'],
                'condition': lambda val: (val is True, 
                                         "Cluster autoscaling is enabled" if val is True else 
                                         "Cluster autoscaling is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable cluster autoscaling for high availability"
                },
                {
                    'name': 'multiple_azs',
                    'attribute_path': ['Zones'],
                    'condition': lambda zones: (
                        isinstance(zones, list) and len(zones) >= 2,
                        f"ASG spans {len(zones)} availability zones" if isinstance(zones, list) and len(zones) >= 2 else
                        "ASG availability zones not determined"
                    ),
                    'severity': 'critical',
                    'recommendation': "Configure ASG to span at least 2 availability zones"
                }
            ]
        
        return self._generic_resource_check(tenant, resources, asg_checks)