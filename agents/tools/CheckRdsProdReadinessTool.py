from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator

class CheckRdsProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([{
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
            }])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_rds_prod_readiness",
            "description": "Checks input rds instances for prod readiness",
            "input_schema": {
                "type": "object",
                "properties": {
                     "EncryptStorage": {
                          "type": "boolean",
                          "description": "Whether RDS instance has been configured with encryption at rest"
                     },
                     "MultiAZ": {
                          "type": "boolean",
                          "description": "Whether RDS has been configured with multi Availability Zone"
                     },
                     "BackupRetentionPeriod": {
                          "type": "integer",
                          "description": "The retention period for backups made out of this RDS instance"
                     },
                     "EnableLogging": {
                          "type": "bollean",
                          "description": "Whether logging has been enabled for this RDS instance"
                     },
                     "DeletionProtection": {
                          "type": "boolean",
                          "description": "Whether RDS instance is configured with duplocloud's delete protection feature"
                     },
                     "EnablePerformanceInsights": {
                          "type": "boolean",
                          "description": "Whether RDS has performance insights enabled"
                     }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.evaluator.evaluate(resources)
