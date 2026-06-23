"""Skill Loader — scan .harness/skills/ for skill definitions.

Supports three formats:
1. Agent Skills spec: skills/<name>/SKILL.md (with YAML frontmatter)
2. Flat markdown: skills/*.md
3. YAML definitions: skills/*.yaml
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


def _extract_yaml_frontmatter(content: str) -> tuple[str, str]:
    """Extract name and description from YAML frontmatter (Agent Skills spec).

    Looks for ``---`` delimited YAML at the start of the file with
    ``name:`` and ``description:`` keys.

    Returns (name, description). Both may be empty strings.
    """
    name = ""
    description = ""
    # Match YAML frontmatter between --- delimiters
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return name, description
    frontmatter = m.group(1)
    # Extract name
    name_match = re.search(r"^name:\s*(.+)", frontmatter, re.MULTILINE)
    if name_match:
        name = name_match.group(1).strip().strip('"').strip("'")
    # Extract description
    desc_match = re.search(
        r"^description:\s*(.+)", frontmatter, re.MULTILINE
    )
    if desc_match:
        description = desc_match.group(1).strip().strip('"').strip("'")
    return name, description


def _extract_yaml_skill_info(path: Path) -> tuple[str, str]:
    """Extract name and description from a YAML skill definition file.

    Reads top-level ``name:`` and ``description:`` keys from a
    standalone YAML file (not frontmatter-delimited).

    Returns (name, description). Both may be empty strings.
    """
    import yaml

    content = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(content)
    if not isinstance(raw, dict):
        return "", ""
    name = str(raw.get("name", "")).strip().strip('"').strip("'")
    description = str(raw.get("description", "")).strip().strip('"').strip("'")
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
        """Return absolute paths of all skill files/directories.

        Supports three formats (checked in priority order):
        1. Agent Skills spec: ``skills/<name>/SKILL.md``
        2. Flat markdown: ``skills/*.md``
        3. YAML skill definitions: ``skills/*.yaml``

        Returns:
            List of absolute paths as strings. Empty list if the
            skills directory does not exist or contains no skills.
        """
        if not self.exists:
            return []
        # Priority 1: directories that contain a SKILL.md file
        skill_dirs: list[str] = []
        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            skill_dirs.append(str(skill_md.parent.resolve()))
        if skill_dirs:
            return skill_dirs
        # Priority 2: flat *.md files
        md_files = sorted(self.skills_dir.glob("*.md"))
        if md_files:
            return [str(p.resolve()) for p in md_files]
        # Priority 3: *.yaml skill definitions
        yaml_files = sorted(self.skills_dir.glob("*.yaml"))
        if yaml_files:
            return [str(p.resolve()) for p in yaml_files]
        return []

    def list_skills(self) -> list[SkillInfo]:
        """List information about all registered skills.

        Supports three formats (checked in priority order):
        1. Agent Skills spec: ``skills/<name>/SKILL.md``
        2. Flat markdown: ``skills/*.md``
        3. YAML definitions: ``skills/*.yaml``

        Returns:
            List of SkillInfo with name, path, size, and description.
            Empty list if the skills directory does not exist.
        """
        if not self.exists:
            return []
        result: list[SkillInfo] = []

        # Primary: scan */SKILL.md (Agent Skills spec)
        for skill_md in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                content = skill_md.read_text(encoding="utf-8")
                name, description = _extract_skill_metadata(content)
                # YAML frontmatter takes priority for name
                fm_name, fm_desc = _extract_yaml_frontmatter(content)
                name = fm_name or name
                description = fm_desc or description
            except Exception:
                name, description = "", ""
            result.append(
                SkillInfo(
                    name=name or skill_md.parent.name.replace("-", " ").title(),
                    path=str(skill_md.resolve()),
                    size=skill_md.stat().st_size,
                    description=description,
                )
            )

        # Fallback 1: flat *.md files
        if not result:
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

        # Fallback 2: *.yaml skill definitions
        if not result:
            for p in sorted(self.skills_dir.glob("*.yaml")):
                try:
                    name, description = _extract_yaml_skill_info(p)
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
