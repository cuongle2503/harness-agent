# Changelog

All notable changes to the Harness Agent project.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-19

### Added
- Agent core with LangChain Runnable protocol (`HarnessAgent`)
- Multi-agent orchestration via LangGraph (`AgentOrchestrator`)
- Tool registry with MCP protocol support (`ToolRegistry`)
- Hybrid memory: key-value + vector store + conversation buffer (`HybridMemory`)
- Middleware pipeline: custom middleware, structured logging, tracing
- Streaming support for real-time token output
- Monitoring & observability: metrics, alerts, dashboard, debug mode
- Deployment: CLI agent, FastAPI server, Docker, multi-tenant support
- Security: HITL approval, PII sanitization, sandbox, subprocess safety
- Permission boundary and path traversal protection
- Agent sub-types: research agent, code agent
- Tool inventory: file tools, search tools, code tools
- Comprehensive test suite: 254+ tests, 95%+ coverage
- CI/CD pipeline configuration
- Regression test suite with 9 BUG cases
- Evaluation framework with 20+ test cases
- A/B testing framework for agent comparison
- Monthly review checklist and maintenance procedures
- Memory feedback loop system

### Changed
- Migrated all models from Claude/Anthropic to DeepSeek V4

### Fixed
- BUG-001: Empty input dict should not crash agent
- BUG-002: Non-list messages should not crash agent
- BUG-003: Empty messages list should produce output
- BUG-004: Missing messages key should not crash agent
- BUG-005: Delete during key iteration should not raise KeyError
- BUG-006: Clear then store should produce valid state
- BUG-007: Retrieve with k=0 should return empty, not error
- BUG-008: Duplicate tool registration should overwrite, not error
- BUG-009: Re-register after get-error should work

### Security
- No hardcoded secrets — all credentials via environment variables
- Input validation on all tool inputs via Pydantic
- Path traversal prevention in file tools
- Subprocess calls use list args (no shell injection)
- HITL approval for sensitive operations

[0.1.0]: https://github.com/cuongle2503/harness-agent/tree/v0.1.0
