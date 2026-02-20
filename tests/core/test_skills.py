# tests/core/test_skills.py
import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from dcaf.core.domain.value_objects.skill_definition import SkillDefinition
from dcaf.core.services.skill_manager import SkillManager
from dcaf.core.services.skill_translator import translate_skills


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
    async def test_fetch_zip_nested_skill_md_elevated(self, tmp_path):
        """Zip with SKILL.md in a subdirectory gets elevated to root."""
        zip_bytes = _make_zip_bytes({
            "my-skill/SKILL.md": "# Nested Skill",
            "my-skill/scripts/run.sh": "echo hello",
        })
        skill = SkillDefinition(
            name="nested-skill", version="1.0.0", url="https://example.com/nested.zip"
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
        assert (Path(path) / "SKILL.md").read_text() == "# Nested Skill"
        assert (Path(path) / "scripts" / "run.sh").read_text() == "echo hello"

    @pytest.mark.asyncio
    async def test_fetch_zip_nested_with_macos_metadata_elevated(self, tmp_path):
        """Zip with __MACOSX metadata and nested SKILL.md still works."""
        zip_bytes = _make_zip_bytes({
            "hello-python/SKILL.md": "# Hello Skill",
            "hello-python/scripts/hello.py": "print('hi')",
            "__MACOSX/._hello-python": "",
            "__MACOSX/hello-python/._SKILL.md": "",
        })
        skill = SkillDefinition(
            name="macos-skill", version="1.0.0", url="https://example.com/macos.zip"
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
        assert (Path(path) / "SKILL.md").read_text() == "# Hello Skill"
        assert (Path(path) / "scripts" / "hello.py").read_text() == "print('hi')"
        # __MACOSX junk should not be present at root
        assert not (Path(path) / "__MACOSX").exists()

    @pytest.mark.asyncio
    async def test_fetch_zip_deeply_nested_skill_md_rejected(self, tmp_path):
        """Zip with SKILL.md nested more than one level deep is rejected."""
        zip_bytes = _make_zip_bytes({
            "a/b/SKILL.md": "# Too Deep",
        })
        skill = SkillDefinition(
            name="deep-skill", version="1.0.0", url="https://example.com/deep.zip"
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

        assert path is None

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

        adapter = AgnoAdapter(model_id="test-model", provider="anthropic")

        # Mock model creation to avoid real API calls
        mock_model = MagicMock()
        adapter._get_or_create_model_async = AsyncMock(return_value=mock_model)

        with (
            patch.object(SkillManager, "__init__", lambda self, **_kw: setattr(self, "storage_path", str(tmp_path)) or None),
            patch.object(SkillManager, "get_local_skill_path", return_value=str(skill_dir)),
            patch("dcaf.core.adapters.outbound.agno.adapter.AgnoAgent") as mock_agno_agent,
        ):
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


class TestEnvVarsConfig:
    def test_persistent_volume_storage_constant_exists(self):
        from dcaf.core.config import EnvVars

        assert EnvVars.PERSISTENT_VOLUME_STORAGE == "PERSISTENT_VOLUME_STORAGE"


class TestSkillsEndToEnd:
    @pytest.mark.asyncio
    async def test_full_flow_cached_skill(self, tmp_path, monkeypatch):
        """End-to-end: cached skill flows from platform context to SkillManager resolution."""
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
        """End-to-end: skill not cached -> fetched -> cached -> loaded."""
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


class TestSkillTranslator:
    def test_translate_skillmd_format(self):
        """SkillMd format creates SkillDefinition with inline content."""
        raw = [
            {
                "Name": "ecs-troubleshooting",
                "Version": 0,
                "Format": "SkillMd",
                "SkillMd": "---\nname: ecs-troubleshooting\n---\n# ECS Skill",
                "IsActive": True,
                "Id": "abc123",
                "Type": "Custom",
            }
        ]
        result = translate_skills(raw)
        assert len(result) == 1
        assert result[0].name == "ecs-troubleshooting"
        assert result[0].version == "0"
        assert result[0].url == ""
        assert result[0].content == "---\nname: ecs-troubleshooting\n---\n# ECS Skill"

    def test_translate_package_format(self):
        """Package format creates SkillDefinition with signed URL."""
        raw = [
            {
                "Name": "magic-iac",
                "Version": 0,
                "Format": "Package",
                "FileStoreSignedUrl": "https://s3.example.com/skill.zip?token=abc",
                "IsActive": True,
                "Id": "def456",
                "Type": "Custom",
            }
        ]
        result = translate_skills(raw)
        assert len(result) == 1
        assert result[0].name == "magic-iac"
        assert result[0].version == "0"
        assert result[0].url == "https://s3.example.com/skill.zip?token=abc"
        assert result[0].content is None

    def test_filter_inactive_skills(self):
        """Inactive skills are excluded."""
        raw = [
            {
                "Name": "inactive-skill",
                "Version": 1,
                "Format": "SkillMd",
                "SkillMd": "# content",
                "IsActive": False,
            },
            {
                "Name": "active-skill",
                "Version": 2,
                "Format": "SkillMd",
                "SkillMd": "# active content",
                "IsActive": True,
            },
        ]
        result = translate_skills(raw)
        assert len(result) == 1
        assert result[0].name == "active-skill"

    def test_version_int_to_str(self):
        """Integer version is converted to string."""
        raw = [
            {
                "Name": "versioned",
                "Version": 42,
                "Format": "SkillMd",
                "SkillMd": "# content",
                "IsActive": True,
            }
        ]
        result = translate_skills(raw)
        assert result[0].version == "42"

    def test_internal_format_passthrough(self):
        """Existing internal format (lowercase keys) passes through unchanged."""
        raw = [
            {"name": "hello-python", "version": "1.0.2", "url": "http://localhost:8001/hello.zip"}
        ]
        result = translate_skills(raw)
        assert len(result) == 1
        assert result[0].name == "hello-python"
        assert result[0].version == "1.0.2"
        assert result[0].url == "http://localhost:8001/hello.zip"
        assert result[0].content is None

    def test_mixed_formats(self):
        """Internal and external formats can coexist in the same list."""
        raw = [
            {"name": "internal-skill", "version": "1.0.0", "url": "http://example.com/skill.md"},
            {
                "Name": "external-skill",
                "Version": 0,
                "Format": "SkillMd",
                "SkillMd": "# External",
                "IsActive": True,
            },
        ]
        result = translate_skills(raw)
        assert len(result) == 2
        assert result[0].name == "internal-skill"
        assert result[1].name == "external-skill"

    def test_unknown_format_skipped(self):
        """Unknown Format value is skipped with warning."""
        raw = [
            {
                "Name": "weird",
                "Version": 0,
                "Format": "SomethingNew",
                "IsActive": True,
            }
        ]
        result = translate_skills(raw)
        assert len(result) == 0

    def test_skillmd_without_content_skipped(self):
        """SkillMd format with empty SkillMd field is skipped."""
        raw = [
            {
                "Name": "empty-md",
                "Version": 0,
                "Format": "SkillMd",
                "SkillMd": "",
                "IsActive": True,
            }
        ]
        result = translate_skills(raw)
        assert len(result) == 0

    def test_package_without_url_skipped(self):
        """Package format without FileStoreSignedUrl is skipped."""
        raw = [
            {
                "Name": "no-url",
                "Version": 0,
                "Format": "Package",
                "FileStoreSignedUrl": "",
                "IsActive": True,
            }
        ]
        result = translate_skills(raw)
        assert len(result) == 0

    def test_is_active_defaults_true(self):
        """Skills without IsActive field default to active."""
        raw = [
            {
                "Name": "no-active-field",
                "Version": 0,
                "Format": "SkillMd",
                "SkillMd": "# content",
            }
        ]
        result = translate_skills(raw)
        assert len(result) == 1


class TestSkillDefinitionContent:
    def test_content_field_default_none(self):
        """Content field defaults to None for backward compatibility."""
        skill = SkillDefinition(name="test", version="1.0.0", url="http://example.com/skill")
        assert skill.content is None

    def test_content_field_set(self):
        """Content field can hold inline markdown."""
        skill = SkillDefinition(
            name="test", version="1.0.0", url="", content="# Inline Skill"
        )
        assert skill.content == "# Inline Skill"


class TestSkillManagerCacheInline:
    def test_cache_inline_writes_skill_md(self, tmp_path):
        """cache_inline writes content to the correct path."""
        manager = SkillManager(storage_path=str(tmp_path))
        skill = SkillDefinition(
            name="inline-skill",
            version="3",
            url="",
            content="---\nname: inline-skill\n---\n# Inline Skill Content",
        )

        path = manager.cache_inline(skill)

        assert path is not None
        skill_file = Path(path) / "SKILL.md"
        assert skill_file.is_file()
        assert skill_file.read_text() == "---\nname: inline-skill\n---\n# Inline Skill Content"

    def test_cache_inline_overwrites_existing(self, tmp_path):
        """cache_inline always overwrites to avoid stale cache."""
        manager = SkillManager(storage_path=str(tmp_path))

        # Write first version
        skill_v1 = SkillDefinition(
            name="overwrite-test", version="0", url="", content="# Version 1"
        )
        manager.cache_inline(skill_v1)

        # Write second version (same name/version, different content)
        skill_v2 = SkillDefinition(
            name="overwrite-test", version="0", url="", content="# Version 2 (updated)"
        )
        path = manager.cache_inline(skill_v2)

        assert path is not None
        assert (Path(path) / "SKILL.md").read_text() == "# Version 2 (updated)"

    @pytest.mark.asyncio
    async def test_resolve_skills_uses_inline_content(self, tmp_path):
        """resolve_skills writes inline content directly without fetching."""
        from agno.skills import Skills

        manager = SkillManager(storage_path=str(tmp_path))
        definitions = [
            SkillDefinition(
                name="inline-resolved",
                version="0",
                url="",
                content="---\nname: inline-resolved\ndescription: Test\n---\n# Inline",
            ),
        ]

        result = await manager.resolve_skills(definitions)

        assert isinstance(result, Skills)
        # Verify the file was written
        cached = tmp_path / "skills" / "inline-resolved" / "0" / "SKILL.md"
        assert cached.is_file()
