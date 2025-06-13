from typing import Any, Dict
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetK8sDeploymentsTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)
        self.duplo_k8s_deployments_client = self.duplo_client.official_client.load("service").list()

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "list_tenant_k8s_deployments",
            "description": "Lists K8s deployments in the tenant configured in platform_context",
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": filter(lambda deployment: \
                all([not deployment.startswith(prefix) for prefix in ["filebeat-k8s-", "cadvisor-k8s-", "node-exporter-k8s-"]]), \
                self.duplo_k8s_deployments_client.list())
        }