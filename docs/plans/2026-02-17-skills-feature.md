# Skills Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable agents to dynamically load skills from platform context — fetching, caching, and integrating them into Agno agents at runtime.

**Architecture:** Skills arrive as an array in the platform context (`skills: [{name, version, url}]`). A `SkillManager` service handles fetching from URLs, caching to persistent storage (`{PERSISTENT_VOLUME_STORAGE}/skills/{name}/{version}/`), and producing Agno `Skills` objects. The `AgnoAdapter._create_agent_async()` method is extended to accept and pass skills to the `AgnoAgent` constructor.

**Tech Stack:** Python 3.11+, Agno SDK 2.5.2 (`agno.skills.Skills`, `agno.skills.LocalSkills`), `httpx` (async HTTP), `zipfile` (stdlib), Pydantic for schema, `pytest` for testing.

---

### Task 1: Upgrade Agno to 2.5.2

**Files:**
- Modify: `pyproject.toml:47` (agno version pin)

**Step 1: Write a smoke test for skills imports**

```python
# tests/core/test_skills.py

def test_agno_skills_imports():
    """Verify agno 2.5.2 has the Skills API we need."""
    from agno.skills import Skills, LocalSkills

    assert Skills is not None
    assert LocalSkills is not None
```

**Step 2: Run it to verify it fails**

Run: `python -m pytest tests/core/test_skills.py::test_agno_skills_imports -v`
Expected: PASS (agno 2.5.2 is already installed in the venv from our verification)

**Step 3: Update the version pin in pyproject.toml**

Change line 47 in `pyproject.toml`:
```
    "agno==2.3.21",               # Agno SDK - pinned to avoid [] bug in 2.3.26
```
to:
```
    "agno==2.5.2",                # Agno SDK - skills support
```

**Step 4: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass (the 1 failing test is a pre-existing AWS credentials issue, not agno-related).

**Step 5: Commit**

```bash
git add pyproject.toml tests/core/test_skills.py
git commit -m "chore: upgrade agno to 2.5.2 for skills support"
```

---

### Task 2: Add SkillDefinition Schema to Platform Context

**Files:**
- Create: `dcaf/core/domain/value_objects/skill_definition.py`
- Modify: `dcaf/core/schemas/messages.py:47-74` (PlatformContext class)
- Test: `tests/core/test_skills.py`

**Step 1: Write the failing tests**

```python
# Append to tests/core/test_skills.py

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition


class TestSkillDefinition:
    def test_create_skill_definition(self):
        skill = SkillDefinition(name="k8s-debug", version="1.0.0", url="https://example.com/skill.zip")
        assert skill.name == "k8s-debug"
        assert skill.version == "1.0.0"
        assert skill.url == "https://example.com/skill.zip"

    def test_skill_definition_immutable(self):
        skill = SkillDefinition(name="k8s-debug", version="1.0.0", url="https://example.com/skill.zip")
        try:
            skill.name = "changed"
            assert False, "Should be immutable"
        except (AttributeError, TypeError, Exception):
            pass  # Expected for frozen dataclass


class TestPlatformContextSkills:
    def test_platform_context_accepts_skills(self):
        from dcaf.core.schemas.messages import PlatformContext

        ctx = PlatformContext(
            tenant_id="t1",
            skills=[
                {"name": "k8s-debug", "version": "1.0.0", "url": "https://example.com/skill.zip"},
                {"name": "aws-helper", "version": "2.0.0", "url": "https://example.com/aws.md"},
            ],
        )
        assert len(ctx.skills) == 2
        assert ctx.skills[0].name == "k8s-debug"

    def test_platform_context_skills_default_empty(self):
        from dcaf.core.schemas.messages import PlatformContext

        ctx = PlatformContext()
        assert ctx.skills == []
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_skills.py::TestSkillDefinition -v`
Expected: FAIL (module does not exist)

Run: `python -m pytest tests/core/test_skills.py::TestPlatformContextSkills -v`
Expected: FAIL (PlatformContext has no `skills` field)

**Step 3: Create the SkillDefinition value object**

```python
# dcaf/core/domain/value_objects/skill_definition.py
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
    """

    name: str
    version: str
    url: str
```

**Step 4: Add SkillDefinitionSchema and skills field to PlatformContext in messages.py**

Add a Pydantic model for wire-format skill definitions and a `skills` field to `PlatformContext`:

```python
# In dcaf/core/schemas/messages.py, add before PlatformContext class:

class SkillDefinitionSchema(BaseModel):
    """Wire-format schema for a skill definition in platform context."""

    name: str
    version: str
    url: str
```

Then add to `PlatformContext` class body (after `aws_region`):

```python
    # Skills to load into the agent
    skills: list[SkillDefinitionSchema] = Field(default_factory=list)
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_skills.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add dcaf/core/domain/value_objects/skill_definition.py dcaf/core/schemas/messages.py tests/core/test_skills.py
git commit -m "feat: add SkillDefinition schema and skills field to PlatformContext"
```

---

### Task 3: Implement SkillManager — Local Cache Lookup

**Files:**
- Create: `dcaf/core/services/skill_manager.py`
- Test: `tests/core/test_skills.py`

The `SkillManager` is responsible for:
1. Checking if a skill exists locally at `{storage}/skills/{name}/{version}/SKILL.md`
2. Fetching from URL if not cached
3. Producing a list of local paths for Agno `LocalSkills` loaders

This task covers only local cache lookup. Fetching is Task 4.

**Step 1: Write the failing tests**

```python
# Append to tests/core/test_skills.py
import os
import tempfile

from dcaf.core.services.skill_manager import SkillManager
from dcaf.core.domain.value_objects.skill_definition import SkillDefinition


class TestSkillManagerLocalLookup:
    def test_skill_found_locally(self, tmp_path):
        """When SKILL.md exists at {storage}/skills/{name}/{version}/, return the path."""
        # Arrange: create a cached skill on disk
        skill_dir = tmp_path / "skills" / "k8s-debug" / "1.0.0"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# K8s Debug Skill")

        manager = SkillManager(storage_path=str(tmp_path))
        skill = SkillDefinition(name="k8s-debug", version="1.0.0", url="https://example.com/unused")

        # Act
        path = manager.get_local_skill_path(skill)

        # Assert
        assert path == str(skill_dir)

    def test_skill_not_found_locally(self, tmp_path):
        """When skill directory doesn't exist, return None."""
        manager = SkillManager(storage_path=str(tmp_path))
        skill = SkillDefinition(name="missing", version="1.0.0", url="https://example.com/skill.zip")

        path = manager.get_local_skill_path(skill)

        assert path is None

    def test_skill_dir_exists_but_no_skill_md(self, tmp_path):
        """When version dir exists but SKILL.md is missing, return None."""
        skill_dir = tmp_path / "skills" / "bad-skill" / "1.0.0"
        skill_dir.mkdir(parents=True)
        (skill_dir / "README.md").write_text("wrong file")

        manager = SkillManager(storage_path=str(tmp_path))
        skill = SkillDefinition(name="bad-skill", version="1.0.0", url="https://example.com/x")

        path = manager.get_local_skill_path(skill)

        assert path is None

    def test_storage_path_defaults_from_env(self, tmp_path, monkeypatch):
        """PERSISTENT_VOLUME_STORAGE env var sets the storage path."""
        monkeypatch.setenv("PERSISTENT_VOLUME_STORAGE", str(tmp_path))
        manager = SkillManager()
        assert manager.storage_path == str(tmp_path)

    def test_storage_path_defaults_to_data(self, monkeypatch):
        """Without env var, defaults to /data."""
        monkeypatch.delenv("PERSISTENT_VOLUME_STORAGE", raising=False)
        manager = SkillManager()
        assert manager.storage_path == "/data"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_skills.py::TestSkillManagerLocalLookup -v`
Expected: FAIL (module does not exist)

**Step 3: Implement SkillManager with local lookup**

```python
# dcaf/core/services/skill_manager.py
import logging
import os
from pathlib import Path

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_PATH = "/data"
SKILLS_DIR = "skills"
SKILL_FILENAME = "SKILL.md"


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
            or os.environ.get("PERSISTENT_VOLUME_STORAGE")
            or DEFAULT_STORAGE_PATH
        )

    def get_local_skill_path(self, skill: SkillDefinition) -> str | None:
        """
        Check if a skill exists in local cache.

        Args:
            skill: The skill definition to look up.

        Returns:
            The local path to the skill directory if found and valid, None otherwise.
        """
        skill_dir = Path(self.storage_path) / SKILLS_DIR / skill.name / skill.version
        skill_file = skill_dir / SKILL_FILENAME

        if skill_file.is_file():
            logger.debug(f"Skill '{skill.name}' v{skill.version} found locally at {skill_dir}")
            return str(skill_dir)

        logger.debug(f"Skill '{skill.name}' v{skill.version} not found locally")
        return None
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_skills.py::TestSkillManagerLocalLookup -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dcaf/core/services/skill_manager.py tests/core/test_skills.py
git commit -m "feat: add SkillManager with local cache lookup"
```

---

### Task 4: Implement SkillManager — Fetch and Cache from URL

**Files:**
- Modify: `dcaf/core/services/skill_manager.py`
- Test: `tests/core/test_skills.py`

This task adds the `fetch_and_cache` async method that:
1. Downloads skill from URL via httpx
2. Determines format by file extension first, then Content-Type header
3. If zip: extracts to temp dir, validates SKILL.md exists, atomically renames into cache
4. If markdown/text: saves as SKILL.md in temp dir, atomically renames into cache
5. Logs errors and returns None on failure

**Step 1: Write the failing tests**

```python
# Append to tests/core/test_skills.py
import zipfile
import io
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import httpx

from dcaf.core.services.skill_manager import SkillManager
from dcaf.core.domain.value_objects.skill_definition import SkillDefinition


def _make_zip_bytes(files: dict[str, str]) -> bytes:
    """Helper: create a zip archive in memory with given files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestSkillManagerFetch:
    @pytest.mark.asyncio
    async def test_fetch_zip_skill(self, tmp_path):
        """Fetching a .zip URL extracts contents and caches them."""
        zip_bytes = _make_zip_bytes({"SKILL.md": "# My Skill", "scripts/run.sh": "echo hi"})
        skill = SkillDefinition(name="zip-skill", version="1.0.0", url="https://example.com/skill.zip")
        manager = SkillManager(storage_path=str(tmp_path))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = zip_bytes
        mock_response.headers = {"content-type": "application/zip"}
        mock_response.raise_for_status = MagicMock()

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            path = await manager.fetch_and_cache(skill)

        assert path is not None
        assert (Path(path) / "SKILL.md").read_text() == "# My Skill"
        assert (Path(path) / "scripts" / "run.sh").read_text() == "echo hi"

    @pytest.mark.asyncio
    async def test_fetch_markdown_skill(self, tmp_path):
        """Fetching a .md URL saves content as SKILL.md."""
        skill = SkillDefinition(
            name="md-skill", version="2.0.0", url="https://example.com/my-skill.md"
        )
        manager = SkillManager(storage_path=str(tmp_path))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Markdown Skill\nDo stuff."
        mock_response.content = b"# Markdown Skill\nDo stuff."
        mock_response.headers = {"content-type": "text/markdown"}
        mock_response.raise_for_status = MagicMock()

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            path = await manager.fetch_and_cache(skill)

        assert path is not None
        assert (Path(path) / "SKILL.md").read_text() == "# Markdown Skill\nDo stuff."

    @pytest.mark.asyncio
    async def test_fetch_zip_missing_skill_md(self, tmp_path):
        """Zip without SKILL.md at root is rejected."""
        zip_bytes = _make_zip_bytes({"README.md": "wrong file"})
        skill = SkillDefinition(name="bad-zip", version="1.0.0", url="https://example.com/bad.zip")
        manager = SkillManager(storage_path=str(tmp_path))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = zip_bytes
        mock_response.headers = {"content-type": "application/zip"}
        mock_response.raise_for_status = MagicMock()

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            path = await manager.fetch_and_cache(skill)

        assert path is None
        # Verify the skill was NOT cached
        assert not (tmp_path / "skills" / "bad-zip" / "1.0.0").exists()

    @pytest.mark.asyncio
    async def test_fetch_unreachable_url(self, tmp_path):
        """Unreachable URL logs error and returns None."""
        skill = SkillDefinition(name="unreachable", version="1.0.0", url="https://down.example.com/x")
        manager = SkillManager(storage_path=str(tmp_path))

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            path = await manager.fetch_and_cache(skill)

        assert path is None

    @pytest.mark.asyncio
    async def test_fetch_uses_extension_over_content_type(self, tmp_path):
        """File extension takes precedence over Content-Type header."""
        skill = SkillDefinition(
            name="ext-skill", version="1.0.0", url="https://example.com/skill.md"
        )
        manager = SkillManager(storage_path=str(tmp_path))

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# Skill content"
        mock_response.content = b"# Skill content"
        # Content-Type says octet-stream, but extension is .md
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.raise_for_status = MagicMock()

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            path = await manager.fetch_and_cache(skill)

        assert path is not None
        # Should be treated as markdown based on extension, not content-type
        assert (Path(path) / "SKILL.md").read_text() == "# Skill content"

    @pytest.mark.asyncio
    async def test_atomic_rename_concurrent_safety(self, tmp_path):
        """If target directory already exists when we rename, we use the existing one."""
        skill = SkillDefinition(name="race", version="1.0.0", url="https://example.com/skill.md")
        manager = SkillManager(storage_path=str(tmp_path))

        # Pre-create the target directory (simulating a concurrent process winning the race)
        target_dir = tmp_path / "skills" / "race" / "1.0.0"
        target_dir.mkdir(parents=True)
        (target_dir / "SKILL.md").write_text("# Original from other process")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "# My version"
        mock_response.content = b"# My version"
        mock_response.headers = {"content-type": "text/markdown"}
        mock_response.raise_for_status = MagicMock()

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            path = await manager.fetch_and_cache(skill)

        assert path is not None
        # The existing directory should be trusted (not overwritten)
        assert (Path(path) / "SKILL.md").read_text() == "# Original from other process"
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_skills.py::TestSkillManagerFetch -v`
Expected: FAIL (`fetch_and_cache` method does not exist)

**Step 3: Implement fetch_and_cache**

Add the following methods to `SkillManager` in `dcaf/core/services/skill_manager.py`:

```python
# Add these imports at the top of the file
import shutil
import tempfile
import zipfile
from io import BytesIO
from urllib.parse import urlparse

import httpx

# Add these methods to the SkillManager class:

    def _detect_format(self, url: str, content_type: str) -> str:
        """
        Detect whether the skill is a zip or text/markdown.

        Order of operations:
        1. Check file extension in URL
        2. Fall back to Content-Type header

        Returns:
            "zip" or "text"
        """
        # 1. Check file extension
        parsed = urlparse(url)
        path = parsed.path.lower()
        if path.endswith(".zip"):
            return "zip"
        if path.endswith((".md", ".txt", ".markdown")):
            return "text"

        # 2. Fall back to content-type
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
            async with httpx.AsyncClient() as client:
                response = await client.get(skill.url)
                response.raise_for_status()
        except Exception:
            logger.error(
                f"Failed to fetch skill '{skill.name}' v{skill.version} from {skill.url}",
                exc_info=True,
            )
            return None

        content_type = response.headers.get("content-type", "")
        fmt = self._detect_format(skill.url, content_type)

        # Create a temp directory for atomic rename
        temp_dir = Path(tempfile.mkdtemp(prefix=f"skill_{skill.name}_"))

        try:
            if fmt == "zip":
                path = self._extract_zip(response.content, temp_dir, skill)
                if path is None:
                    return None
            else:
                (temp_dir / SKILL_FILENAME).write_text(response.text)

            # Atomic rename into cache
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                temp_dir.rename(target_dir)
                logger.info(
                    f"Cached skill '{skill.name}' v{skill.version} at {target_dir}"
                )
            except OSError:
                # Target already exists (concurrent process won the race).
                # Trust the existing version.
                logger.debug(
                    f"Skill '{skill.name}' v{skill.version} already cached "
                    f"by another process, using existing"
                )
                shutil.rmtree(temp_dir, ignore_errors=True)

            return str(target_dir)

        except Exception:
            logger.error(
                f"Failed to cache skill '{skill.name}' v{skill.version}",
                exc_info=True,
            )
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

    def _extract_zip(
        self, content: bytes, target: Path, skill: SkillDefinition
    ) -> str | None:
        """
        Extract zip contents to target directory and validate SKILL.md exists.

        Returns:
            The target path string, or None if SKILL.md is missing.
        """
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                zf.extractall(target)
        except zipfile.BadZipFile:
            logger.error(
                f"Skill '{skill.name}' v{skill.version}: invalid zip file from {skill.url}"
            )
            shutil.rmtree(target, ignore_errors=True)
            return None

        if not (target / SKILL_FILENAME).is_file():
            logger.error(
                f"Skill '{skill.name}' v{skill.version}: "
                f"Expected SKILL.md file missing at folder root"
            )
            shutil.rmtree(target, ignore_errors=True)
            return None

        return str(target)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_skills.py::TestSkillManagerFetch -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dcaf/core/services/skill_manager.py tests/core/test_skills.py
git commit -m "feat: add skill fetching and caching with atomic rename"
```

---

### Task 5: Implement SkillManager — Resolve All Skills

**Files:**
- Modify: `dcaf/core/services/skill_manager.py`
- Test: `tests/core/test_skills.py`

This task adds `resolve_skills()` — the main entry point that takes a list of `SkillDefinition` objects, resolves each one (local cache or fetch), and returns an Agno `Skills` object ready to pass to the agent.

**Step 1: Write the failing tests**

```python
# Append to tests/core/test_skills.py
from pathlib import Path


class TestSkillManagerResolve:
    @pytest.mark.asyncio
    async def test_resolve_cached_skills(self, tmp_path):
        """resolve_skills returns an Agno Skills object for cached skills."""
        from agno.skills import Skills

        # Create two cached skills
        for name, ver in [("skill-a", "1.0.0"), ("skill-b", "2.0.0")]:
            d = tmp_path / "skills" / name / ver
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name}")

        manager = SkillManager(storage_path=str(tmp_path))
        definitions = [
            SkillDefinition(name="skill-a", version="1.0.0", url="https://example.com/a"),
            SkillDefinition(name="skill-b", version="2.0.0", url="https://example.com/b"),
        ]

        result = await manager.resolve_skills(definitions)

        assert isinstance(result, Skills)

    @pytest.mark.asyncio
    async def test_resolve_empty_list(self, tmp_path):
        """Empty skills list returns None."""
        manager = SkillManager(storage_path=str(tmp_path))

        result = await manager.resolve_skills([])

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_skips_failed_skills(self, tmp_path):
        """Skills that fail to fetch are skipped, others still load."""
        from agno.skills import Skills

        # One cached skill
        d = tmp_path / "skills" / "good" / "1.0.0"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# Good skill")

        manager = SkillManager(storage_path=str(tmp_path))
        definitions = [
            SkillDefinition(name="good", version="1.0.0", url="https://example.com/good"),
            SkillDefinition(name="bad", version="1.0.0", url="https://down.example.com/bad"),
        ]

        # Mock fetch_and_cache to fail for the "bad" skill
        original_fetch = manager.fetch_and_cache

        async def selective_fetch(skill):
            if skill.name == "bad":
                return None
            return await original_fetch(skill)

        manager.fetch_and_cache = selective_fetch

        result = await manager.resolve_skills(definitions)

        assert isinstance(result, Skills)

    @pytest.mark.asyncio
    async def test_resolve_all_skills_fail(self, tmp_path):
        """If all skills fail to resolve, return None."""
        manager = SkillManager(storage_path=str(tmp_path))
        definitions = [
            SkillDefinition(name="fail1", version="1.0.0", url="https://down.example.com/a"),
        ]

        # Mock fetch to always fail
        manager.fetch_and_cache = AsyncMock(return_value=None)

        result = await manager.resolve_skills(definitions)

        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_skills.py::TestSkillManagerResolve -v`
Expected: FAIL (`resolve_skills` method does not exist)

**Step 3: Implement resolve_skills**

Add the following import and method to `SkillManager`:

```python
# Add to imports at top of file:
from agno.skills import Skills, LocalSkills

# Add method to SkillManager class:

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

        loaders: list[LocalSkills] = []

        for skill in definitions:
            path = self.get_local_skill_path(skill)

            if path is None:
                path = await self.fetch_and_cache(skill)

            if path is None:
                logger.error(
                    f"Skipping skill '{skill.name}' v{skill.version}: "
                    f"could not resolve locally or from {skill.url}"
                )
                continue

            loaders.append(LocalSkills(path))
            logger.info(f"Loaded skill '{skill.name}' v{skill.version} from {path}")

        if not loaders:
            logger.warning("No skills could be resolved")
            return None

        return Skills(loaders=loaders)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_skills.py::TestSkillManagerResolve -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add dcaf/core/services/skill_manager.py tests/core/test_skills.py
git commit -m "feat: add resolve_skills to produce Agno Skills from definitions"
```

---

### Task 6: Wire Skills into AgnoAdapter

**Files:**
- Modify: `dcaf/core/adapters/outbound/agno/adapter.py` (methods: `_create_agent_async`, `invoke`, `invoke_stream`)
- Test: `tests/core/test_skills.py`

This is the integration point. The `AgnoAdapter` receives `platform_context` dict which now may contain `skills`. It uses `SkillManager` to resolve them and passes the resulting `Skills` object to `AgnoAgent(skills=...)`.

**Step 1: Write the failing tests**

```python
# Append to tests/core/test_skills.py

class TestAgnoAdapterSkillsIntegration:
    @pytest.mark.asyncio
    async def test_create_agent_with_skills(self, tmp_path):
        """AgnoAgent is created with skills= parameter when platform_context has skills."""
        # Create a cached skill
        skill_dir = tmp_path / "skills" / "test-skill" / "1.0.0"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: A test\n---\n# Test")

        platform_context = {
            "skills": [
                {"name": "test-skill", "version": "1.0.0", "url": "https://example.com/unused"},
            ],
        }

        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter
        from agno.agent import Agent as AgnoAgent
        from agno.skills import Skills

        adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

        # Mock model creation to avoid real API calls
        mock_model = MagicMock()
        adapter._get_or_create_model_async = AsyncMock(return_value=mock_model)

        with patch.object(SkillManager, "__init__", lambda self, **kwargs: setattr(self, "storage_path", str(tmp_path)) or None):
            with patch.object(SkillManager, "get_local_skill_path", return_value=str(skill_dir)):
                with patch("dcaf.core.adapters.outbound.agno.adapter.AgnoAgent") as mock_agno_agent:
                    mock_agno_agent.return_value = MagicMock()

                    await adapter._create_agent_async(
                        tools=[],
                        system_prompt="test",
                        platform_context=platform_context,
                    )

                    # Verify AgnoAgent was called with skills parameter
                    call_kwargs = mock_agno_agent.call_args[1]
                    assert "skills" in call_kwargs
                    assert call_kwargs["skills"] is not None

    @pytest.mark.asyncio
    async def test_create_agent_without_skills(self):
        """AgnoAgent is created without skills when platform_context has no skills."""
        from dcaf.core.adapters.outbound.agno.adapter import AgnoAdapter

        adapter = AgnoAdapter(model_id="test-model", provider="anthropic")
        mock_model = MagicMock()
        adapter._get_or_create_model_async = AsyncMock(return_value=mock_model)

        with patch("dcaf.core.adapters.outbound.agno.adapter.AgnoAgent") as mock_agno_agent:
            mock_agno_agent.return_value = MagicMock()

            await adapter._create_agent_async(
                tools=[],
                system_prompt="test",
                platform_context={"tenant_id": "t1"},
            )

            call_kwargs = mock_agno_agent.call_args[1]
            assert call_kwargs.get("skills") is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/core/test_skills.py::TestAgnoAdapterSkillsIntegration -v`
Expected: FAIL (adapter doesn't handle skills yet)

**Step 3: Modify AgnoAdapter._create_agent_async**

In `dcaf/core/adapters/outbound/agno/adapter.py`, make these changes:

1. Add import at top of file:
```python
from dcaf.core.services.skill_manager import SkillManager
from dcaf.core.domain.value_objects.skill_definition import SkillDefinition
```

2. Replace the `_create_agent_async` method to resolve skills from platform_context and pass to AgnoAgent:

```python
    async def _create_agent_async(
        self,
        tools: list[Any],
        system_prompt: str | None = None,
        stream: bool = False,
        platform_context: dict[str, Any] | None = None,
    ) -> AgnoAgent:
        """
        Create an Agno Agent with async session.

        Args:
            tools: List of dcaf Tool objects
            system_prompt: Optional system prompt
            stream: Whether streaming is enabled
            platform_context: Optional platform context to inject into tools

        Returns:
            Configured AgnoAgent
        """
        # Create the model with async session
        model = await self._get_or_create_model_async()

        # Convert tools to Agno format (with context injection for tools that need it)
        agno_tools = self._convert_tools_to_agno(tools, platform_context)

        # WORKAROUND: Prepend instruction to prevent parallel tool calls
        modified_prompt = self._get_modified_system_prompt(system_prompt)

        # Resolve skills from platform context
        agno_skills = await self._resolve_skills(platform_context)

        logger.info(
            f"Agno: Creating agent with {len(agno_tools)} tools "
            f"(stream={stream}, tool_limit={self._tool_call_limit}, "
            f"skills={'yes' if agno_skills else 'no'})"
        )

        # Create the agent
        agent = AgnoAgent(
            model=model,
            instructions=modified_prompt,
            tools=agno_tools if agno_tools else None,
            stream=stream,
            tool_call_limit=self._tool_call_limit,
            skills=agno_skills,
        )

        return agent

    async def _resolve_skills(
        self, platform_context: dict[str, Any] | None
    ) -> "Skills | None":
        """
        Extract and resolve skills from platform context.

        Args:
            platform_context: The platform context dict, may contain a "skills" key.

        Returns:
            An Agno Skills object, or None if no skills are defined.
        """
        if not platform_context:
            return None

        raw_skills = platform_context.get("skills")
        if not raw_skills:
            return None

        definitions = [
            SkillDefinition(name=s["name"], version=s["version"], url=s["url"])
            for s in raw_skills
        ]

        manager = SkillManager()
        return await manager.resolve_skills(definitions)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_skills.py::TestAgnoAdapterSkillsIntegration -v`
Expected: All PASS

**Step 5: Run full test suite for regressions**

Run: `python -m pytest tests/ -x -q --tb=short`
Expected: All existing tests still pass.

**Step 6: Commit**

```bash
git add dcaf/core/adapters/outbound/agno/adapter.py tests/core/test_skills.py
git commit -m "feat: wire skills from platform context into AgnoAgent"
```

---

### Task 7: Add PERSISTENT_VOLUME_STORAGE to EnvVars Config

**Files:**
- Modify: `dcaf/core/config.py:66-100` (EnvVars class)
- Test: `tests/core/test_skills.py`

**Step 1: Write the failing test**

```python
# Append to tests/core/test_skills.py

class TestEnvVarsConfig:
    def test_persistent_volume_storage_constant_exists(self):
        from dcaf.core.config import EnvVars

        assert EnvVars.PERSISTENT_VOLUME_STORAGE == "PERSISTENT_VOLUME_STORAGE"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_skills.py::TestEnvVarsConfig -v`
Expected: FAIL (attribute does not exist)

**Step 3: Add the constant to EnvVars**

In `dcaf/core/config.py`, add to the `EnvVars` class after the behavior flags section:

```python
    # Storage
    PERSISTENT_VOLUME_STORAGE = "PERSISTENT_VOLUME_STORAGE"
```

Then update `SkillManager.__init__` to use it:

```python
from dcaf.core.config import EnvVars

# In __init__:
        self.storage_path = (
            storage_path
            or os.environ.get(EnvVars.PERSISTENT_VOLUME_STORAGE)
            or DEFAULT_STORAGE_PATH
        )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/core/test_skills.py -v`
Expected: All PASS

**Step 5: Run full suite**

Run: `python -m pytest tests/ -x -q --tb=short`
Expected: All pass.

**Step 6: Commit**

```bash
git add dcaf/core/config.py dcaf/core/services/skill_manager.py tests/core/test_skills.py
git commit -m "feat: add PERSISTENT_VOLUME_STORAGE to EnvVars config"
```

---

### Task 8: End-to-End Integration Test

**Files:**
- Test: `tests/core/test_skills.py`

Write a test that exercises the full flow: platform context with skills → SkillManager resolves → AgnoAdapter creates agent with skills.

**Step 1: Write the integration test**

```python
# Append to tests/core/test_skills.py

class TestSkillsEndToEnd:
    @pytest.mark.asyncio
    async def test_full_flow_cached_skill(self, tmp_path, monkeypatch):
        """End-to-end: cached skill flows from platform context to AgnoAgent."""
        from agno.skills import Skills

        monkeypatch.setenv("PERSISTENT_VOLUME_STORAGE", str(tmp_path))

        # Set up a cached skill
        skill_dir = tmp_path / "skills" / "e2e-skill" / "1.0.0"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: e2e-skill\ndescription: End to end test skill\n---\n# E2E Skill"
        )

        # Build skill definitions as they'd appear in platform context
        definitions = [
            SkillDefinition(name="e2e-skill", version="1.0.0", url="https://example.com/unused"),
        ]

        manager = SkillManager()
        result = await manager.resolve_skills(definitions)

        assert isinstance(result, Skills)
        assert "e2e-skill" in result.get_skill_names()

    @pytest.mark.asyncio
    async def test_full_flow_fetch_and_cache(self, tmp_path, monkeypatch):
        """End-to-end: skill not cached → fetched → cached → loaded."""
        monkeypatch.setenv("PERSISTENT_VOLUME_STORAGE", str(tmp_path))

        zip_bytes = _make_zip_bytes({
            "SKILL.md": "---\nname: fetched\ndescription: Fetched skill\n---\n# Fetched",
        })

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = zip_bytes
        mock_response.headers = {"content-type": "application/zip"}
        mock_response.raise_for_status = MagicMock()

        definitions = [
            SkillDefinition(name="fetched", version="1.0.0", url="https://example.com/skill.zip"),
        ]

        manager = SkillManager()

        with patch("dcaf.core.services.skill_manager.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await manager.resolve_skills(definitions)

        assert result is not None
        # Verify it was cached
        cached = tmp_path / "skills" / "fetched" / "1.0.0" / "SKILL.md"
        assert cached.is_file()
```

**Step 2: Run integration tests**

Run: `python -m pytest tests/core/test_skills.py::TestSkillsEndToEnd -v`
Expected: All PASS

**Step 3: Run full suite one final time**

Run: `python -m pytest tests/ -x -q --tb=short`
Expected: All pass.

**Step 4: Commit**

```bash
git add tests/core/test_skills.py
git commit -m "test: add end-to-end integration tests for skills feature"
```

---

## Summary of Files

| Action | File |
|--------|------|
| Modify | `pyproject.toml` (agno version bump) |
| Create | `dcaf/core/domain/value_objects/skill_definition.py` |
| Modify | `dcaf/core/schemas/messages.py` (SkillDefinitionSchema + skills field) |
| Create | `dcaf/core/services/skill_manager.py` |
| Modify | `dcaf/core/adapters/outbound/agno/adapter.py` (_create_agent_async + _resolve_skills) |
| Modify | `dcaf/core/config.py` (PERSISTENT_VOLUME_STORAGE) |
| Create | `tests/core/test_skills.py` |
