"""Translation layer for external skill formats.

Converts PascalCase platform skill definitions into internal
SkillDefinition value objects. Supports two external formats:

- ``SkillMd``: Inline markdown content (no URL fetch needed)
- ``Package``: Zip download from a signed URL
"""

import logging
from typing import Any

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition

logger = logging.getLogger(__name__)


def _is_external_format(raw: dict[str, Any]) -> bool:
    """Return True if the dict uses the external PascalCase format."""
    return "Format" in raw


def _translate_one(raw: dict[str, Any]) -> SkillDefinition | None:
    """Translate a single external skill dict into a SkillDefinition.

    Returns None if the skill should be skipped (inactive or unknown format).
    """
    if not raw.get("IsActive", True):
        logger.debug("Skipping inactive skill '%s'", raw.get("Name", "unknown"))
        return None

    name = raw.get("Name", "")
    version = str(raw.get("Version", "0"))
    fmt = raw.get("Format", "")

    if fmt == "SkillMd":
        content = raw.get("SkillMd", "")
        if not content:
            logger.warning("Skill '%s': SkillMd format but no SkillMd content", name)
            return None
        return SkillDefinition(name=name, version=version, url="", content=content)

    if fmt == "Package":
        url = raw.get("FileStoreSignedUrl", "")
        if not url:
            logger.warning("Skill '%s': Package format but no FileStoreSignedUrl", name)
            return None
        return SkillDefinition(name=name, version=version, url=url)

    logger.warning("Skill '%s': unknown format '%s', skipping", name, fmt)
    return None


def _translate_internal(raw: dict[str, Any]) -> SkillDefinition:
    """Translate the existing internal lowercase format."""
    return SkillDefinition(
        name=raw["name"],
        version=raw["version"],
        url=raw["url"],
    )


def translate_skills(raw_skills: list[dict[str, Any]]) -> list[SkillDefinition]:
    """Translate a mixed list of skill dicts into SkillDefinition objects.

    Handles both the new external PascalCase format and the existing
    internal lowercase format. Detection is based on the presence of
    the ``Format`` key (external) vs lowercase ``name`` key (internal).

    Args:
        raw_skills: List of skill dicts from platform_context["skills"].

    Returns:
        List of SkillDefinition objects (excludes inactive/invalid skills).
    """
    definitions: list[SkillDefinition] = []

    for raw in raw_skills:
        if _is_external_format(raw):
            defn = _translate_one(raw)
            if defn is not None:
                definitions.append(defn)
        else:
            definitions.append(_translate_internal(raw))

    return definitions
