from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator
from schemas.ToolResult import ToolResult

class CheckK8sDeploymentProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([
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
            }])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_k8s_deployment_readiness",
            "description": "Checks input k8s deployment for prod readiness",
            "input_schema": {
                "type": "array",
                "description": "List of kubernetes deployments needing prod readiness assessment",
                "items": {
                    "type": "object",
                    "properties": {
                        "Replicas": {
                            "type": "integer",
                            "description": "The set number of replicas configured for the k8s deployment"
                        },
                        "HPASpecs": {
                            "type": "object",
                            "description": "The horizontal pod autoscaler (HPA) configuration for the k8s deployment",
                            "properties": {
                                "minReplicas": {
                                    "type": "integer",
                                    "description": "The minimum number of replicas that should host the k8s deployment"
                                },
                                "metrics": {
                                    "type": "array",
                                    "description": "Metrics configured for monitoring the k8s deployment's HPA",
                                    "items": {
                                        "type": "object",
                                        "description": "Individual metric of the HPA"
                                    }
                                }
                            }
                        },
                        "Template": {
                            "type": "object",
                            "properties": {
                                "OtherDockerConfig": {
                                    "type": "string",
                                    "description": "Stringified miscelaneous docker configurations that apply to the k8s deployment"
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]], tool_id: str) -> ToolResult:
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": self.evaluator.evaluate(resources)
        }
