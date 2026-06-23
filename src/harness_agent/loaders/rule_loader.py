"""Rule Loader — scan .harness/rules/**/*.md for MemoryMiddleware sources.

Plan: docs/guides/plans-phase-2/03-rule-loader.md
"""

from __future__ import annotations

from pathlib import Path


class RuleInfo:
    """Basic information about a registered rule."""

    def __init__(self, name: str, relative_path: str, size: int) -> None:
        self.name = name
        self.relative_path = relative_path
        self.size = size

    def __repr__(self) -> str:
        return (
            f"RuleInfo(name={self.name!r}, "
            f"path={self.relative_path!r}, "
            f"size={self.size})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RuleInfo):
            return NotImplemented
        return (
            self.name == other.name
            and self.relative_path == other.relative_path
            and self.size == other.size
        )


class RuleLoader:
    """Scan .harness/rules/**/*.md and provide paths for MemoryMiddleware.

    Rules are markdown files describing constraints the agent must follow.
    They are injected into the system prompt via MemoryMiddleware.sources.

    Unlike skills (flat structure), rules support subdirectories for
    organizing by domain: python/, database/, security/, etc.

    Usage::

        loader = RuleLoader(Path("my-project/.harness"))
        sources = loader.get_memory_sources()
        # sources = [
        #     "/abs/path/.harness/rules/api-naming.md",
        #     "/abs/path/.harness/rules/python/coding-style.md",
        #     ...
        # ]
    """

    def __init__(self, harness_dir: Path) -> None:
        """Create a rule loader for the given ``.harness/`` directory.

        Args:
            harness_dir: Path to the ``.harness/`` directory.
        """
        self.harness_dir = harness_dir
        self.rules_dir = harness_dir / "rules"

    @property
    def exists(self) -> bool:
        """Check whether the rules/ directory exists."""
        return self.rules_dir.is_dir()

    def get_memory_sources(self) -> list[str]:
        """Return absolute paths of all rule markdown files (recursive).

        These paths are designed to be passed directly to
        ``MemoryMiddleware(sources=[...])``.

        Returns:
            List of absolute paths as strings, sorted. Empty list if the
            rules directory does not exist or contains no .md files.
        """
        if not self.exists:
            return []
        return sorted(
            str(p.resolve()) for p in self.rules_dir.rglob("*.md")
        )

    def list_rules(self) -> list[RuleInfo]:
        """List information about all registered rules.

        Returns:
            List of RuleInfo with name, relative_path, and size. Empty
            list if the rules directory does not exist.
        """
        if not self.exists:
            return []
        return [
            RuleInfo(
                name=p.stem,
                relative_path=str(p.relative_to(self.rules_dir)),
                size=p.stat().st_size,
            )
            for p in sorted(self.rules_dir.rglob("*.md"))
        ]
