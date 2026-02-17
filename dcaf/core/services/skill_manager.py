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
