from typing import Optional, TypedDict

class ResourceProdReadinessCheckResult(TypedDict):
    passed: bool
    message: str
    severity: str
    recommendation: str
    score: Optional[float]
