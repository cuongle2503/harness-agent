"""Web search tool using Tavily API."""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """Input schema for web_search tool."""

    query: str = Field(..., description="Search query string", min_length=1)
    max_results: int = Field(
        default=5,
        description="Maximum number of results to return",
        ge=1,
        le=20,
    )


@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information using Tavily API.

    Args:
        query: The search query string.
        max_results: Maximum number of results (1-20, default 5).

    Returns:
        A JSON string with search results including title, url, and content.
    """
    # Minimal GREEN-phase implementation — returns placeholder.
    # Full Tavily integration deferred to Phase 4.
    return f'{{"results": [], "query": "{query}", "max_results": {max_results}}}'
