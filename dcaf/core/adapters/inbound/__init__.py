"""
Inbound Adapters - Entry Points.

Inbound adapters handle incoming requests from external systems
and translate them to application service calls.

Examples:
    - ServerAdapter: FastAPI server integration
    - CLI handlers
    - Message queue consumers
"""

from .server_adapter import ServerAdapter

__all__ = ["ServerAdapter"]
