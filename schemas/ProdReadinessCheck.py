from typing import Callable, Tuple, TypedDict


class ProdReadinessCheck(TypedDict):
    name: str
    attribute_path: str
    condition: Callable[object, Tuple[bool, str]]
    severity: str
    recommendation: str