# tests/core/test_skills.py


def test_agno_skills_imports():
    """Verify agno 2.5.2 has the Skills API we need."""
    from agno.skills import Skills, LocalSkills

    assert Skills is not None
    assert LocalSkills is not None
