from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator
from schemas.ProdReadinessCheck import ProdReadinessCheck
from schemas.ToolResult import ToolResult

class CheckAutoScalingGroupProdReadinessTool:
    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_asg_prod_readiness",
            "description": "Checks input ASG for prod readiness",
            "input_schema": {
                "type": "object",
                "properties": {
                    "entities": {

                        "type": "array",
                        "description": "List of Auto Scaling Groups needing prod readiness assessment",
                        "items": {
                            "type": "object",
                            "properties": {
                                "IsClusterAutoscaled": {
                                    "type": "boolean",
                                    "description": "Whether or not Cluster autoscaling is enabled for this ASG"
                                },
                                "Zones": {
                                    "type": "array",
                                    "description": "List of zones the ASG is configured in",
                                    "items": {
                                        "type": "string",
                                        "description": "Name of an AWS zone"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]], tool_id: str) -> ToolResult:
        if resources is None or resources == []:
            checks = [
                {
                    'name': 'asg_not_found',
                    'condition': lambda val: (False, "No Auto Scaling Groups found"),
                    'severity': 'critical',
                    'recommendation': "Configure Auto Scaling Groups for high availability and fault tolerance in production environments"
                }
            ]
        else:
            checks: List[ProdReadinessCheck] = [
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

        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": ProdReadinessChecksEvaluator(checks).evaluate(resources)
        }
