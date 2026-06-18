# ADR-005: Model Selection — DeepSeek V4 Family Strategy

> **Status**: ✅ Accepted
> **Date**: 2026-06-18
> **Phase**: 2 — Architecture & Design (formalizing Phase 0 decision)
> **Deciders**: harness-architect agent

---

## Context

Chọn model là quyết định nền tảng ảnh hưởng đến cost, latency, reasoning quality, và tool calling accuracy của toàn bộ hệ thống. Harness Agent là Coordinator Agent với 4 subagents — mỗi role có yêu cầu khác nhau về reasoning depth và tốc độ.

Quyết định model đã được thực hiện trong Phase 0 và validated trong Phase 1. ADR này formalize quyết định đó với rationale đầy đủ.

## Decision

**Chọn DeepSeek V4 family** — dùng `deepseek-v4-flash` cho hầu hết tác vụ, `deepseek-v4-pro` cho task cần deep reasoning.

### Model Assignment

```
┌─────────────────────────────────────────────────────────────┐
│                    Model Assignment Map                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Main Orchestrator ───────▶ deepseek-v4-flash               │
│  (plan, route, synthesize)  $0.14/M input, 2500 QPS         │
│                                                              │
│  Subagent: Researcher ────▶ deepseek-v4-flash               │
│  (search, fetch, summarize) $0.14/M input, fast              │
│                                                              │
│  Subagent: Reviewer ───────▶ deepseek-v4-flash              │
│  (read, lint, analyze)      $0.14/M input, fast              │
│                                                              │
│  Subagent: Coder ──────────▶ deepseek-v4-pro                │
│  (generate, refactor, test) $0.435/M input, best reasoning   │
│                                                              │
│  Subagent: Architect ──────▶ deepseek-v4-pro                │
│  (design, evaluate, decide) $0.435/M input, best reasoning   │
│                                                              │
│  Summarization ────────────▶ deepseek-v4-flash              │
│  (compact context)          $0.14/M input, 1M context        │
│                                                              │
│  Router / Classifier ──────▶ deepseek-v4-flash              │
│  (structured output)       $0.14/M input, fast               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Model Comparison

| Tiêu chí | deepseek-v4-pro | deepseek-v4-flash |
|----------|-----------------|-------------------|
| Complex reasoning | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Tool calling accuracy | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Cost efficiency | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Context window | 1M tokens | 1M tokens |
| Max output | 384K tokens | 384K tokens |
| Total params | 1.6T | 284B |
| Active params | 49B | 13B |
| Input (cache miss) | $0.435/1M | $0.14/1M |
| Input (cache hit) | $0.003625/1M | $0.0028/1M |
| Output | $0.87/1M | $0.28/1M |
| Concurrency | 500 QPS | 2,500 QPS |

### Why DeepSeek V4?

1. **1M context window** — cả hai model hỗ trợ 1M tokens → phù hợp với agent conversation dài
2. **384K max output** — đủ cho code generation dài, research reports, architecture docs
3. **Tool calling accuracy** — cả hai model ⭐⭐⭐⭐⭐ cho function calling
4. **Cost structure** — v4-flash rẻ hơn 3x so với v4-pro → dùng cho phần lớn task
5. **OpenAI-compatible API** — `langchain-deepseek` package, dễ migrate
6. **Model được release 2026-04-24** — state-of-the-art tại thời điểm xây dựng

### Model Selection Rules

```python
from langchain_deepseek import ChatDeepSeek

def select_model(role: str) -> ChatDeepSeek:
    """Chọn model dựa trên role của agent."""
    if role in ("coder", "architect"):
        # Task cần deep reasoning: code generation, system design
        return ChatDeepSeek(model="deepseek-v4-pro", temperature=0)
    else:
        # Task cần tốc độ + cost efficiency: orchestration, research, review, summarize
        return ChatDeepSeek(model="deepseek-v4-flash", temperature=0)
```

| Role | Model | Rationale |
|------|-------|-----------|
| **Main Orchestrator** | `deepseek-v4-flash` | Tool calling reliability + tốc độ + giá rẻ. Orchestration không cần deep reasoning. |
| **Coder** | `deepseek-v4-pro` | Code generation cần reasoning mạnh nhất. 1.6T params cho chất lượng code tốt nhất. |
| **Architect** | `deepseek-v4-pro` | Architecture decisions cần deep analysis, trade-off evaluation, multi-perspective reasoning. |
| **Researcher** | `deepseek-v4-flash` | Searching + synthesis. Cost efficient cho task đọc nhiều. |
| **Reviewer** | `deepseek-v4-flash` | Pattern matching + lint analysis. Không cần deep reasoning. |
| **Summarization** | `deepseek-v4-flash` | 1M context input, chỉ cần tóm tắt text. Giá rẻ $0.28/1M output. |

## Alternatives Considered

### 1. deepseek-v4-pro cho tất cả roles (Rejected)

**Mô tả**: Dùng model mạnh nhất cho mọi thứ.

**Pros**: Chất lượng cao nhất cho mọi task

**Cons**:
- Cost cao gấp 3x cho input ($0.435 vs $0.14)
- Cost cao gấp 3x cho output ($0.87 vs $0.28)
- Concurrency thấp hơn (500 vs 2500 QPS)
- Overkill cho task đơn giản: summarization, research, review không cần 1.6T params

**Lý do reject**: Lãng phí tài nguyên. Phần lớn task (orchestration, research, review, summarization) không cần deep reasoning.

### 2. Claude/Anthropic models (Rejected)

**Mô tả**: Dùng Claude Opus 4.8 cho task nặng, Sonnet 4.6 cho task nhẹ.

**Pros**: Anthropic models có chất lượng cao

**Cons**:
- Cost cao hơn đáng kể
- Context window nhỏ hơn (200K vs 1M)
- Không có model giá rẻ tương đương v4-flash
- API khác với OpenAI-compatible → cần adapter riêng

**Lý do reject**: DeepSeek V4 có 1M context window và cost structure tốt hơn cho agent use case.

### 3. OpenAI GPT models (Rejected)

**Mô tả**: Dùng GPT-4o / GPT-4o-mini.

**Pros**: Hệ sinh thái lớn, nhiều tooling

**Cons**:
- GPT-4o context 128K → quá nhỏ cho agent conversation dài
- GPT-4o-mini context 128K → same issue
- Cost không cạnh tranh với v4-flash ($0.14/1M)
- Không có model 1M context

**Lý do reject**: Context window 128K không đủ cho deep agent với conversation dài + memory + tool outputs.

## Consequences

### Positive
- ✅ **Cost-efficient**: 80% task dùng v4-flash ($0.14/1M); 20% dùng v4-pro ($0.435/1M)
- ✅ **1M context**: Đủ cho conversation dài, codebase lớn, multi-file operations
- ✅ **High concurrency**: v4-flash 2500 QPS → có thể spawn nhiều subagents song song
- ✅ **Tool calling excellence**: Cả hai model ⭐⭐⭐⭐⭐ cho function calling
- ✅ **Simple integration**: `langchain-deepseek` package, OpenAI-compatible API

### Negative
- ⚠️ **DeepSeek API dependency**: Single point of failure nếu DeepSeek API down
- ⚠️ **Model deprecation**: `deepseek-chat`/`deepseek-reasoner` deprecated 2026-07-24 — phải migrate trước hạn
- ⚠️ **Regional availability**: DeepSeek API có thể không available ở một số regions

### Mitigation
- **API dependency**: `ModelFallbackMiddleware` với retry 3 lần. Có thể thêm fallback model khác trong tương lai.
- **Model deprecation**: Đã dùng `deepseek-v4-flash`/`deepseek-v4-pro` — model mới nhất, không cần migrate.
- **Regional availability**: Dùng API qua proxy nếu cần.

---

## References

- [AIDLC Lifecycle §0.2](../guides/aidlc-lifecycle.md#02-model-selection-decision-matrix)
- [Harness Agent Requirements §9](../requirements/harness-agent-requirements.md#9-model-selection-summary)
- [DeepSeek V4 Documentation](https://api-docs.deepseek.com/)
