from typing import Any, Dict
from agents.tools.BaseDuploInterfaceTool import BaseDuploInterfaceTool
from schemas import ToolResult


class GetS3BucketsTool(BaseDuploInterfaceTool):
    def __init__(self, platform_context):
        super().__init__(platform_context)
        self.duplo_s3_client = self.duplo_client.official_client.load("s3")

    def get_definition(self) -> Dict[str, Any]:
        return {
            "name": "list_tenant_s3_buckets",
            "description": "Lists s3 Buckets in the tenant configured in platform_context",
            "input_schema": {}
        }
    
    def execute(self, tool_id: str) -> ToolResult:
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": self.duplo_s3_client.list()
        }