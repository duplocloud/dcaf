from typing import Any, Dict, Optional, Tuple
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetTenantSettingsTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "get_tenant_settings",
            "description": "Gets tenant scoped settings for configured tenant",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        tenant_resource = {
            "identifier": f"{self.duplo_client.tenant_name}",
            "Name": f"{self.duplo_client.tenant_name}",
            "LoggingEnabled": self._is_tenant_logging_enabled(),
            "MonitoringEnabled": self._is_tenant_monitoring_enabled(),
            "AlertingEnabled": self._is_tenant_alerting_enabled(),
        }

        tenant_notification_enabled, tenant_configured_notification_channel = self._get_tenant_notification_status()

        tenant_resource["NotificationConfigured"] = tenant_notification_enabled
        tenant_resource["NotificationChannel"] = tenant_configured_notification_channel
        
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": [tenant_resource]
        }
    
    def _is_tenant_logging_enabled(self) -> bool:
        logging_enabled_tenants = self.duplo_client.get("admin/GetLoggingEnabledTenants")

        return logging_enabled_tenants is not None and \
            any([ \
                tenant_logging.get("TenantId") == self.duplo_client.tenant_id and \
                tenant_logging.get("Enabled") is True \
                for tenant_logging in logging_enabled_tenants \
            ])
    
    def _is_tenant_monitoring_enabled(self) -> bool:
        tenant_monitoring_setting = self.duplo_client.get("admin/GetMonitoringConfigForTenant/default")
        
        return self._is_tenant_monitoring_globally_enabled(tenant_monitoring_setting) and \
            any([ \
                tenant_info.get("TenantId") == self.duplo_client.tenant_id and \
                tenant_info.get("Enabled") is True \
                for tenant_info in tenant_monitoring_setting.get("EnabledTenants", []) \
            ])
    
    def _is_tenant_monitoring_globally_enabled(self, tenant_monitoring_setting: Optional[Dict[str, Any]]) -> bool:
        return tenant_monitoring_setting is not None and \
            isinstance(tenant_monitoring_setting, dict) and \
            tenant_monitoring_setting.get("Enabled") is True
    
    def _is_tenant_alerting_enabled(self) -> bool:
        tenant_alerting_setting = self.duplo_client.get(f"v3/admin/tenant/{self.duplo_client.tenant_id}/metadata/enable_alerting")

        return tenant_alerting_setting is not None and \
            ( \
                # for API format #1
                isinstance(tenant_alerting_setting, dict) and tenant_alerting_setting.get("Value", "").lower() == "true" or \
                # for API format #2
                isinstance(tenant_alerting_setting, dict) and tenant_alerting_setting.get("Key") == "enable_alerting" and tenant_alerting_setting.get("Value", "").lower() == "true" \
            )
    
    def _get_tenant_notification_status(self) -> Tuple[bool, str]:
        tenant_notification_setting = self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetTenantMonConfig")

        # Extract notification configuration status
        notification_configured = False
        notification_channel = "None"
        if tenant_notification_setting is not None:
            notification_data = tenant_notification_setting
            if isinstance(notification_data, dict):
                # Check for different notification channels
                if notification_data.get("RoutingKey"):
                    notification_configured = True
                    notification_channel = "PagerDuty"
                elif notification_data.get("Dsn"):
                    notification_configured = True
                    notification_channel = "Sentry"
                elif notification_data.get("NrApiKey"):
                    notification_configured = True
                    notification_channel = "New Relic"
                elif notification_data.get("OpsGenieApiKey"):
                    notification_configured = True
                    notification_channel = "OpsGenie"
        return notification_configured, notification_channel
