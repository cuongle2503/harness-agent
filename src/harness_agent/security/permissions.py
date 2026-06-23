"""Permission boundary enforcement.

Phase 5 — Security Hardening (per AIDLC §5.7 Permission Boundaries).

Limits file system access by path, preventing:
- Access to .git/ directory
- Access to .env and secrets files
- Access to system directories (/etc/, /proc/, /sys/)
- Access outside the workspace
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Permission = Literal["read", "write"]


@dataclass
class PathPermission:
    """A single path permission rule.

    Attributes:
        path: The path pattern (glob supported).
        permissions: Allowed permissions (read, write, or empty for deny).
    """

    path: str
    permissions: list[Permission]


@dataclass
class PermissionBoundary:
    """File system permission boundary for agent tools.

    Default: deny all, then selectively allow with rules.
    Rules are evaluated in order — first match wins.

    Attributes:
        rules: Ordered list of path permission rules.
        workspace_root: The root directory for workspace-scoped access.
    """

    rules: list[PathPermission] = field(default_factory=list)
    workspace_root: Path = field(default_factory=lambda: Path.home() / "my-projects")

    @classmethod
    def production(cls) -> PermissionBoundary:
        """Create production permission boundaries.

        Allows:
        - /workspace/** — read, write
        - /memories/** — read, write
        - /data/** — read only

        Denies:
        - /workspace/.git/** — no access
        - /workspace/.env* — no access
        - /etc/**, /proc/**, /sys/** — no access
        """
        return cls(rules=[
            PathPermission(path="/workspace/.git/**", permissions=[]),
            PathPermission(path="/workspace/.env*", permissions=[]),
            PathPermission(path="/workspace/**", permissions=["read", "write"]),
            PathPermission(path="/memories/**", permissions=["read", "write"]),
            PathPermission(path="/data/**", permissions=["read"]),
            # Default: everything else denied (implicit)
        ])

    @classmethod
    def development(cls) -> PermissionBoundary:
        """Create development permission boundaries (more permissive)."""
        return cls(rules=[
            PathPermission(path="/workspace/.git/**", permissions=["read"]),
            PathPermission(path="/workspace/.env*", permissions=[]),
            PathPermission(path="/workspace/**", permissions=["read", "write"]),
            PathPermission(path="/memories/**", permissions=["read", "write"]),
            PathPermission(path="/tmp/**", permissions=["read", "write"]),
        ])

    def is_allowed(self, file_path: str, permission: Permission) -> bool:
        """Check if a file path is accessible with the given permission.

        Args:
            file_path: The absolute or relative path to check.
            permission: The requested permission (read/write).

        Returns:
            True if the path is allowed with the given permission.
        """
        resolved = Path(file_path).resolve()
        resolved_str = str(resolved)

        # Check permission rules FIRST (first match wins)
        for rule in self.rules:
            if _path_matches(resolved_str, rule.path):
                return permission in rule.permissions

        # When no rule matches, apply unconditional safety blocks
        blocked_prefixes = ("/etc/", "/proc/", "/sys/", "/dev/", "/boot/")
        for prefix in blocked_prefixes:
            if resolved_str.startswith(prefix):
                return False

        if resolved.name.startswith(".env") or resolved.name == ".env":
            return False

        if ".git" in resolved.parts:
            return False

        # Default: deny
        return False

    def is_path_safe(self, file_path: str) -> bool:
        """Check if a path is within the workspace (traversal prevention).

        Args:
            file_path: The path to check.

        Returns:
            True if the path is within the workspace root.
        """
        resolved = Path(file_path).resolve()
        workspace = self.workspace_root.resolve()
        return resolved.is_relative_to(workspace)


def _path_matches(file_path: str, pattern: str) -> bool:
    """Check if a file path matches a glob-like pattern.

    Supports ** for recursive matching and * for single-segment matching.

    Args:
        file_path: The resolved absolute file path.
        pattern: The glob pattern.

    Returns:
        True if the path matches the pattern.
    """
    # Simple prefix matching for common cases
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        from pathlib import PurePath
        return PurePath(file_path).is_relative_to(prefix)
    if pattern.endswith("*"):
        # Match files in the same directory
        import os
        dir_pattern = os.path.dirname(pattern)
        name_pattern = os.path.basename(pattern)
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        if file_dir == dir_pattern or file_path.startswith(dir_pattern):
            import fnmatch
            return fnmatch.fnmatch(file_name, name_pattern)
    return file_path == pattern


__all__ = ["PermissionBoundary", "PathPermission", "Permission"]
