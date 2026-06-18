---
description: Review code for quality, security, and best practices
arguments:
  - name: path
    description: File or directory to review
    required: false
---

Use the **code-reviewer** agent to review the code at `$path` (or the current changes if no path is given). Focus on security, code quality, architecture, and Pythonic patterns. Report findings with severity levels.
