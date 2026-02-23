from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDefinition:
    """
    Immutable value object representing a skill to load.

    Received via platform context. Contains the information
    needed to fetch, cache, and load a skill into the agent.

    Attributes:
        name: Unique identifier for the skill
        version: Exact version string for cache lookup
        url: URL to fetch the skill from if not cached locally
        content: Inline skill markdown content (skip URL fetch when set)
    """

    name: str
    version: str
    url: str
    content: str | None = None
