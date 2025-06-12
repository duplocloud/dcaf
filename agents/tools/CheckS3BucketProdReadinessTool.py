from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator

class CheckS3BucketProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([
            {
                'name': 'encryption',
                'attribute_path': ['DefaultEncryption'],
                'condition': lambda val: (val is not None, 
                    "Server-side encryption is enabled" if val is not None else 
                    "Server-side encryption is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable server-side encryption"
            },
            {
                'name': 'public_access_block',
                'attribute_path': ['AllowPublicAccess'],
                'condition': lambda val: (val is False,
                    "Block public access is enabled" if val is False else
                    "Block public access is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable block public access"
            },
            {
                'name': 'versioning',
                'attribute_path': ['EnableVersioning'],
                'condition': lambda val: (val is True, 
                    "Versioning is enabled" if val is True else 
                    "Versioning is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable versioning for data protection"
            },
            {
                'name': 'logging',
                'attribute_path': ['EnableAccessLogs'],
                'condition': lambda val: (val is True, 
                    "Logging is enabled" if val is True else 
                    "Logging is not enabled"),
                'severity': 'warning',
                'recommendation': "Enable logging to track bucket access"
            },
        ])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_s3_prod_readiness",
            "description": "Checks input s3 instances for prod readiness",
            "input_schema": {
                "type": "object",
                "properties": {
                     "DefaultEncryption": {
                         "type": "string",
                         "description": "Default encryption method the s3 bucket is configured to use"
                     },
                     "AllowPublicAccess": {
                         "type": "boolean",
                         "description": "whether or not the bucket allows access from the public internet"
                     },
                     "EnableVersioning": {
                         "type": "boolean",
                         "description": "Whether or not bucket versioning is enabled for the s3 bucket"
                     },
                     "EnableAccessLogs": {
                         "type": "boolean",
                         "description": "Whether or not access logs is enabled for monitoring access of s3 bucket"
                     }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.evaluator.evaluate(resources)
