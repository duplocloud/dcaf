# dcaf/core/services/skill_manager.py
import logging
import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_PATH = "/data"
SKILLS_DIR = "skills"
SKILL_FILENAME = "SKILL.md"
MAX_SKILL_SIZE = 50 * 1024 * 1024  # 50 MB


class SkillManager:
    """
    Manages skill fetching, caching, and local path resolution.

    Skills are stored at: {storage_path}/skills/{name}/{version}/SKILL.md

    The storage path is determined by:
    1. Explicit `storage_path` constructor argument
    2. PERSISTENT_VOLUME_STORAGE environment variable
    3. Default: /data
    """

    def __init__(self, storage_path: str | None = None) -> None:
        self.storage_path = (
            storage_path or os.environ.get("PERSISTENT_VOLUME_STORAGE") or DEFAULT_STORAGE_PATH
        )

    def get_local_skill_path(self, skill: SkillDefinition) -> str | None:
        """
        Check if a skill exists in local cache.

        Args:
            skill: The skill definition to look up.

        Returns:
            The local path to the skill directory if found and valid,
            None otherwise.
        """
        skill_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version
        skill_file = skill_dir / SKILL_FILENAME

        if skill_file.is_file():
            logger.debug(
                "Skill '%s' v%s found locally at %s",
                skill.name,
                skill.version,
                skill_dir,
            )
            return str(skill_dir)

        logger.debug(
            "Skill '%s' v%s not found locally",
            skill.name,
            skill.version,
        )
        return None

    def _detect_format(self, url: str, content_type: str) -> str:
        """
        Detect whether the skill is a zip or text/markdown.

        Order of operations:
        1. Check file extension in URL
        2. Fall back to Content-Type header

        Args:
            url: The skill URL.
            content_type: The Content-Type header value.

        Returns:
            "zip" or "text"
        """
        parsed = urlparse(url)
        path = parsed.path.lower()
        if path.endswith(".zip"):
            return "zip"
        if path.endswith((".md", ".txt", ".markdown")):
            return "text"

        ct = content_type.lower()
        if "zip" in ct:
            return "zip"

        return "text"

    async def fetch_and_cache(self, skill: SkillDefinition) -> str | None:
        """
        Fetch a skill from its URL and cache it locally.

        Uses atomic rename for concurrent safety. If the target directory
        already exists when we try to rename, the existing version is trusted.

        Args:
            skill: The skill definition with name, version, and URL.

        Returns:
            The local path to the cached skill directory, or None on failure.
        """
        target_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(skill.url)
                response.raise_for_status()
                if len(response.content) > MAX_SKILL_SIZE:
                    logger.error(
                        "Skill '%s' v%s: download too large (%d bytes, max %d)",
                        skill.name, skill.version, len(response.content), MAX_SKILL_SIZE,
                    )
                    return None
        except Exception:
            logger.error(
                "Failed to fetch skill '%s' v%s from %s",
                skill.name,
                skill.version,
                skill.url,
                exc_info=True,
            )
            return None

        content_type = response.headers.get("content-type", "")
        fmt = self._detect_format(skill.url, content_type)

        temp_dir = Path(tempfile.mkdtemp(prefix=f"skill_{skill.name}_"))

        try:
            if fmt == "zip":
                result = self._extract_zip(response.content, temp_dir, skill)
                if result is None:
                    return None
            else:
                (temp_dir / SKILL_FILENAME).write_text(response.text)

            target_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                temp_dir.rename(target_dir)
                logger.info(
                    "Cached skill '%s' v%s at %s",
                    skill.name,
                    skill.version,
                    target_dir,
                )
            except OSError:
                logger.debug(
                    "Skill '%s' v%s already cached by another process, using existing",
                    skill.name,
                    skill.version,
                )
                shutil.rmtree(temp_dir, ignore_errors=True)

            return str(target_dir)

        except Exception:
            logger.error(
                "Failed to cache skill '%s' v%s",
                skill.name,
                skill.version,
                exc_info=True,
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def _extract_zip(self, content: bytes, target: Path, skill: SkillDefinition) -> str | None:
        """
        Extract zip contents to target directory and validate SKILL.md exists.

        Args:
            content: The raw zip bytes.
            target: The directory to extract into.
            skill: The skill definition (for logging).

        Returns:
            The target path string, or None if SKILL.md is missing.
        """
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                for member in zf.namelist():
                    member_path = (target / member).resolve()
                    if not str(member_path).startswith(str(target.resolve())):
                        logger.error(
                            "Skill '%s' v%s: zip contains unsafe path: %s",
                            skill.name, skill.version, member,
                        )
                        shutil.rmtree(target, ignore_errors=True)
                        return None
                zf.extractall(target)
        except zipfile.BadZipFile:
            logger.error(
                "Skill '%s' v%s: invalid zip file from %s",
                skill.name,
                skill.version,
                skill.url,
            )
            shutil.rmtree(target, ignore_errors=True)
            return None

        if not (target / SKILL_FILENAME).is_file():
            logger.error(
                "Skill '%s' v%s: expected SKILL.md file missing at folder root",
                skill.name,
                skill.version,
            )
            shutil.rmtree(target, ignore_errors=True)
            return None

        return str(target)
