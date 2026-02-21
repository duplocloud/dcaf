"""Translation layer for external skill formats.

Converts PascalCase platform skill definitions into internal
SkillDefinition value objects. Supports two external formats:

- ``SkillMd``: Inline markdown content (no URL fetch needed)
- ``Package``: Zip download — either from S3 directly (PackagePath="s3")
  or via HTTP (any other PackagePath value)
"""

import logging
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition

logger = logging.getLogger(__name__)


def _is_external_format(raw: dict[str, Any]) -> bool:
    """Return True if the dict uses the external PascalCase format."""
    return "Format" in raw


def _parse_s3_uri_from_federation_url(federation_url: str) -> str | None:
    """Extract an s3:// URI from an AWS federation/console URL.

    The federation URL embeds the S3 console URL in its ``Destination``
    query parameter, e.g.:
        Destination=https://s3.console.aws.amazon.com/s3/buckets/my-bucket
                    ?region=us-west-2&prefix=skills/my-skill

    Returns an ``s3://bucket/prefix?region=us-west-2`` URI, or None if
    the URL cannot be parsed.
    """
    try:
        parsed = urlparse(federation_url)
        params = parse_qs(parsed.query)
        destinations = params.get("Destination", [])
        if not destinations:
            return None

        destination = unquote(destinations[0])
        dest_parsed = urlparse(destination)

        # Expect path like /s3/buckets/{bucket}
        path_parts = dest_parsed.path.strip("/").split("/")
        if len(path_parts) < 3 or path_parts[0] != "s3" or path_parts[1] != "buckets":
            return None

        bucket = path_parts[2]
        dest_params = parse_qs(dest_parsed.query)
        prefix = dest_params.get("prefix", [""])[0]
        region = dest_params.get("region", ["us-east-1"])[0]

        s3_uri = f"s3://{bucket}/{prefix}"
        if region:
            s3_uri += f"?region={region}"

        return s3_uri

    except Exception:
        logger.debug("Failed to parse S3 URI from federation URL", exc_info=True)
        return None


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
        raw_url = raw.get("FileStoreSignedUrl", "")
        if not raw_url:
            logger.warning("Skill '%s': Package format but no FileStoreSignedUrl", name)
            return None

        package_path = raw.get("PackagePath", "")
        if package_path == "s3":
            s3_uri = _parse_s3_uri_from_federation_url(raw_url)
            if not s3_uri:
                logger.warning(
                    "Skill '%s': PackagePath=s3 but could not parse S3 URI from URL", name
                )
                return None
            logger.debug("Skill '%s': resolved S3 URI: %s", name, s3_uri)
            return SkillDefinition(name=name, version=version, url=s3_uri)

        return SkillDefinition(name=name, version=version, url=raw_url)

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
