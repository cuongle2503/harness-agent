---
name: plan
description: Create an implementation plan for a feature or refactoring task
---

# /plan

## Overview

Use this command to create a detailed implementation plan before writing code.

## When to Use

- New feature implementation
- Complex refactoring
- Architectural changes
- Any task affecting 2+ files with dependencies

## How It Works

1. Spawns the **planner** subagent
2. Analyzes requirements and existing codebase
3. Produces a phased implementation plan
4. Identifies dependencies, risks, and testing strategy

## Output Format

The planner produces:

```markdown
# Implementation Plan: [Feature Name]

## Overview
## Requirements
## Architecture Changes
## Implementation Steps (Phased)
## Testing Strategy
## Risks & Mitigations
## Success Criteria
```

## Example

```
/plan Add agent memory system with vector store and conversation buffer
```
