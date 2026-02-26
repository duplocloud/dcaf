# tests/core/test_discovery.py
from dcaf.core.discovery import (
    DiscoveryEdge,
    DiscoveryNode,
    DiscoveryPayload,
)


class TestDiscoveryModels:
    def test_discovery_node_creation(self):
        node = DiscoveryNode(
            id="n1",
            labels=["Service"],
            properties={"name": "web-api", "status": "running"},
        )
        assert node.id == "n1"
        assert node.labels == ["Service"]
        assert node.properties["name"] == "web-api"

    def test_discovery_edge_creation(self):
        edge = DiscoveryEdge(
            id="e1",
            type="CONNECTS_TO",
            startNode="n1",
            endNode="n2",
            properties={"port": 5432},
        )
        assert edge.id == "e1"
        assert edge.type == "CONNECTS_TO"
        assert edge.startNode == "n1"
        assert edge.endNode == "n2"

    def test_discovery_edge_empty_properties_default(self):
        edge = DiscoveryEdge(id="e1", type="RUNS_ON", startNode="n1", endNode="n2")
        assert edge.properties == {}

    def test_discovery_payload_creation(self):
        payload = DiscoveryPayload(
            nodes=[DiscoveryNode(id="n1", labels=["Service"], properties={"name": "web-api"})],
            edges=[
                DiscoveryEdge(
                    id="e1", type="CONNECTS_TO", startNode="n1", endNode="n2", properties={}
                )
            ],
        )
        assert len(payload.nodes) == 1
        assert len(payload.edges) == 1

    def test_discovery_payload_serialization_matches_ui_format(self):
        payload = DiscoveryPayload(
            nodes=[
                DiscoveryNode(
                    id="n1",
                    labels=["Service"],
                    properties={"name": "web-api", "replicas": 3},
                )
            ],
            edges=[
                DiscoveryEdge(
                    id="e1",
                    type="CONNECTS_TO",
                    startNode="n1",
                    endNode="n2",
                    properties={"port": 5432},
                )
            ],
        )
        data = payload.model_dump()
        assert data == {
            "nodes": [
                {
                    "id": "n1",
                    "labels": ["Service"],
                    "properties": {"name": "web-api", "replicas": 3},
                }
            ],
            "edges": [
                {
                    "id": "e1",
                    "type": "CONNECTS_TO",
                    "startNode": "n1",
                    "endNode": "n2",
                    "properties": {"port": 5432},
                }
            ],
        }
