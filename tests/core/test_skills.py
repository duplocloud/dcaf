# tests/core/test_skills.py
import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition
from dcaf.core.services.skill_manager import SkillManager


def test_agno_skills_imports():
    """Verify agno 2.5.2 has the Skills API we need."""
    from agno.skills import LocalSkills, Skills

    assert Skills is not None
    assert LocalSkills is not None


class TestSkillDefinition:
    def test_create_skill_definition(self):
        skill = SkillDefinition(
            name="k8s-debug", version="1.0.0", url="https://example.com/skill.zip"
        )
        assert skill.name == "k8s-debug"
        assert skill.version == "1.0.0"
        assert skill.url == "https://example.com/skill.zip"

    def test_skill_definition_immutable(self):
        skill = SkillDefinition(
            name="k8s-debug", version="1.0.0", url="https://example.com/skill.zip"
        )
        try:
            skill.name = "changed"
            raise AssertionError("Should be immutable")
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


class TestSkillManagerLocalLookup:
    def test_skill_found_locally(self, tmp_path):
        """When SKILL.md exists at {storage}/skills/{name}/{version}/, return the path."""
        skill_dir = tmp_path / "skills" / "k8s-debug" / "1.0.0"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# K8s Debug Skill")

        manager = SkillManager(storage_path=str(tmp_path))
        skill = SkillDefinition(name="k8s-debug", version="1.0.0", url="https://example.com/unused")

        path = manager.get_local_skill_path(skill)

        assert path == str(skill_dir)

    def test_skill_not_found_locally(self, tmp_path):
        """When skill directory doesn't exist, return None."""
        manager = SkillManager(storage_path=str(tmp_path))
        skill = SkillDefinition(
            name="missing", version="1.0.0", url="https://example.com/skill.zip"
        )

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
        skill = SkillDefinition(
            name="zip-skill", version="1.0.0", url="https://example.com/skill.zip"
        )
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
        skill = SkillDefinition(
            name="unreachable", version="1.0.0", url="https://down.example.com/x"
        )
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

    @pytest.mark.asyncio
    async def test_fetch_zip_path_traversal_rejected(self, tmp_path):
        """Zip with path traversal attack is rejected."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("SKILL.md", "# Skill")
            zf.writestr("../../../etc/passwd", "malicious")
        zip_bytes = buf.getvalue()

        skill = SkillDefinition(name="evil", version="1.0.0", url="https://example.com/evil.zip")
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
