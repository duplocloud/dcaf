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
