from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator
from schemas.ToolResult import ToolResult

class CheckElastiCacheProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([
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
        ])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_elasticache_prod_readiness",
            "description": "Checks input elasticache clusters for prod readiness",
            "input_schema": {
                "type": "array",
                "description": "List of ElastiCache clusters needing prod readiness assessment",
                "items": {
                    "type": "object",
                    "properties": {
                        "EnableEncryptionAtRest": {
                            "type": "boolean",
                            "description": "Whether ElastiCache Cluster has been configured with encryption at rest"
                        },
                        "EnableEncryptionAtTransit": {
                            "type": "boolean",
                            "description": "Whether ElastiCache Cluster has been configured with encryption in transit"
                        },
                        "MultiAZEnabled": {
                            "type": "boolean",
                            "description": "Whether ElastiCache Cluster has been configured with multi availability zone"
                        },
                        "AutomaticFailoverEnabled": {
                            "type": "boolean",
                            "description": "Whether ElastiCache Cluster has multi failover enabled or not"
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
