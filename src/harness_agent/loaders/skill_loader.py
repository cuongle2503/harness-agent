"""Skill Loader — scan .harness/skills/*.md for MemoryMiddleware sources.

Plan: docs/guides/plans-phase-2/02-skill-loader.md
"""

from __future__ import annotations

import re
from pathlib import Path


class SkillInfo:
    """Basic information about a registered skill."""

    def __init__(
        self, name: str, path: str, size: int, description: str = ""
    ) -> None:
        self.name = name
        self.path = path
        self.size = size
        self.description = description

    def __repr__(self) -> str:
        return (
            f"SkillInfo(name={self.name!r}, size={self.size}, "
            f"desc={self.description[:40]!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SkillInfo):
            return NotImplemented
        return (
            self.name == other.name
            and self.path == other.path
            and self.size == other.size
            and self.description == other.description
        )


def _extract_skill_metadata(content: str) -> tuple[str, str]:
    """Extract skill name and description from markdown content.

    Name: first ``# Heading`` (stripped of leading ``#``).
    Description: first non-empty paragraph after the heading
    (before the next heading or list).

    Returns (name, description). Both may be empty strings.
    """
    name = ""
    description = ""

    # Try first # heading for name
    heading_match = re.match(r"^#\s+(.+)", content, re.MULTILINE)
    if heading_match:
        name = heading_match.group(1).strip()

    # Try to find description: text between first heading and
    # next heading/list/code block, excluding blank lines and
    # the heading line itself.
    lines = content.split("\n")
    in_desc = False
    desc_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Start collecting after first heading
        if not in_desc and re.match(r"^#\s+", stripped):
            in_desc = True
            continue

        if in_desc:
            # Stop at next heading, list item, code fence, or horizontal rule
            if re.match(r"^(#+|[-*]\s|```|--|\|)", stripped):
                break
            if stripped:
                desc_lines.append(stripped)
            elif desc_lines:
                # Blank line after we have content → stop
                break

    if desc_lines:
        description = " ".join(desc_lines)

    return name, description


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

        Parses each skill file to extract the name (first ``# Heading``)
        and description (first paragraph after the heading). These are
        used for progressive disclosure — the LLM sees name + description
        at all times, and the full body is loaded when the task matches.

        Returns:
            List of SkillInfo with name, path, size, and description.
            Empty list if the skills directory does not exist.
        """
        if not self.exists:
            return []
        result: list[SkillInfo] = []
        for p in sorted(self.skills_dir.glob("*.md")):
            try:
                content = p.read_text(encoding="utf-8")
                name, description = _extract_skill_metadata(content)
            except Exception:
                name, description = "", ""
            result.append(
                SkillInfo(
                    name=name or p.stem.replace("-", " ").title(),
                    path=str(p.resolve()),
                    size=p.stat().st_size,
                    description=description,
                )
            )
        return result
