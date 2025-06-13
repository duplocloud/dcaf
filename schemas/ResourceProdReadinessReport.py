

from typing import Dict, TypedDict
from schemas.ResourceProdReadinessCheckResult import ResourceProdReadinessCheckResult

class ResourceProdReadinessReport(TypedDict):
    checks: Dict[str, ResourceProdReadinessCheckResult]
    pass_count: int
    fail_count: int
    critical_failures: int
    warnings: int