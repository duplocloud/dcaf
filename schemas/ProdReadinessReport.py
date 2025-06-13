
from typing import List, TypedDict

from schemas.ResourceProdReadinessReport import ResourceProdReadinessReport

class ProdReadinessSummary(TypedDict):
    total_resources: int
    passing_resources: int
    critical_issues: int
    warnings: int
    overall_score: float

class ProdReadinessReport(TypedDict):
    tenant: str
    timestamp: str
    resources: List[ResourceProdReadinessReport]
    summary: ProdReadinessSummary
