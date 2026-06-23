"""Skill invocation tool for Tier 2 fallback (no deepagents).

When the deepagents package is not installed, this tool allows the
LLM to explicitly activate a skill by name. It reads the skill's
markdown content and returns it so the LLM can follow the workflow.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SkillInput(BaseModel):
    """Input schema for the skill invocation tool."""

    skill_name: str = Field(
        ..., description="Name of the skill to activate (case-insensitive)"
    )
    context: str = Field(
        default="",
        description="Optional context about the current task for the skill",
    )


class SkillTool(BaseTool):
    """Activate a skill by name and return its workflow instructions.

    Looks up the skill by name from the SkillLoader, reads its
    markdown content, and returns it so the LLM can follow the
    described workflow.
    """

    name: str = "use_skill"
    description: str = (
        "Activate a skill workflow by name. Returns the skill's instructions "
        "which you should then follow step-by-step. Use this when a task "
        "matches an available skill's description."
    )
    args_schema: type[BaseModel] = SkillInput

    skill_loader: Any = None

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, skill_name: str, context: str = "") -> str:
        return self._invoke_skill(skill_name, context)

    async def _arun(self, skill_name: str, context: str = "") -> str:
        return self._invoke_skill(skill_name, context)

    def _invoke_skill(self, skill_name: str, context: str) -> str:
        if self.skill_loader is None:
            return "No skill loader configured."

        skills = self.skill_loader.list_skills()
        if not skills:
            return "No skills available."

        # Case-insensitive match
        match = None
        for sk in skills:
            if sk.name.lower() == skill_name.lower():
                match = sk
                break

        # Fuzzy fallback: partial match
        if match is None:
            for sk in skills:
                if skill_name.lower() in sk.name.lower():
                    match = sk
                    break

        if match is None:
            available = [sk.name for sk in skills]
            return (
                f"Unknown skill '{skill_name}'. "
                f"Available skills: {available}"
            )

        # Read skill content
        from pathlib import Path
        try:
            content = Path(match.path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.error("Failed to read skill '%s': %s", skill_name, e)
            return f"Error reading skill '{match.name}': {e}"

        header = f"# Skill: {match.name}\n\n"
        if context:
            header += f"**Task context**: {context}\n\n"
        header += "Follow the workflow below:\n\n---\n\n"

        return header + content


def create_skill_tool(skill_loader: Any) -> BaseTool:
    """Create a skill invocation tool for the Tier 2 fallback path.

    Args:
        skill_loader: A SkillLoader instance for resolving skill names.

    Returns:
        A configured SkillTool instance.
    """
    return SkillTool(skill_loader=skill_loader)
