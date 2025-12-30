"""Mock infrastructure updater for demo purposes.

Provides a function to apply a simple change (add EC2 instance) to an existing
resource list and returns the node/link created.
"""
from __future__ import annotations

import random
from typing import List, Tuple

from models import AWSResource, ResourceType


def add_instance(resources: List[AWSResource], *, rng: random.Random | None = None) -> Tuple[AWSResource, dict]:
    """Add a new EC2 instance to a random subnet in *resources*.

    Returns the new node and its link dict.
    """
    if rng is None:
        rng = random.Random()
    # Pick a subnet
    subnets = [r for r in resources if r.resource_type is ResourceType.SUBNET]
    if not subnets:
        raise ValueError("No subnet to attach instance")

    subnet = rng.choice(subnets)
    idx = len([r for r in resources if r.resource_type is ResourceType.INSTANCE]) + 1
    instance_id = f"i-demo-{idx:04d}"
    node = AWSResource(
        resource_id=instance_id,
        resource_type=ResourceType.INSTANCE,
        configuration={
            "instance_type": "t3.small",
            "availability_zone": subnet.configuration.get("availability_zone"),
        },
        relationships=[{"to": subnet.resource_id, "type": "contained-in"}],
        tags={"Name": f"DemoInstance-{idx}"},
    )
    resources.append(node)
    link = {"source": node.resource_id, "target": subnet.resource_id, "type": "contained-in"}
    return node, link

__all__: list[str] = ["add_instance"]
