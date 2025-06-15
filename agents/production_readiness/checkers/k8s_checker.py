"""
Kubernetes/DuploCloud service checker for the Production Readiness Agent.
"""
import logging
from typing import List, Dict, Any
from .base_checker import BaseChecker

logger = logging.getLogger(__name__)

class K8sProductionReadinessChecker(BaseChecker):
    """
    Checker for Kubernetes/DuploCloud service production readiness.
    """
    
    def check(self, tenant: str, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check Kubernetes/DuploCloud services for production readiness.
        
        Args:
            tenant: Tenant name or ID
            resources: List of service resources to check
            
        Returns:
            Dictionary with check results
        """
        # Filter out system services
        filtered_services = self._filter_resources(
            resources, 
            exclude_prefixes=["system-", "kube-", "kubernetes-", "duplo-"]
        )
        
        k8s_checks = [
            {
                'name': 'replicas',
                'attribute_path': ['ReplicaCount'],
                'condition': lambda val: (val >= 2 if val is not None else False, 
                    f"Replica count is {val}" if val is not None else 
                    "Replica count is not set"),
                'severity': 'critical',
                'recommendation': "Set replica count to at least 2 for high availability"
            },
            {
                'name': 'resource_limits',
                'attribute_path': ['Containers', 0, 'ResourceLimits'],
                'condition': lambda val: (val is not None and len(val) > 0, 
                    "Resource limits are set" if val is not None and len(val) > 0 else 
                    "Resource limits are not set"),
                'severity': 'warning',
                'recommendation': "Set resource limits for CPU and memory"
            },
            {
                'name': 'health_checks',
                'attribute_path': ['Containers', 0, 'LivenessProbe'],
                'condition': lambda val: (val is not None, 
                    "Health checks are configured" if val is not None else 
                    "Health checks are not configured"),
                'severity': 'warning',
                'recommendation': "Configure health checks for better reliability"
            },
            {
                'name': 'image_tag',
                'attribute_path': ['Containers', 0, 'Image'],
                'condition': lambda val: (val is not None and ':latest' not in val, 
                    "Image tag is specific" if val is not None and ':latest' not in val else 
                    "Image uses 'latest' tag"),
                'severity': 'warning',
                'recommendation': "Use specific image tags instead of 'latest'"
            }
        ]

        return self._generic_resource_check(tenant, filtered_services, k8s_checks)
