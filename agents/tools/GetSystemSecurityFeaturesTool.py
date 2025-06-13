from typing import Any, Dict
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetSystemSecurityFeaturesTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "get_system_security_features",
            "description": "Gets the security related features configured in the DuploCloud system",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        aws_security_configuration = self.duplo_client.get("v3/admin/systemSettings/awsAccountSecurity")

        # Extract security features
        security_features = {} \
            if aws_security_configuration is None or not isinstance(aws_security_configuration, dict) \
            else aws_security_configuration.get("Features", {})

        security_resource = {
            "identifier": "aws-security",
            "Name": "aws-security",
            "EnableVpcFlowLogs": security_features.get("EnableVpcFlowLogs", False),
            "EnableSecurityHub": security_features.get("EnableSecurityHub", False),
            "EnableGuardDuty": security_features.get("EnableGuardDuty", False),
            "EnableCloudTrail": security_features.get("EnableCloudTrail", False),
            "EnablePasswordPolicy": security_features.get("EnablePasswordPolicy", False),
            "EnableGlobalS3PublicAccessBlock": security_features.get("EnableGlobalS3PublicAccessBlock", False),
            "EnableInspector": security_features.get("EnableInspector", False),
            "EnableCisCloudTrailCloudWatchAlarms": security_features.get("EnableCisCloudTrailCloudWatchAlarms", False),
            "EnableAllSecurityHubRegions": security_features.get("EnableAllSecurityHubRegions", False),
            "EnableAllInspectorRegions": security_features.get("EnableAllInspectorRegions", False),
            "DeleteDefaultVpcs": security_features.get("DeleteDefaultVpcs", False),
            "RevokeDefaultSgRules": security_features.get("RevokeDefaultSgRules", False),
        }

        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": [security_resource]
        }