# tests/core/test_discovery.py
from dcaf.core.discovery import (
    DiscoveryEdge,
    DiscoveryNode,
    DiscoveryPayload,
    drain_discovery_queue,
    emit_discovery,
    reset_discovery_queue,
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


class TestEmitDiscovery:
    def setup_method(self):
        reset_discovery_queue()

    def test_emit_discovery_queues_payload(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )
        payloads = drain_discovery_queue()
        assert len(payloads) == 1
        assert payloads[0].nodes[0].id == "n1"

    def test_emit_discovery_multiple_calls_queue_in_order(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "first"}}],
            edges=[],
        )
        emit_discovery(
            nodes=[{"id": "n2", "labels": ["Database"], "properties": {"name": "second"}}],
            edges=[],
        )
        payloads = drain_discovery_queue()
        assert len(payloads) == 2
        assert payloads[0].nodes[0].properties["name"] == "first"
        assert payloads[1].nodes[0].properties["name"] == "second"

    def test_drain_clears_queue(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )
        drain_discovery_queue()
        payloads = drain_discovery_queue()
        assert len(payloads) == 0

    def test_drain_empty_queue_returns_empty_list(self):
        payloads = drain_discovery_queue()
        assert payloads == []

    def test_emit_discovery_with_edges(self):
        emit_discovery(
            nodes=[
                {"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}},
                {"id": "n2", "labels": ["Database"], "properties": {"name": "postgres"}},
            ],
            edges=[
                {
                    "id": "e1",
                    "type": "CONNECTS_TO",
                    "startNode": "n1",
                    "endNode": "n2",
                    "properties": {"port": 5432},
                }
            ],
        )
        payloads = drain_discovery_queue()
        assert len(payloads) == 1
        assert len(payloads[0].nodes) == 2
        assert len(payloads[0].edges) == 1
        assert payloads[0].edges[0].type == "CONNECTS_TO"

    def test_reset_clears_queue(self):
        emit_discovery(
            nodes=[{"id": "n1", "labels": ["Service"], "properties": {"name": "web-api"}}],
            edges=[],
        )
        reset_discovery_queue()
        payloads = drain_discovery_queue()
        assert payloads == []


class TestDiscoveryEvent:
    def test_discovery_event_type(self):
        from dcaf.core.schemas.events import DiscoveryEvent

        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[DiscoveryNode(id="n1", labels=["Service"], properties={"name": "web-api"})],
                edges=[],
            )
        )
        assert event.type == "discovery"

    def test_discovery_event_serialization_matches_ui_format(self):
        from dcaf.core.schemas.events import DiscoveryEvent

        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[
                    DiscoveryNode(
                        id="n1",
                        labels=["Service"],
                        properties={"name": "web-api", "status": "running"},
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
        )
        data = event.model_dump()
        assert data["type"] == "discovery"
        assert "discovery" in data
        assert data["discovery"]["nodes"][0]["id"] == "n1"
        assert data["discovery"]["edges"][0]["type"] == "CONNECTS_TO"

    def test_discovery_event_json_serialization(self):
        """Verify model_dump_json() produces valid JSON the server can stream."""
        import json

        from dcaf.core.schemas.events import DiscoveryEvent

        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[DiscoveryNode(id="n1", labels=["Host"], properties={"name": "worker-1"})],
                edges=[],
            )
        )
        json_str = event.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["type"] == "discovery"
        assert parsed["discovery"]["nodes"][0]["properties"]["name"] == "worker-1"


class TestNeo4jResultParser:
    def test_parse_simple_node_results(self):
        """Parse a result from MATCH (n:Service) RETURN n."""
        from dcaf.core.discovery import neo4j_result_to_discovery

        neo4j_data = [
            {"n": {"name": "web-api", "status": "running"}},
            {"n": {"name": "postgres", "engine": "PostgreSQL 15"}},
        ]
        payload = neo4j_result_to_discovery(neo4j_data)
        assert len(payload.nodes) == 2
        assert payload.nodes[0].properties["name"] == "web-api"
        assert payload.nodes[1].properties["name"] == "postgres"

    def test_nodes_get_deterministic_ids(self):
        """Same data should produce the same ID."""
        from dcaf.core.discovery import neo4j_result_to_discovery

        neo4j_data = [{"n": {"name": "web-api"}}]
        payload1 = neo4j_result_to_discovery(neo4j_data)
        payload2 = neo4j_result_to_discovery(neo4j_data)
        assert payload1.nodes[0].id == payload2.nodes[0].id

    def test_empty_result_returns_empty_payload(self):
        from dcaf.core.discovery import neo4j_result_to_discovery

        payload = neo4j_result_to_discovery([])
        assert payload.nodes == []
        assert payload.edges == []

    def test_string_result_returns_empty_payload(self):
        """If result is a plain string (e.g., error), return empty."""
        from dcaf.core.discovery import neo4j_result_to_discovery

        payload = neo4j_result_to_discovery("No results found")
        assert payload.nodes == []
        assert payload.edges == []

    def test_nodes_use_name_property_for_label_if_no_labels(self):
        """When neo4j labels are lost in .data(), use column name as label."""
        from dcaf.core.discovery import neo4j_result_to_discovery

        neo4j_data = [{"n": {"name": "web-api"}}]
        payload = neo4j_result_to_discovery(neo4j_data)
        assert len(payload.nodes[0].labels) >= 1

    def test_deduplicates_nodes(self):
        """Same node appearing in multiple rows should be deduplicated."""
        from dcaf.core.discovery import neo4j_result_to_discovery

        neo4j_data = [
            {"n": {"name": "web-api"}, "m": {"name": "postgres"}},
            {"n": {"name": "web-api"}, "m": {"name": "redis"}},
        ]
        payload = neo4j_result_to_discovery(neo4j_data)
        names = [n.properties.get("name") for n in payload.nodes]
        assert len(set(names)) == len(names)  # No duplicates


class TestAgentDiscoveryPassthrough:
    def test_convert_stream_event_passes_through_server_events(self):
        """DiscoveryEvent (Pydantic) should pass through _convert_stream_event unchanged."""
        from dcaf.core.agent import Agent
        from dcaf.core.schemas.events import DiscoveryEvent
        from dcaf.core.schemas.events import StreamEvent as ServerStreamEvent

        agent = Agent(tools=[])
        event = DiscoveryEvent(
            discovery=DiscoveryPayload(
                nodes=[DiscoveryNode(id="n1", labels=["Service"], properties={"name": "api"})],
                edges=[],
            )
        )
        pending: list = []
        result = agent._convert_stream_event(event, pending)
        assert result is event
        assert isinstance(result, ServerStreamEvent)
