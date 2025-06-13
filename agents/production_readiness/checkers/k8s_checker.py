# k8s_checker.py
from typing import List, Dict, Any, Optional
from .base_checker import BaseChecker
import logging
from ..resource_provider import ResourceProvider

logger = logging.getLogger(__name__)

class K8sDeploymentProductionReadinessChecker(BaseChecker):
    """Checker for Kubernetes deployment production readiness"""
    
    def check(self, tenant: str, deployments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Check Kubernetes deployments for production readiness
        
        Args:
            tenant: Tenant name or ID
            deployments: List of Kubernetes deployments to check
            
        Returns:
            Dictionary with check results
        """
        # Fetch Kubernetes deployments if not provided
        if deployments is None:
            deployments = self.get_resources(tenant, "k8s_deployments")
            
            # Filter out system deployments
            exclude_prefixes = ["filebeat-k8s-", "cadvisor-k8s-", "node-exporter-k8s-", 
                               "kube-", "system-", "metrics-", "istio-", "monitoring-"]
            deployments = self._filter_resources(deployments, exclude_prefixes)
        
        # Define checks for Kubernetes deployments
        k8s_checks = [
            {
                'name': 'replicas',
                'attribute_path': ['Replicas'],
                'condition': lambda val: (val >= 2 if isinstance(val, (int, float)) else False,
                                         f"Deployment has {val} replicas" if isinstance(val, (int, float)) else
                                         "Replica count not determined"),
                'severity': 'critical',
                'recommendation': "Configure at least 2 replicas for high availability"
            },
            {
                'name': 'hpa_configured',
                'attribute_path': ['HPASpecs'],
                'condition': lambda val: (
                    val is not None,
                    "HPA is configured" if val is not None else "HPA is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure Horizontal Pod Autoscaler (HPA) for automatic scaling"
            },
            {
                'name': 'hpa_min_replicas',
                'attribute_path': ['HPASpecs', 'minReplicas'],
                'condition': lambda val: (
                    isinstance(val, (int, float)) and val >= 2,
                    f"HPA minimum replicas is {val}" if isinstance(val, (int, float)) else "HPA minimum replicas not determined"
                ),
                'severity': 'critical',
                'recommendation': "Configure HPA with at least 2 minimum replicas for high availability"
            },
            {
                'name': 'hpa_metrics_configured',
                'attribute_path': ['HPASpecs', 'metrics'],
                'condition': lambda metrics: (
                    isinstance(metrics, list) and len(metrics) > 0,
                    f"HPA has {len(metrics)} metrics configured" if isinstance(metrics, list) else "HPA metrics not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure HPA with appropriate metrics (CPU/memory)"
            },
            {
                'name': 'resource_limits',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"Resources"' in config and '"limits"' in config,
                    "Resource limits are configured" if isinstance(config, str) and '"Resources"' in config and '"limits"' in config else
                    "Resource limits are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Set resource limits for all containers"
            },
            {
                'name': 'resource_requests',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"Resources"' in config and '"requests"' in config,
                    "Resource requests are configured" if isinstance(config, str) and '"Resources"' in config and '"requests"' in config else
                    "Resource requests are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Set resource requests for all containers"
            },
            {
                'name': 'liveness_probe',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"LivenessProbe"' in config,
                    "Liveness probe is configured" if isinstance(config, str) and '"LivenessProbe"' in config else
                    "Liveness probe is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure liveness probe to ensure automatic restart of unhealthy containers"
            },
            {
                'name': 'readiness_probe',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"ReadinessProbe"' in config,
                    "Readiness probe is configured" if isinstance(config, str) and '"ReadinessProbe"' in config else
                    "Readiness probe is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure readiness probe to prevent routing traffic to containers that aren't ready"
            },
            {
                'name': 'rolling_update_strategy',
                'attribute_path': ['Template', 'OtherDockerConfig'],
                'condition': lambda config: (
                    isinstance(config, str) and '"DeploymentStrategy"' in config and '"RollingUpdate"' in config,
                    "Rolling update strategy is configured" if isinstance(config, str) and '"DeploymentStrategy"' in config and '"RollingUpdate"' in config else
                    "Rolling update strategy is not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure rolling update strategy for zero-downtime deployments"
            }
        ]
        
        return self._generic_resource_check(tenant, deployments, k8s_checks)