from typing import Any, Dict
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetElastiCacheInstancesTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)
        self.duplo_rds_client = self.duplo_client.official_client.load("rds")

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "list_tenant_elasticache_instances",
            "description": "Lists ElastiCache instances in the tenant configured in platform_context",
            "input_schema": {}
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": self.duplo_client.get(f"subscriptions/{self.duplo_client.tenant_id}/GetEcacheInstances")
        }