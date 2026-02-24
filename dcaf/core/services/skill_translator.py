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


def _translate_package(raw: dict[str, Any], name: str, version: str) -> SkillDefinition | None:
    """Translate a Package-format skill dict into a SkillDefinition.

    When ``PackagePath`` is ``"s3"``, the skill is fetched from S3 using
    ``StorageBucketName`` and ``SkillFolder``.  Otherwise the signed URL
    in ``FileStoreSignedUrl`` is used for an HTTP download.
    """
    if raw.get("PackagePath") == "s3":
        bucket = raw.get("StorageBucketName", "")
        folder = raw.get("SkillFolder", "").lstrip("/")
        if not bucket:
            logger.warning("Skill '%s': Package/S3 but no StorageBucketName", name)
            return None
        if not folder:
            logger.warning("Skill '%s': Package/S3 but no SkillFolder", name)
            return None
        s3_path = f"s3://{bucket}/{folder}"
        return SkillDefinition(name=name, version=version, url="", s3_path=s3_path)

    raw_url = raw.get("FileStoreSignedUrl", "")
    if not raw_url:
        logger.warning("Skill '%s': Package format but no FileStoreSignedUrl", name)
        return None

    return SkillDefinition(name=name, version=version, url=raw_url)


def _translate_s3(raw: dict[str, Any], name: str, version: str) -> SkillDefinition | None:
    """Translate an S3-format skill dict into a SkillDefinition."""
    s3_path = raw.get("S3Path", "")
    if not s3_path:
        logger.warning("Skill '%s': S3 format but no S3Path", name)
        return None

    return SkillDefinition(name=name, version=version, url="", s3_path=s3_path)


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
        return _translate_package(raw, name, version)

    if fmt == "S3":
        return _translate_s3(raw, name, version)

    logger.warning("Skill '%s': unknown format '%s', skipping", name, fmt)
    return None


def _translate_internal(raw: dict[str, Any]) -> SkillDefinition:
    """Translate the existing internal lowercase format."""
    return SkillDefinition(
        name=raw["name"],
        version=raw["version"],
        url=raw.get("url", ""),
        s3_path=raw.get("s3_path"),
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
