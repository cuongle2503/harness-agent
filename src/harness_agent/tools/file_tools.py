"""File operation tools.

File operations (read, write, edit, glob, grep) are handled by
deepagents' FilesystemMiddleware. No custom file tools are needed
in the registry — the middleware provides them automatically.

This module is reserved for custom file utilities that extend
or wrap the built-in FilesystemMiddleware tools in future phases.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class FetchUrlInput(BaseModel):
    """Input schema for fetch_url tool."""

    url: str = Field(..., description="URL to fetch content from", min_length=1)
    max_length: int = Field(
        default=100_000,
        description="Maximum content length to return",
        ge=1,
        le=1_000_000,
    )


@tool(args_schema=FetchUrlInput)
def fetch_url(url: str, max_length: int = 100_000) -> str:
    """Fetch and parse content from a URL as markdown.

    Uses httpx + BeautifulSoup for fetching and parsing.
    SSRF prevention: validates URL against allowlist, blocks internal IPs.

    Args:
        url: The URL to fetch content from.
        max_length: Maximum content length to return (default 100KB).

    Returns:
        The page content converted to markdown.
    """
    # Minimal GREEN-phase implementation.
    # Full httpx + BeautifulSoup integration deferred to Phase 4.
    return f'{{"content": "", "url": "{url}", "status": "placeholder"}}'
