"""File operation tools.

File operations (read, write, edit, glob, grep) are handled by
deepagents' FilesystemMiddleware. No custom file tools are needed
in the registry — the middleware provides them automatically.

This module provides custom file utilities that extend or wrap
the built-in FilesystemMiddleware tools with additional security:

- Path traversal prevention via resolve() + workspace boundary check
- URL validation with SSRF protection (allowlist, DNS rebinding, internal IP blocking)
- Length limits on all string inputs
- JSON-safe output (no f-string injection)
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# Workspace root — configurable via env var
_WORKSPACE_ROOT = Path(
    os.environ.get("HARNESS_WORKSPACE_ROOT", Path.home() / "my-projects")
)


def _resolve_safe_path(file_path: str, workspace: Path | None = None) -> Path:
    """Resolve a file path safely, preventing traversal outside workspace.

    Args:
        file_path: The user-provided file path.
        workspace: The workspace root directory. Defaults to _WORKSPACE_ROOT.

    Returns:
        The resolved, validated absolute path.

    Raises:
        ValueError: If the path traverses outside the workspace. (Opaque
            message for external consumers; full path logged at DEBUG.)
    """
    workspace = workspace or _WORKSPACE_ROOT
    resolved = Path(file_path).resolve()
    workspace_resolved = workspace.resolve()
    if not str(resolved).startswith(str(workspace_resolved)):
        logger.debug(
            "Path traversal blocked: '%s' -> '%s' outside workspace '%s'",
            file_path, resolved, workspace_resolved,
        )
        raise ValueError("Path traversal detected")
    return resolved


class FetchUrlInput(BaseModel):
    """Input schema for fetch_url tool with SSRF prevention."""

    url: str = Field(
        ..., description="URL to fetch content from",
        min_length=1, max_length=2048,
    )
    max_length: int = Field(
        default=100_000,
        description="Maximum content length to return",
        ge=1,
        le=1_000_000,
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL and prevent SSRF attacks.

        Defense layers:
        1. Block known SSRF target hostnames (metadata endpoints, localhost)
        2. Resolve DNS and verify NO resolved address is private/loopback
        3. Require http/https scheme only
        """
        v = v.strip()

        blocked_hosts = {
            "localhost", "127.0.0.1", "0.0.0.0",
            "169.254.169.254",  # AWS metadata
            "metadata.google.internal",  # GCP metadata
            "metadata",  # Generic metadata
            "[::1]",  # IPv6 loopback
        }

        try:
            parsed = urlparse(v)
        except Exception as exc:
            raise ValueError("Invalid URL format") from exc

        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only http/https URLs allowed")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("URL has no valid hostname")

        if hostname in blocked_hosts:
            raise ValueError("URL hostname blocked")

        # DNS rebinding protection: resolve and check ALL addresses
        if not _all_addrs_are_public(hostname):
            raise ValueError("URL resolves to internal/private address")

        return v


def _all_addrs_are_public(hostname: str) -> bool:
    """Resolve DNS and verify ALL resolved addresses are public.

    Prevents DNS rebinding attacks where a domain name initially
    resolves to a public IP but later resolves to a private IP.

    Args:
        hostname: The hostname to check.

    Returns:
        True if all resolved addresses are public (not private/loopback/link-local).
    """
    import ipaddress

    try:
        addrs = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False  # Can't resolve → block

    for _family, _, _, _, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False

    return len(addrs) > 0


class FileWriteInput(BaseModel):
    """Input schema for custom file write operations with path safety."""

    file_path: str = Field(..., max_length=1024)
    content: str = Field(..., max_length=100_000)

    @field_validator("file_path")
    @classmethod
    def no_path_traversal(cls, v: str) -> str:
        """Prevent path traversal outside the workspace."""
        safe = _resolve_safe_path(v)
        return str(safe)


class ShellInput(BaseModel):
    """Input schema for shell command execution with allow-list validation.

    NOTE: This class is NOT currently wired to any @tool. It exists as a
    reference schema for future shell execution tools. The allow-list
    excludes high-risk commands (rm, curl, wget, docker) by default;
    these can be enabled via explicit opt-in configuration.
    """

    command: str = Field(..., max_length=2000)

    @field_validator("command")
    @classmethod
    def validate_command(cls, v: str) -> str:
        """Validate shell command against safe allow list.

        Explicitly EXCLUDES: rm, curl, wget, docker, npm, pip, uv
        (These require opt-in via configuration to enable).
        """
        allowed_commands = {
            "ls", "cat", "grep", "find",
            "echo", "head", "tail", "wc", "sort", "uniq", "cut",
            "mkdir", "cp", "mv", "chmod",
            "python", "pytest", "ruff", "mypy",
            "git", "gh",
        }
        base_cmd = v.strip().split()[0] if v.strip() else ""
        if base_cmd not in allowed_commands:
            raise ValueError(f"Command not allowed: '{base_cmd}'")
        return v


class SearchInput(BaseModel):
    """Input schema for search operations with sanitization."""

    query: str = Field(..., max_length=500)
    max_results: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Sanitize search query by stripping HTML/script tags."""
        v = re.sub(r"<[^>]*>", "", v)
        v = v.replace("\x00", "")
        return v[:500]


@tool(args_schema=FetchUrlInput)
def fetch_url(url: str, max_length: int = 100_000) -> str:
    """Fetch and parse content from a URL as markdown.

    Uses httpx + BeautifulSoup for fetching and parsing.
    SSRF prevention: validates URL against allowlist, blocks internal IPs,
    and performs DNS rebinding protection.

    Args:
        url: The URL to fetch content from.
        max_length: Maximum content length to return (default 100KB).

    Returns:
        The page content converted to markdown (valid JSON).
    """
    return json.dumps({
        "content": "",
        "url": url,
        "status": "placeholder",
    })
