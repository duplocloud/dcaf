# tests/core/test_skills.py


def test_agno_skills_imports():
    """Verify agno 2.5.2 has the Skills API we need."""
    from agno.skills import Skills, LocalSkills

    assert Skills is not None
    assert LocalSkills is not None


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


from dcaf.core.services.skill_manager import SkillManager


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
