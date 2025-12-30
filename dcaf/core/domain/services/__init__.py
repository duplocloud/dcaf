"""
Domain Services - Stateless business operations.

Domain services encapsulate business logic that doesn't naturally
fit within a single entity or value object. They are stateless
and operate on domain objects.
"""

from .approval_policy import ApprovalPolicy

__all__ = [
    "ApprovalPolicy",
]
