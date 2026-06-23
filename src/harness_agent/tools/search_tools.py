"""Web search tool using Tavily API.

Security hardening (Phase 5):
- Query sanitization (HTML tags, null bytes, length limits)
- Result count bounded (1-20)
- Input validation via Pydantic schema
- JSON-safe output (no f-string injection)
"""

from __future__ import annotations

import json
import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator


class WebSearchInput(BaseModel):
    """Input schema for web_search tool."""

    query: str = Field(
        ...,
        description="Search query string",
        min_length=1,
        max_length=500,
    )
    max_results: int = Field(
        default=5,
        description="Maximum number of results to return",
        ge=1,
        le=20,
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Sanitize search query.

        - Strip HTML/script tags
        - Remove null bytes
        - Trim whitespace
        - Limit length
        """
        v = re.sub(r"<[^>]*>", "", v)
        v = v.replace("\x00", "")
        v = v.strip()
        return v[:500]


@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information using Tavily API.

    Args:
        query: The search query string.
        max_results: Maximum number of results (1-20, default 5).

    Returns:
        A valid JSON string with search results including title, url, and content.
    """
    return json.dumps({
        "status": "not_implemented",
        "message": "web_search is not yet implemented. Configure Tavily API to enable.",
        "query": query,
        "max_results": max_results,
    })
