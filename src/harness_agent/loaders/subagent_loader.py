"""SubAgent Loader — parse .harness/subagents/*.yaml into subagent definitions.

Plan: docs/guides/plans-phase-2/04-subagent-loader.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from harness_agent.core.exceptions import HarnessError
from harness_agent.tools.registry import ToolRegistry


class SubAgentLoadError(HarnessError):
    """Raised when a subagent definition file cannot be loaded."""


class SubAgentInfo:
    """Basic information about a registered subagent (without resolving tools)."""

    def __init__(
        self,
        name: str,
        source_file: str,
        description: str,
        tool_count: int,
    ) -> None:
        self.name = name
        self.source_file = source_file
        self.description = description
        self.tool_count = tool_count

    def __repr__(self) -> str:
        return (
            f"SubAgentInfo(name={self.name!r}, "
            f"source_file={self.source_file!r}, "
            f"tool_count={self.tool_count})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SubAgentInfo):
            return NotImplemented
        return (
            self.name == other.name
            and self.source_file == other.source_file
            and self.description == other.description
            and self.tool_count == other.tool_count
        )


class MiddlewareResolver:
    """Resolve middleware names to instances.

    Supports two formats:
    1. String: "ContextEditingMiddleware" → ContextEditingMiddleware()
    2. Dict with params: {"ToolRetryMiddleware": {"max_retries": 3}}
       → ToolRetryMiddleware(max_retries=3)
    """

    def __init__(self) -> None:
        self._registry: dict[str, type] = {}

    def register(self, name: str, middleware_class: type) -> None:
        """Register a middleware class under a name."""
        self._registry[name] = middleware_class

    def resolve(
        self, raw_middleware: list[Any], source_file: str
    ) -> list[Any]:
        """Resolve a list of middleware specs into instances.

        Args:
            raw_middleware: List of strings or dicts from YAML.
            source_file: The YAML file name (for error messages).

        Returns:
            List of middleware instances.

        Raises:
            SubAgentLoadError: If a middleware name is unknown or format is invalid.
        """
        instances: list[Any] = []
        for item in raw_middleware:
            if isinstance(item, str):
                cls = self._registry.get(item)
                if cls is None:
                    raise SubAgentLoadError(
                        f"Unknown middleware '{item}' in {source_file}. "
                        f"Known: {list(self._registry.keys())}"
                    )
                instances.append(cls())
            elif isinstance(item, dict):
                for name, params in item.items():
                    cls = self._registry.get(name)
                    if cls is None:
                        raise SubAgentLoadError(
                            f"Unknown middleware '{name}' in {source_file}. "
                            f"Known: {list(self._registry.keys())}"
                        )
                    if not isinstance(params, dict):
                        raise SubAgentLoadError(
                            f"Middleware params for '{name}' in {source_file} "
                            f"must be a dict, got {type(params).__name__}"
                        )
                    instances.append(cls(**params))
            else:
                raise SubAgentLoadError(
                    f"Invalid middleware spec in {source_file}: "
                    f"expected str or dict, got {type(item).__name__}"
                )
        return instances


class SubAgentLoader:
    """Parse .harness/subagents/*.yaml into subagent definitions.

    Each .yaml file defines one subagent with:
    - name, description, system_prompt (required)
    - tools, model, middleware (optional)

    Tools are resolved via ToolRegistry.
    Middleware is resolved via MiddlewareResolver.

    Usage::

        registry = ToolRegistry()
        registry.register(read_file_tool)
        registry.register(grep_tool)

        loader = SubAgentLoader(Path("my-project/.harness"), registry)
        subagents = loader.load_all()
        # subagents = [
        #     {"name": "code-reviewer", "description": "...", ...},
        #     {"name": "api-tester", "description": "...", ...},
        # ]
    """

    REQUIRED_FIELDS = ("name", "description", "system_prompt")

    def __init__(
        self,
        harness_dir: Path,
        tool_registry: ToolRegistry,
    ) -> None:
        """Create a subagent loader for the given ``.harness/`` directory.

        Args:
            harness_dir: Path to the ``.harness/`` directory.
            tool_registry: ToolRegistry for resolving tool name references.
        """
        self.harness_dir = harness_dir
        self.subagents_dir = harness_dir / "subagents"
        self.tool_registry = tool_registry
        self._middleware_resolver = MiddlewareResolver()

    @property
    def middleware_resolver(self) -> MiddlewareResolver:
        """Expose the middleware resolver for external registration."""
        return self._middleware_resolver

    @property
    def exists(self) -> bool:
        """Check whether the subagents/ directory exists."""
        return self.subagents_dir.is_dir()

    def load_all(self) -> list[dict[str, Any]]:
        """Load all subagent definitions from .harness/subagents/.

        Returns:
            List of subagent definition dicts ready for SubAgentMiddleware.

        Raises:
            SubAgentLoadError: If a YAML file is invalid or missing required fields.
        """
        if not self.exists:
            return []

        definitions: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for file in sorted(self.subagents_dir.glob("*.yaml")):
            definition = self._load_one(file)

            # Check for duplicate names
            name = definition["name"]
            if name in seen_names:
                raise SubAgentLoadError(
                    f"Duplicate subagent name '{name}' in {file.name}. "
                    f"Subagent names must be unique across all files."
                )
            seen_names.add(name)

            definitions.append(definition)

        return definitions

    def load_all_graceful(self) -> tuple[list[dict[str, Any]], list[str]]:
        """Load subagent definitions, collecting errors per-file.

        Unlike load_all(), this does not abort on the first error.
        Valid subagents are returned even when some files fail to load.

        Returns:
            Tuple of (definitions, errors) where errors contains
            human-readable messages for each failed file.
        """
        if not self.exists:
            return [], []

        definitions: list[dict[str, Any]] = []
        errors: list[str] = []
        seen_names: set[str] = set()

        for file in sorted(self.subagents_dir.glob("*.yaml")):
            try:
                definition = self._load_one(file)
            except SubAgentLoadError as e:
                errors.append(str(e))
                continue

            name = definition["name"]
            if name in seen_names:
                errors.append(
                    f"Duplicate subagent name '{name}' in {file.name} — skipped"
                )
                continue
            seen_names.add(name)
            definitions.append(definition)

        return definitions, errors

    def _load_one(self, file: Path) -> dict[str, Any]:
        """Load and validate a single subagent definition file.

        Args:
            file: Path to a .yaml subagent definition file.

        Returns:
            A validated subagent definition dict.

        Raises:
            SubAgentLoadError: If parse fails or required fields are missing.
        """
        # 1. Parse YAML
        try:
            raw_text = file.read_text(encoding="utf-8")
            raw = yaml.safe_load(raw_text) or {}
        except yaml.YAMLError as e:
            raise SubAgentLoadError(
                f"Failed to parse {file.name}: {e}"
            ) from e

        # 2. Validate raw is a dict
        if not isinstance(raw, dict):
            raise SubAgentLoadError(
                f"Invalid subagent definition in {file.name}: "
                f"expected a mapping, got {type(raw).__name__}"
            )

        # 3. Validate required fields
        missing: list[str] = []
        for field in self.REQUIRED_FIELDS:
            if field not in raw or not raw[field]:
                missing.append(field)
        if missing:
            raise SubAgentLoadError(
                f"Missing required fields in {file.name}: {missing}"
            )

        # 4. Validate name is a valid identifier
        name = raw["name"]
        if not isinstance(name, str) or not name:
            raise SubAgentLoadError(
                f"Subagent name in {file.name} must be a non-empty string"
            )

        # 5. Resolve tools
        tool_names: list[str] = raw.get("tools", [])
        if not isinstance(tool_names, list):
            raise SubAgentLoadError(
                f"'tools' in {file.name} must be a list, "
                f"got {type(tool_names).__name__}"
            )
        tools = self._resolve_tools(tool_names, file.name)

        # 6. Resolve middleware
        middleware_raw: list[Any] = raw.get("middleware", [])
        if not isinstance(middleware_raw, list):
            raise SubAgentLoadError(
                f"'middleware' in {file.name} must be a list, "
                f"got {type(middleware_raw).__name__}"
            )
        middleware = self._middleware_resolver.resolve(
            middleware_raw, file.name
        )

        # 7. Build definition
        return {
            "name": name,
            "description": raw["description"],
            "system_prompt": raw["system_prompt"],
            "tools": tools,
            "model": raw.get("model", "deepseek-v4-flash"),
            "middleware": middleware,
        }

    def _resolve_tools(
        self, tool_names: list[str], source_file: str
    ) -> list[Any]:
        """Resolve tool names to tool objects via ToolRegistry.

        Args:
            tool_names: List of tool names from YAML.
            source_file: YAML file name (for error messages).

        Returns:
            List of BaseTool instances.

        Raises:
            SubAgentLoadError: If a tool is not found in the registry.
        """
        tools: list[Any] = []
        for name in tool_names:
            try:
                tool = self.tool_registry.get(name)
                tools.append(tool)
            except Exception as exc:
                available = [
                    t["name"] for t in self.tool_registry.list_tools()
                ]
                raise SubAgentLoadError(
                    f"Tool '{name}' in {source_file} not found in registry. "
                    f"Available tools: {available}"
                ) from exc
        return tools

    def list_subagents(self) -> list[SubAgentInfo]:
        """List registered subagents (without resolving tools).

        Returns:
            List of SubAgentInfo with name, source_file, description, and
            tool_count. Empty list if the subagents dir does not exist.
        """
        if not self.exists:
            return []

        result: list[SubAgentInfo] = []
        for file in sorted(self.subagents_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                # Skip unparseable files in list mode
                continue

            if not isinstance(raw, dict):
                continue

            tool_names = raw.get("tools", [])
            if not isinstance(tool_names, list):
                tool_names = []

            result.append(
                SubAgentInfo(
                    name=raw.get("name", file.stem),
                    source_file=file.name,
                    description=raw.get("description", ""),
                    tool_count=len(tool_names),
                )
            )
        return result
