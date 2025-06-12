from typing import Any, Dict
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetRdsInstancesTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)
        self.duplo_rds_client = self.duplo_client.official_client.load("rds")

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "list_tenant_rds_instances",
            "description": "Lists RDS instances in the tenant configured in platform_context",
            "input_schema": {}
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": self.duplo_rds_client.list()
        }