from typing import Any, Dict
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetSystemSettingsTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "get_duplocloud_system_settings",
            "description": "Lists system level settings currently configured in the DuploCloud platform",
            "input_schema": {}
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        system_settings = self.duplo_client.get("v3/admin/systemSettings/config")

        # Create a synthetic resource to represent system settings
        system_resource = {
            'identifier': "system-settings",
            'Name': "system-settings"
        }
        
        # Extract system settings
        token_expiration_notification_enabled = False
        token_expiration_notification_days = 0
        token_expiration_notification_emails = ""
        
        if system_settings is not None and isinstance(system_settings, list):
            for setting in system_settings:
                if setting.get("Type") == "AppConfig" and setting.get("Key") == "EnableUserTokenExpirationNotification":
                    try:
                        days = int(setting.get("Value", "0"))
                        if days > 0:
                            token_expiration_notification_enabled = True
                            token_expiration_notification_days = days
                    except (ValueError, TypeError):
                        pass
                
                if setting.get("Type") == "AppConfig" and setting.get("Key") == "UserTokenExpirationNotificationEmails":
                    token_expiration_notification_emails = setting.get("Value", "")
        
        # Add settings to resource
        system_resource["TokenExpirationNotificationEnabled"] = token_expiration_notification_enabled
        system_resource["TokenExpirationNotificationDays"] = token_expiration_notification_days
        system_resource["TokenExpirationNotificationEmails"] = token_expiration_notification_emails
        system_resource["HasTokenExpirationEmails"] = bool(token_expiration_notification_emails)

        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": [system_resource]
        }