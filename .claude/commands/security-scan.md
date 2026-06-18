---
description: Scan code for security vulnerabilities
arguments:
  - name: path
    description: File or directory to scan
    required: false
---

Use the **security-reviewer** agent to scan `$path` (or the whole project if no path is given). Check for: hardcoded secrets, injection risks, path traversal, unsafe deserialization, and MCP security issues. Report CRITICAL findings first.
