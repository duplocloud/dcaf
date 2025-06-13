from typing import Any, Dict, List
from agents.tools.ProdReadinessChecksEvaluator import ProdReadinessChecksEvaluator

class CheckTenantSettingsProdReadinessTool:
    def __init__(self):
        self.evaluator = ProdReadinessChecksEvaluator([
            {
                'name': 'logging_enabled',
                'attribute_path': ['LoggingEnabled'],
                'condition': lambda val: (val is True,
                                         "Logging is enabled" if val is True else "Logging is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable logging for the tenant to ensure proper audit trails and troubleshooting capabilities"
            },
            {
                'name': 'monitoring_enabled',
                'attribute_path': ['MonitoringEnabled'],
                'condition': lambda val: (val is True,
                                         "Monitoring is enabled" if val is True else "Monitoring is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable monitoring for the tenant to track resource performance and health"
            },
            {
                'name': 'alerting_enabled',
                'attribute_path': ['AlertingEnabled'],
                'condition': lambda val: (val is True,
                                         "Alerting is enabled" if val is True else "Alerting is not enabled"),
                'severity': 'critical',
                'recommendation': "Enable alerting to receive notifications for critical events and issues"
            },
            {
                'name': 'notification_configured',
                'attribute_path': ['NotificationConfigured'],
                'condition': lambda val, resource=None: (
                    val is True,
                    f"Alert notification is configured using {resource.get('NotificationChannel')}" if val is True and resource else "Alert notification is not configured"
                ),
                'severity': 'critical',
                'recommendation': "Configure alert notification channel (PagerDuty, Sentry, New Relic, or OpsGenie) to ensure timely response to critical alerts"
            }
        ])

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "check_tenant_configuration_prod_readiness",
            "description": "Checks input tenant configuration for prod readiness",
            "input_schema": {
                "type": "object",
                "properties": {
                     "LoggingEnabled": {
                         "type": "boolean",
                         "description": "Whether tenant has duplocloud's logging feature enabled"
                     },
                     "MonitoringEnabled": {
                         "type": "boolean",
                         "description": "Whether monitoring has been enabled for the tenant"
                     },
                     "AlertingEnabled": {
                         "type": "boolean",
                         "description": "Whether alerting has been properly configured for the tenant"
                     },
                     "NotificationConfigured": {
                         "type": "boolean",
                         "description": "Whether notifications have been configured for the tenant"
                     }
                }
            }
        }
    
    def execute(self, resources: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.evaluator.evaluate(resources)
