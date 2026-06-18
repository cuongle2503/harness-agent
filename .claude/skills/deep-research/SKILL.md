---
name: deep-research
description: Multi-source research workflow — search, deep read, cross-reference, and synthesize a cited report.
origin: harness-agent
---

# Deep Research

Multi-source research workflow for thorough, fact-checked investigations.

## When to Activate

- Researching a new technology or framework
- Answering complex architectural questions
- Gathering evidence for design decisions
- Comparing multiple approaches or tools

## Workflow

### Phase 1: Understand the Question
- Clarify scope and success criteria
- Break down into sub-questions
- Identify key search terms

### Phase 2: Multi-Source Search
- Code search (GitHub, PyPI)
- Documentation (official docs, readthedocs)
- Web search for current best practices
- Academic/technical papers when relevant

### Phase 3: Deep Read
- Read top sources thoroughly
- Extract key claims and patterns
- Note contradictions between sources

### Phase 4: Adversarial Verify
- Cross-reference claims across sources
- Check recency (prefer <1 year old for fast-moving tech)
- Verify code examples actually work
- Identify gaps and follow up

### Phase 5: Synthesize
- Structure findings logically
- Every claim must have a source
- Include code examples where applicable
- Note uncertainties and areas for further investigation

## Quality Rules
- Every factual claim must cite a source
- Cross-reference critical claims across 2+ sources
- Prefer primary sources (official docs) over secondary (blog posts)
- Flag speculative or uncertain claims explicitly
- Include date of access for web sources

## Output Format

```markdown
# Research: [Topic]

## Summary
[2-3 sentence executive summary]

## Findings
### [Finding 1]
- Claim: ...
- Sources: [link], [link]
- Confidence: High/Medium/Low

## Recommendations
## Sources
## Areas for Further Investigation
```
