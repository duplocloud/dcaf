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
from agno.skills import LocalSkills, Skills
from agno.skills.loaders.base import SkillLoader

from dcaf.core.config import EnvVars
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
            storage_path
            or os.environ.get(EnvVars.PERSISTENT_VOLUME_STORAGE)
            or DEFAULT_STORAGE_PATH
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

        The temp directory is created under ``target_dir.parent`` (not in
        ``/tmp``) so that the rename stays within a single filesystem.
        Cross-device renames (``EXDEV``) are a common failure mode in
        Kubernetes where ``/tmp`` and the persistent volume are on separate
        filesystems.

        Args:
            skill: The skill definition with name, version, and URL.

        Returns:
            The local path to the cached skill directory, or None on failure.
        """
        target_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(skill.url)
                response.raise_for_status()
                if len(response.content) > MAX_SKILL_SIZE:
                    logger.error(
                        "Skill '%s' v%s: download too large (%d bytes, max %d)",
                        skill.name,
                        skill.version,
                        len(response.content),
                        MAX_SKILL_SIZE,
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

        logger.info(
            "Fetched skill '%s' v%s from %s (%d bytes)",
            skill.name,
            skill.version,
            skill.url,
            len(response.content),
        )
        content_bytes = response.content
        content_type = response.headers.get("content-type", "")
        fmt = self._detect_format(skill.url, content_type)

        # Create the parent directory first so the temp dir lives on the
        # same filesystem as the target — required for atomic rename.
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(dir=target_dir.parent, prefix=f"skill_{skill.name}_"))

        try:
            if fmt == "zip":
                result = self._extract_zip(content_bytes, temp_dir, skill)
                if result is None:
                    return None
            else:
                (temp_dir / SKILL_FILENAME).write_bytes(content_bytes)

            try:
                temp_dir.rename(target_dir)
                logger.info(
                    "Cached skill '%s' v%s at %s",
                    skill.name,
                    skill.version,
                    target_dir,
                )
            except OSError:
                logger.info(
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

    async def fetch_and_cache_from_s3(self, skill: SkillDefinition) -> str | None:
        """
        Recursively download a skill from S3 and cache it locally.

        Uses the default AWS credential chain (IAM role) to authenticate.
        Downloads all objects under the S3 prefix, preserving the directory
        structure relative to the prefix root.

        Uses atomic rename for concurrent safety. The temp directory is
        created on the same filesystem as the target to avoid EXDEV errors
        in Kubernetes environments.

        Args:
            skill: Skill definition with ``s3_path`` set (e.g. ``s3://bucket/prefix``).

        Returns:
            The local path to the cached skill directory, or None on failure.
        """
        import aioboto3

        s3_uri = skill.s3_path or ""
        parsed = urlparse(s3_uri)
        if parsed.scheme != "s3" or not parsed.netloc:
            logger.error(
                "Skill '%s' v%s: invalid S3 URI '%s'",
                skill.name,
                skill.version,
                s3_uri,
            )
            return None

        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")

        target_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(dir=target_dir.parent, prefix=f"skill_{skill.name}_"))

        try:
            session = aioboto3.Session()
            async with session.client("s3") as s3:
                paginator = s3.get_paginator("list_objects_v2")
                total = 0
                async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        rel_path = key[len(prefix) :].lstrip("/")
                        if not rel_path:
                            # Key is the prefix itself (directory marker) — skip
                            continue

                        # Path traversal guard
                        dest_path = (temp_dir / rel_path).resolve()
                        if not str(dest_path).startswith(str(temp_dir.resolve())):
                            logger.error(
                                "Skill '%s' v%s: S3 key contains unsafe path: %s",
                                skill.name,
                                skill.version,
                                key,
                            )
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            return None

                        dest_path.parent.mkdir(parents=True, exist_ok=True)
                        response = await s3.get_object(Bucket=bucket, Key=key)
                        body = await response["Body"].read()
                        dest_path.write_bytes(body)
                        total += 1

            if total == 0:
                logger.error(
                    "Skill '%s' v%s: no objects found at %s",
                    skill.name,
                    skill.version,
                    s3_uri,
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            if not (temp_dir / SKILL_FILENAME).is_file():
                logger.error(
                    "Skill '%s' v%s: SKILL.md not found at S3 prefix root",
                    skill.name,
                    skill.version,
                )
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None

            logger.info(
                "Downloaded %d object(s) for skill '%s' v%s from %s",
                total,
                skill.name,
                skill.version,
                s3_uri,
            )

            try:
                temp_dir.rename(target_dir)
                logger.info(
                    "Cached skill '%s' v%s at %s",
                    skill.name,
                    skill.version,
                    target_dir,
                )
            except OSError:
                logger.info(
                    "Skill '%s' v%s already cached by another process, using existing",
                    skill.name,
                    skill.version,
                )
                shutil.rmtree(temp_dir, ignore_errors=True)

            return str(target_dir)

        except Exception:
            logger.error(
                "Failed to fetch skill '%s' v%s from %s",
                skill.name,
                skill.version,
                s3_uri,
                exc_info=True,
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def _extract_zip(self, content: bytes, target: Path, skill: SkillDefinition) -> str | None:
        """
        Extract zip contents to target directory and validate SKILL.md exists.

        If SKILL.md is not at the zip root but exists exactly one directory
        level deep, the contents of that subdirectory are elevated to the
        root.  This handles zips created by tools (e.g. macOS Finder) that
        wrap files in a top-level folder.  ``__MACOSX`` metadata directories
        are removed during elevation.

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
                            skill.name,
                            skill.version,
                            member,
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

        if (target / SKILL_FILENAME).is_file():
            return str(target)

        # SKILL.md not at root — look one level deep and elevate if found.
        elevated = self._elevate_skill_root(target, skill)
        if elevated:
            return str(target)

        logger.error(
            "Skill '%s' v%s: SKILL.md not found at root or one level deep",
            skill.name,
            skill.version,
        )
        shutil.rmtree(target, ignore_errors=True)
        return None

    def _elevate_skill_root(self, target: Path, skill: SkillDefinition) -> bool:
        """
        Find SKILL.md one directory level deep and elevate that folder to root.

        Searches immediate subdirectories of *target* for a ``SKILL.md`` file.
        If exactly one is found, its parent directory's contents are moved to
        *target* and any ``__MACOSX`` metadata directories are removed.

        Args:
            target: The extraction root directory.
            skill: The skill definition (for logging).

        Returns:
            True if elevation succeeded, False otherwise.
        """
        candidates = [
            d
            for d in target.iterdir()
            if d.is_dir() and d.name != "__MACOSX" and (d / SKILL_FILENAME).is_file()
        ]

        if len(candidates) != 1:
            return False

        skill_subdir = candidates[0]
        logger.info(
            "Skill '%s' v%s: SKILL.md found in subdirectory '%s', elevating to root",
            skill.name,
            skill.version,
            skill_subdir.name,
        )

        # Move all files from the subdirectory to root
        for item in list(skill_subdir.iterdir()):
            dest = target / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            item.rename(dest)

        # Clean up the now-empty subdirectory and __MACOSX junk
        skill_subdir.rmdir()
        macosx_dir = target / "__MACOSX"
        if macosx_dir.exists():
            shutil.rmtree(macosx_dir)

        return True

    def cache_inline(self, skill: SkillDefinition) -> str | None:
        """Write inline skill content directly to the local cache.

        Always overwrites existing content to avoid serving stale
        inline markdown when the platform sends updated content.

        Args:
            skill: Skill definition with ``content`` set.

        Returns:
            The local path to the cached skill directory, or None on failure.
        """
        target_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version

        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / SKILL_FILENAME).write_text(skill.content or "")
            logger.info(
                "Cached inline skill '%s' v%s at %s",
                skill.name,
                skill.version,
                target_dir,
            )
            return str(target_dir)
        except Exception:
            logger.error(
                "Failed to cache inline skill '%s' v%s",
                skill.name,
                skill.version,
                exc_info=True,
            )
            return None

    async def resolve_skills(self, definitions: list[SkillDefinition]) -> Skills | None:
        """
        Resolve a list of skill definitions into an Agno Skills object.

        For each skill:
        1. Check local cache
        2. If not cached, fetch and cache from URL
        3. If fetch fails, skip and log error

        Args:
            definitions: List of skill definitions from platform context.

        Returns:
            An Agno Skills object with LocalSkills loaders, or None if
            no skills were resolved.
        """
        if not definitions:
            return None

        logger.info(
            "Resolving %d skill(s): %s",
            len(definitions),
            ", ".join(f"'{s.name}' v{s.version}" for s in definitions),
        )

        loaders: list[SkillLoader] = []

        for skill in definitions:
            logger.info("Resolving skill '%s' v%s ...", skill.name, skill.version)

            # Inline content: write directly (always overwrite for freshness)
            if skill.content is not None:
                path = self.cache_inline(skill)
            else:
                path = self.get_local_skill_path(skill)

                if path is not None:
                    logger.info(
                        "Skill '%s' v%s resolved from local cache at %s",
                        skill.name,
                        skill.version,
                        path,
                    )
                elif skill.s3_path:
                    logger.info(
                        "Skill '%s' v%s not in local cache, fetching from S3 path %s",
                        skill.name,
                        skill.version,
                        skill.s3_path,
                    )
                    path = await self.fetch_and_cache_from_s3(skill)
                else:
                    logger.info(
                        "Skill '%s' v%s not in local cache, fetching from %s",
                        skill.name,
                        skill.version,
                        skill.url,
                    )
                    path = await self.fetch_and_cache(skill)

            if path is None:
                logger.error(
                    "Skipping skill '%s' v%s: could not resolve",
                    skill.name,
                    skill.version,
                )
                continue

            loaders.append(LocalSkills(path, validate=False))
            logger.info("Loaded skill '%s' v%s from %s", skill.name, skill.version, path)

        if not loaders:
            logger.warning("No skills could be resolved")
            return None

        return Skills(loaders=loaders)
