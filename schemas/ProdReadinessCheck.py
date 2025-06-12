from typing import Callable, TypedDict


class ProdReadinessCheck(TypedDict):
    name: str
    attribute_path: str
    condition: Callable[object, bool]
    severity: str
    recommendation: str