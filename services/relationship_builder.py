"""Transform AWSResource objects into node/link structures for graph storage or visualization."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from models import AWSResource

Node = Dict[str, Any]
Link = Dict[str, str]


class RelationshipBuilder:
    """Convert resources to graph nodes and links."""

    def __init__(self, resources: List[AWSResource]):
        self.resources = resources

    def build(self) -> Tuple[List[Node], List[Link]]:
        nodes: List[Node] = []
        links: List[Link] = []

        for res in self.resources:
            nodes.append(
                {
                    "id": res.resource_id,
                    "type": res.resource_type,
                    "state": res.state,
                    "icon": res.icon,
                    "tags": res.tags,
                    "zone": res.configuration.get("availability_zone"),
                }
            )
            for rel in res.relationships:
                links.append(
                    {
                        "source": res.resource_id,
                        "target": rel["to"],
                        "type": rel.get("type", "related-to"),
                    }
                )

        # Optionally ensure bidirectional uniqueness
        unique_links = {(link["source"], link["target"], link["type"]): link for link in links}
        return nodes, list(unique_links.values())

__all__: List[str] = ["RelationshipBuilder", "Node", "Link"]
