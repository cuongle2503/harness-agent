"""Skill Loader — scan .harness/skills/*.md for MemoryMiddleware sources.

Plan: docs/guides/plans-phase-2/02-skill-loader.md
"""

from __future__ import annotations

from pathlib import Path


class SkillInfo:
    """Basic information about a registered skill."""

    def __init__(self, name: str, path: str, size: int) -> None:
        self.name = name
        self.path = path
        self.size = size

    def __repr__(self) -> str:
        return f"SkillInfo(name={self.name!r}, size={self.size})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SkillInfo):
            return NotImplemented
        return (
            self.name == other.name
            and self.path == other.path
            and self.size == other.size
        )


class SkillLoader:
    """Scan .harness/skills/*.md and provide paths for MemoryMiddleware.

    Skills are markdown files describing workflows for specific tasks.
    They are injected into the system prompt via MemoryMiddleware.sources.
    The agent reads these skills in context and decides when to apply
    the instructions from the appropriate skill.

    Usage::

        loader = SkillLoader(Path("my-project/.harness"))
        sources = loader.get_memory_sources()
        # sources = [
        #     "/abs/path/.harness/skills/deploy-to-k8s.md",
        #     "/abs/path/.harness/skills/db-migration.md",
        # ]
    """

    def __init__(self, harness_dir: Path) -> None:
        """Create a skill loader for the given ``.harness/`` directory.

        Args:
            harness_dir: Path to the ``.harness/`` directory.
        """
        self.harness_dir = harness_dir
        self.skills_dir = harness_dir / "skills"

    @property
    def exists(self) -> bool:
        """Check whether the skills/ directory exists."""
        return self.skills_dir.is_dir()

    def get_memory_sources(self) -> list[str]:
        """Return absolute paths of all skill markdown files.

        These paths are designed to be passed directly to
        ``MemoryMiddleware(sources=[...])``.

        Returns:
            List of absolute paths as strings. Empty list if the
            skills directory does not exist or contains no .md files.
        """
        if not self.exists:
            return []
        return sorted(
            str(p.resolve()) for p in self.skills_dir.glob("*.md")
        )

    def list_skills(self) -> list[SkillInfo]:
        """List information about all registered skills.

        Returns:
            List of SkillInfo with name, path, and size. Empty list if
            the skills directory does not exist.
        """
        if not self.exists:
            return []
        return [
            SkillInfo(
                name=p.stem,
                path=str(p.resolve()),
                size=p.stat().st_size,
            )
            for p in sorted(self.skills_dir.glob("*.md"))
        ]
