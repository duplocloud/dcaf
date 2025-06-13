from typing import List

from schemas.ProdReadinessReport import ProdReadinessReport, ProdReadinessSummary
from schemas.ResourceProdReadinessReport import ResourceProdReadinessReport
from schemas.ToolResult import ToolResult
from schemas.messages import PlatformContext

class GenerateProdReadinessSummaryTool:

    def __init__(self, platform_context: PlatformContext):
        self.tenant_name = platform_context["tenant_name"]

    def get_definition(self):
        return {
            "name": "generate_full_prod_readyness_report",
            "description": "Aggregates results from previously computed prod readiness assessments into one full report",
            "input_schema": {
                "type": "array",
                "description": "A list of prod readiness reports from various resources whose data needs aggregation",
                "items": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                        "passed": { "type": "boolean" },
                        "message": { "type": "string" },
                        "severity": { "type": "string" },
                        "recommendation": { "type": "string" },
                        "score": { "type": "number" }
                        },
                        "required": ["passed","message","severity","recommendation"]
                    }
                }
            }
        }
    
    def execute(self, reports: List[ResourceProdReadinessReport], tool_id: str) -> ToolResult:
        """
        Calculate summary statistics for assessment results.
        
        Args:
            results: Assessment results dictionary to update with summary
        """
        total_resources = 0
        passing_resources = 0
        critical_issues = 0
        warnings = 0

        for report in reports:
            if not report:
                continue

            # Handle list format (most resource types)
            if isinstance(report, list):
                for resource in report:
                    if not isinstance(resource, dict):
                        continue
                        
                    total_resources += 1
                    
                    # Count issues by severity
                    critical_failures = 0
                    warning_count = 0
                    
                    for check in resource.get("checks", []):
                        if not check.get("passed", True):
                            if check.get("severity") == "critical":
                                critical_failures += 1
                            elif check.get("severity") == "warning":
                                warning_count += 1
                    
                    # Store counts in the resource for future reference
                    resource["critical_failures"] = critical_failures
                    resource["warnings"] = warning_count
                    
                    # A resource is considered passing if it has no critical failures
                    if critical_failures == 0:
                        passing_resources += 1
                    
                    critical_issues += critical_failures
                    warnings += warning_count
            
            # Handle dict format (aws_security and system_settings)
            elif isinstance(report, dict) and "checks" in report:
                total_resources += 1
                critical_failures = 0
                warning_count = 0
                
                for check in report.get("checks", []):
                    if not check.get("passed", True):
                        if check.get("severity") == "critical":
                            critical_failures += 1
                        elif check.get("severity") == "warning":
                            warning_count += 1
                
                # Store counts in the resource for future reference
                report["critical_failures"] = critical_failures
                report["warnings"] = warning_count
                
                # A resource is considered passing if it has no critical failures
                if critical_failures == 0:
                    passing_resources += 1
                
                critical_issues += critical_failures
                warnings += warning_count

        prod_readiness_report: ProdReadinessReport = {
            "tenant": self.tenant_name,
            "timestamp": self._get_current_timestamp(),
            "resources": reports,
            "summary": {
                "total_resources": total_resources,
                "passing_resources": passing_resources,
                "critical_issues": critical_issues,
                "warnings": warnings,

                # Calculate overall score (0-100)
                "overall_score": 0 if total_resources <= 0 else \
                    max(0, min(100, 100 - (critical_issues * 15 + warnings * 5) / total_resources))
            }
        }
        
        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": prod_readiness_report
        }

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()