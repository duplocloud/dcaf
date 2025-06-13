from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator

class CheckSystemSettingsProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([
            {
                'name': 'token_expiration_notification',
                'attribute_path': ['TokenExpirationNotificationEnabled'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"User token expiration notification is enabled ({resource.get('TokenExpirationNotificationDays', 0)} days)" if val is True 
                    else "User token expiration notification is not enabled"
                ),
                'severity': 'warning',
                'recommendation': "Enable user token expiration notification to alert users before their tokens expire"
            },
            {
                'name': 'token_expiration_emails',
                'attribute_path': ['HasTokenExpirationEmails'],
                'condition': lambda val, resource=None: (
                    val is True,
                    "Token expiration notification emails are configured" if val is True 
                    else "Token expiration notification emails are not configured"
                ),
                'severity': 'warning',
                'recommendation': "Configure token expiration notification emails to ensure notifications are delivered"
            }
        ])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_system_settings_prod_readiness",
            "description": "Checks input system settings for prod readiness",
            "input_schema": {
                "type": "object",
                "properties": {
                     "TokenExpirationNotificationEnabled": {
                         "type": "boolean",
                         "description": "Whether token expiration notifications have been configured in the system to alert users before their tokens expire"
                     },
                     "HasTokenExpirationEmails": {
                         "type": "boolean",
                         "description": "Whether an email has been configured to receive token expiration notifications"
                     }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.evaluator.evaluate(resources)
