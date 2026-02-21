# dcaf/core/services/skill_manager.py
import logging
import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import boto3
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
            storage_path or os.environ.get(EnvVars.PERSISTENT_VOLUME_STORAGE) or DEFAULT_STORAGE_PATH
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

    def _fetch_from_s3(self, skill: SkillDefinition) -> bytes | None:
        """Download skill zip bytes directly from S3.

        The skill URL is expected to be an ``s3://bucket/prefix`` URI
        (optionally with ``?region=...``).  We list objects under the
        prefix to find a ``.zip`` file and download it.

        Args:
            skill: The skill definition with an ``s3://`` URL.

        Returns:
            Raw zip bytes, or None on failure.
        """
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(skill.url)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
        region = parse_qs(parsed.query).get("region", ["us-east-1"])[0]

        try:
            s3 = boto3.client("s3", region_name=region)

            # List objects under the prefix to find the zip file
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
            contents = response.get("Contents", [])

            zip_keys = [obj["Key"] for obj in contents if obj["Key"].endswith(".zip")]
            if not zip_keys:
                logger.error(
                    "Skill '%s' v%s: no .zip file found at s3://%s/%s",
                    skill.name,
                    skill.version,
                    bucket,
                    prefix,
                )
                return None

            key = zip_keys[0]
            logger.info(
                "Skill '%s' v%s: downloading s3://%s/%s",
                skill.name,
                skill.version,
                bucket,
                key,
            )

            obj = s3.get_object(Bucket=bucket, Key=key)
            content = obj["Body"].read()

            if len(content) > MAX_SKILL_SIZE:
                logger.error(
                    "Skill '%s' v%s: S3 download too large (%d bytes, max %d)",
                    skill.name,
                    skill.version,
                    len(content),
                    MAX_SKILL_SIZE,
                )
                return None

            logger.info(
                "Skill '%s' v%s: fetched %d bytes from S3",
                skill.name,
                skill.version,
                len(content),
            )
            return content

        except Exception:
            logger.error(
                "Failed to fetch skill '%s' v%s from S3 (%s)",
                skill.name,
                skill.version,
                skill.url,
                exc_info=True,
            )
            return None

    async def fetch_and_cache(self, skill: SkillDefinition) -> str | None:
        """
        Fetch a skill from its URL and cache it locally.

        Routes to the S3 SDK when the URL scheme is ``s3://``, otherwise
        uses HTTP. Uses atomic rename for concurrent safety.

        Args:
            skill: The skill definition with name, version, and URL.

        Returns:
            The local path to the cached skill directory, or None on failure.
        """
        target_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version

        parsed_scheme = skill.url.split("://")[0] if "://" in skill.url else "http"

        if parsed_scheme == "s3":
            raw_bytes = self._fetch_from_s3(skill)
            if raw_bytes is None:
                return None
            content_bytes = raw_bytes
            fmt = "zip"
        else:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
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

        temp_dir = Path(tempfile.mkdtemp(prefix=f"skill_{skill.name}_"))

        try:
            if fmt == "zip":
                result = self._extract_zip(content_bytes, temp_dir, skill)
                if result is None:
                    return None
            else:
                (temp_dir / SKILL_FILENAME).write_bytes(content_bytes)

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
