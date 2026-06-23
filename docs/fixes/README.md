# Code Fixes — Phased Plan

Kết quả từ full source review (2026-06-23). Các issue được chia thành phase theo mức độ nghiêm trọng và thứ tự fix hợp lý.

| Phase | File | Scope | Priority |
|-------|------|-------|----------|
| 0 | [phase-0-critical.md](phase-0-critical.md) | CRITICAL — shell injection, mutable state, silent exceptions | Immediate |
| 1 | [phase-1-security.md](phase-1-security.md) | Security boundaries — path traversal, PII accumulation | This week |
| 2 | [phase-2-async-types.md](phase-2-async-types.md) | Async/sync mismatch, type safety, exception chaining | This week |
| 3 | [phase-3-dead-code.md](phase-3-dead-code.md) | Dead code, stubs returning fake results, unused exports | Next sprint |
| 4 | [phase-4-style-cleanup.md](phase-4-style-cleanup.md) | Style, imports, minor refactors | Backlog |
