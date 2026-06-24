"""Streaming logic for CLI agent turns.

Provides TurnContext (shared hook/metrics helpers) and two streaming
functions: one for the CompiledStateGraph path, one for the manual
LLM-loop fallback.
"""

from __future__ import annotations

import json
import re
import sys
import time
import traceback as _traceback
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from harness_agent.deployment.cli_metrics_bridge import MetricsBridge
from harness_agent.deployment.cli_terminal import (
    Color,
    clear_indicator,
    debug_chunk,
    draw_tool_box_bottom,
    draw_tool_box_top,
    extract_chunk_text,
    reset_debug_chunk_count,
    run_tool_with_spinner,
    show_indicator,
)
from harness_agent.loaders.hook_loader import EventBus, HookEvent, HookResult
from harness_agent.monitoring.metrics import AgentMetrics

# ---------------------------------------------------------------------------
# TurnContext — shared hook/metrics logic for both streaming paths
# ---------------------------------------------------------------------------


@dataclass
class TurnContext:
    """Shared state and helpers for a single streaming turn.

    Eliminates duplication between graph-based and agent-based streaming
    by centralizing hook firing and metrics recording.
    """

    thread_id: str
    bridge: MetricsBridge | None
    metrics: AgentMetrics
    event_bus: EventBus
    llm: Any
    harness_rule_sources: list[str] = field(default_factory=list)
    harness_skill_names: list[str] = field(default_factory=list)
    _emitted_skills: set[str] = field(default_factory=set)

    def fire_hook(self, event: HookEvent, context: dict[str, Any]) -> HookResult:
        """Fire a hook event and emit activity for the Live Workflow UI."""
        result = self.event_bus.fire(event, context)
        if self.bridge:
            self.bridge.activity(
                "hook_fired",
                event=event.value,
                name=", ".join(result.messages) if result.messages else event.value,
                allowed=result.allowed,
            )
        return result

    def emit_llm_start(self) -> None:
        """Emit llm_start activity and fire PRE_LLM_CALL hook."""
        model_name = getattr(self.llm, "model_name", "?")
        if self.bridge:
            self.bridge.activity(
                "llm_start", model=model_name, thread=self.thread_id
            )
            if self.harness_rule_sources:
                self.bridge.activity("rule_applied", name="rules")

        self.fire_hook(
            HookEvent.PRE_LLM_CALL,
            {
                "session_id": self.thread_id,
                "model": model_name,
                "messages_count": 0,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def emit_skill_used(self, skill_name: str) -> None:
        """Emit skill_used activity, deduplicating within a turn."""
        key = skill_name.lower()
        if key in self._emitted_skills:
            return
        self._emitted_skills.add(key)
        if self.bridge:
            self.bridge.activity("skill_used", name=skill_name)

    def detect_skill_usage(self, user_input: str, response_text: str) -> None:
        """Detect which skills were activated and emit skill_used activities.

        Uses word-boundary regex matching against user input and LLM
        response to avoid false positives from short skill names.
        Skips skills already emitted earlier in the turn (e.g. via
        use_skill tool call or on_custom_event).
        """
        if not self.bridge or not self.harness_skill_names:
            return

        combined = (user_input + " " + response_text).lower()
        for skill_name in self.harness_skill_names:
            if skill_name.lower() in self._emitted_skills:
                continue
            pattern = r"\b" + re.escape(skill_name.lower()) + r"\b"
            if re.search(pattern, combined):
                self.emit_skill_used(skill_name)

    def emit_llm_end(self, elapsed_ms: int, *, success: bool = True) -> None:
        """Fire POST_LLM_CALL hook."""
        self.fire_hook(
            HookEvent.POST_LLM_CALL,
            {
                "session_id": self.thread_id,
                "model": getattr(self.llm, "model_name", "?"),
                "tokens_used": 0,
                "duration_ms": elapsed_ms,
                "success": success,
            },
        )

    def emit_tool_start(self, tool_name: str, tool_input: dict[str, Any]) -> HookResult:
        """Fire PRE_TOOL_CALL hook. Returns hook result (check .allowed)."""
        return self.fire_hook(
            HookEvent.PRE_TOOL_CALL,
            {
                "session_id": self.thread_id,
                "tool_name": tool_name,
                "tool_args": tool_input,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )

    def emit_tool_end(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        result_str: str,
        elapsed_ms: float,
        error: bool,
    ) -> None:
        """Fire POST_TOOL_CALL hook, record metrics, emit activity."""
        self.fire_hook(
            HookEvent.POST_TOOL_CALL,
            {
                "session_id": self.thread_id,
                "tool_name": tool_name,
                "tool_args": tool_input,
                "tool_result": result_str,
                "duration_ms": int(elapsed_ms),
                "success": not error,
            },
        )

        self.metrics.record_tool_call(tool_name, elapsed_ms, success=not error)

        if self.bridge:
            safe_input = (
                {k: v for k, v in tool_input.items() if k != "runtime"}
                if isinstance(tool_input, dict)
                else {}
            )
            self.bridge.tool_history(
                name=tool_name,
                input_str=json.dumps(safe_input, default=str, ensure_ascii=False),
                output_str=result_str[:500],
                latency_ms=elapsed_ms,
                success=not error,
            )
            self.bridge.activity(
                "tool_end", name=tool_name, latency_ms=round(elapsed_ms, 2)
            )

    def emit_error(self, error: Exception, messages_count: int, tool_count: int) -> None:
        """Fire ON_ERROR hook."""
        self.fire_hook(
            HookEvent.ON_ERROR,
            {
                "session_id": self.thread_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "traceback": _traceback.format_exc(),
                "context": {
                    "messages_count": messages_count,
                    "tool_count": tool_count,
                },
            },
        )


# ---------------------------------------------------------------------------
# Graph-based streaming (CompiledStateGraph from HarnessBuilder)
# ---------------------------------------------------------------------------


async def stream_turn_graph(
    graph: Any,
    messages: list[BaseMessage],
    config: RunnableConfig,
    ctx: TurnContext,
) -> tuple[str | None, list[BaseMessage]]:
    """Stream a turn using CompiledStateGraph.astream_events().

    Uses LangGraph's event-based streaming for token-level text AND
    tool-call visibility, rendered with Claude-style tool display boxes.
    """
    ctx.emit_llm_start()
    stream_start = time.perf_counter()
    final_text = ""
    tool_count = 0
    last_messages: list[BaseMessage] = list(messages)
    tool_state: dict[str, Any] | None = None

    try:
        graph_input: dict[str, Any] = {"messages": messages}
        graph_config = dict(config) if config else {}
        graph_config.setdefault("recursion_limit", 100)

        async for event in graph.astream_events(
            graph_input, graph_config, version="v2"
        ):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    content = extract_chunk_text(chunk)
                    if content:
                        sys.stdout.write(content)
                        sys.stdout.flush()
                        final_text += content

            elif kind == "on_tool_start":
                tool_count += 1
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})

                if tool_name == "task" and ctx.bridge:
                    subagent_name = (
                        tool_input.get("subagent_type", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)[:60]
                    )
                    ctx.bridge.activity(
                        "subagent_start",
                        name=subagent_name or "subagent",
                        input=str(tool_input)[:200],
                    )

                if tool_name == "use_skill" and ctx.bridge:
                    skill_name = (
                        tool_input.get("skill_name", "")
                        if isinstance(tool_input, dict)
                        else str(tool_input)[:60]
                    )
                    ctx.emit_skill_used(skill_name or "skill")

                pre_result = ctx.emit_tool_start(tool_name, tool_input)
                if not pre_result.allowed:
                    # NOTE: In graph mode, the tool has already been dispatched
                    # by LangGraph's internal executor. This check is cosmetic —
                    # it logs the block but cannot prevent execution. For actual
                    # tool blocking in graph mode, use interrupt_on config in
                    # create_deep_agent or HumanInTheLoopMiddleware.
                    blocked_msg = (
                        f"Tool '{tool_name}' blocked by hook (graph mode — "
                        "execution already dispatched): "
                        + "; ".join(pre_result.messages)
                    )
                    print(f"\n  {Color.warn('🚫 ' + blocked_msg)}")
                    continue

                print()
                box_w = draw_tool_box_top(tool_name, tool_input)
                tool_state = {
                    "name": tool_name,
                    "input": tool_input,
                    "box_w": box_w,
                    "start": time.perf_counter(),
                }

            elif kind == "on_tool_end":
                if tool_state is not None:
                    tool_name = tool_state["name"]
                    tool_input = tool_state["input"]
                    box_w = tool_state["box_w"]
                    t0 = tool_state["start"]
                    elapsed_ms = (time.perf_counter() - t0) * 1000

                    if tool_name == "task" and ctx.bridge:
                        ctx.bridge.activity(
                            "subagent_end",
                            name=(
                                tool_input.get("subagent_type", "")
                                if isinstance(tool_input, dict)
                                else "subagent"
                            ),
                            latency_ms=round(elapsed_ms, 2),
                        )

                    output = event.get("data", {}).get("output")

                    # Detect skill activation from SkillTool output header
                    if tool_name == "use_skill" and output:
                        out_str = str(output)
                        if out_str.startswith("# Skill: "):
                            header = out_str.split("\n", 1)[0]
                            detected = header.removeprefix("# Skill: ").strip()
                            if detected:
                                ctx.emit_skill_used(detected)
                    result_str = str(output) if output else "(no output)"
                    error = "error" in str(kind).lower()

                    ctx.emit_tool_end(
                        tool_name, tool_input, result_str, elapsed_ms, error
                    )
                    draw_tool_box_bottom(
                        box_w, result=result_str, elapsed_ms=elapsed_ms, error=error
                    )
                    tool_state = None

            elif kind == "on_chain_end":
                # Only capture messages from the root-level chain, not
                # intermediate nodes (tool nodes, model nodes, etc.)
                parent_ids = event.get("parent_ids", [])
                if not parent_ids:
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        last_messages = output.get("messages", last_messages)

            elif kind == "on_custom_event":
                # SkillsMiddleware emits custom events on skill activation
                custom_data = event.get("data", {})
                event_name = event.get("name", "")
                event_lower = event_name.lower()
                if ctx.bridge and any(
                    kw in event_lower
                    for kw in ("skill", "activate", "progressive", "disclosure")
                ):
                    skill_name = (
                        custom_data.get("skill_name", "")
                        if isinstance(custom_data, dict)
                        else str(custom_data)[:60]
                    )
                    ctx.emit_skill_used(skill_name or event_name)

    except Exception as e:
        ctx.emit_error(e, len(messages), tool_count)
        raise

    stream_elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
    ctx.emit_llm_end(stream_elapsed_ms)

    if final_text:
        print()

    # Detect skill usage from the user's last message and agent response
    user_input = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_input = str(msg.content) if msg.content else ""
            break
    ctx.detect_skill_usage(user_input, final_text)

    return (final_text if final_text else None, last_messages)


# ---------------------------------------------------------------------------
# Agent-based streaming (manual LLM loop, fallback when no graph)
# ---------------------------------------------------------------------------


async def stream_turn_agent(
    agent: Any,
    messages: list[BaseMessage],
    config: RunnableConfig,
    ctx: TurnContext,
    max_iterations: int,
) -> tuple[str | None, list[BaseMessage]]:
    """Manual LLM-loop streaming for basic HarnessAgent (no .harness/).

    Streams tokens from the LLM, resolves tool calls, executes tools
    with spinner display, and loops until no more tool calls or max
    iterations reached.
    """
    full_msgs = list(messages)
    if agent.system_prompt and (
        not full_msgs or not isinstance(full_msgs[0], SystemMessage)
    ):
        full_msgs.insert(0, SystemMessage(content=agent.system_prompt))

    llm_with_tools = agent.llm
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        reset_debug_chunk_count()

        accumulated: AIMessageChunk | None = None
        tool_calls_in_progress: dict[int, dict[str, Any]] = {}
        indicator_shown: str | None = None
        text_streamed: bool = False

        ctx.emit_llm_start()
        stream_start = time.perf_counter()

        async for chunk in llm_with_tools.astream(full_msgs, config):
            accumulated = (
                chunk if accumulated is None else accumulated + chunk  # type: ignore[operator]
            )

            content = extract_chunk_text(chunk)
            has_tool_calls = (
                hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks
            )

            debug_chunk(chunk, content)

            if content:
                clear_indicator(indicator_shown)
                indicator_shown = None
                sys.stdout.write(content)
                sys.stdout.flush()
                text_streamed = True

            if has_tool_calls:
                for tc_chunk in chunk.tool_call_chunks:
                    idx = (
                        tc_chunk.get("index", 0)
                        if isinstance(tc_chunk, dict)
                        else getattr(tc_chunk, "index", 0)
                    )
                    name = (
                        tc_chunk.get("name")
                        if isinstance(tc_chunk, dict)
                        else getattr(tc_chunk, "name", None)
                    )
                    args = (
                        tc_chunk.get("args")
                        if isinstance(tc_chunk, dict)
                        else getattr(tc_chunk, "args", None)
                    )
                    id_ = (
                        tc_chunk.get("id")
                        if isinstance(tc_chunk, dict)
                        else getattr(tc_chunk, "id", None)
                    )
                    if idx not in tool_calls_in_progress:
                        tool_calls_in_progress[idx] = {
                            "name": "", "args": "", "id": ""
                        }
                    if name:
                        tool_calls_in_progress[idx]["name"] += name
                    if args:
                        tool_calls_in_progress[idx]["args"] += args
                    if id_ and not tool_calls_in_progress[idx]["id"]:
                        tool_calls_in_progress[idx]["id"] = id_

                if indicator_shown != "planning":
                    clear_indicator(indicator_shown)
                    if text_streamed:
                        print()
                        text_streamed = False
                    show_indicator("planning")
                    indicator_shown = "planning"

            elif indicator_shown is None and not content:
                show_indicator("thinking")
                indicator_shown = "thinking"

        if indicator_shown:
            clear_indicator(indicator_shown)

        if accumulated is None:
            return ("", full_msgs)

        # Extract usage metadata
        usage_meta: dict[str, Any] = getattr(accumulated, "usage_metadata", None) or {}
        input_tokens = usage_meta.get("input_tokens", 0)
        output_tokens = usage_meta.get("output_tokens", 0)
        total_tokens = usage_meta.get("total_tokens", 0) or (input_tokens + output_tokens)

        stream_elapsed_ms = int((time.perf_counter() - stream_start) * 1000)
        ctx.emit_llm_end(stream_elapsed_ms)

        ctx.metrics.record_model_call(
            latency_ms=0.0,
            success=True,
            tokens=int(total_tokens),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
        )

        if (total_tokens or input_tokens or output_tokens) and ctx.bridge:
            ctx.bridge.session(
                ctx.thread_id,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                api_calls=1,
            )

        content = extract_chunk_text(accumulated)

        # Resolve tool calls
        resolved_tool_calls = None
        if tool_calls_in_progress:
            resolved_tool_calls = [
                {
                    "name": tc["name"],
                    "args": json.loads(tc["args"]) if tc["args"] else {},
                    "id": tc["id"] or f"call_{idx}",
                }
                for idx, tc in tool_calls_in_progress.items()
            ]
        elif hasattr(accumulated, "tool_calls") and accumulated.tool_calls:
            resolved_tool_calls = accumulated.tool_calls  # type: ignore[assignment]

        ai_msg: AIMessage
        if resolved_tool_calls:
            ai_msg = AIMessage(content=str(content), tool_calls=resolved_tool_calls)
        else:
            ai_msg = AIMessage(content=str(content))

        full_msgs.append(ai_msg)

        if not ai_msg.tool_calls:
            if ai_msg.content:
                print()
            # Detect skill usage from user input and response
            user_input = ""
            for m in messages:
                if hasattr(m, "type") and m.type == "human":
                    user_input = str(m.content) if m.content else ""
            ctx.detect_skill_usage(user_input, str(ai_msg.content))
            return (str(ai_msg.content), full_msgs)

        print()

        # Execute tools
        tool_msgs: list[Any] = []
        for tc in ai_msg.tool_calls:
            tool_name = tc.get("name", "unknown")
            tool_args = tc.get("args", {})
            tool_id = tc.get("id", "")

            pre_result = ctx.emit_tool_start(tool_name, tool_args)
            if not pre_result.allowed:
                blocked_msg = (
                    f"Tool '{tool_name}' blocked by hook: "
                    + "; ".join(pre_result.messages)
                )
                print(f"\n  {Color.warn('🚫 ' + blocked_msg)}")
                tool_msgs.append(ToolMessage(content=blocked_msg, tool_call_id=tool_id))
                continue

            if tool_name == "task" and ctx.bridge:
                subagent_name = (
                    tool_args.get("subagent_type", "")
                    if isinstance(tool_args, dict)
                    else ""
                )
                ctx.bridge.activity(
                    "subagent_start",
                    name=subagent_name or "subagent",
                    input=str(tool_args)[:200],
                )

            if tool_name == "use_skill" and ctx.bridge:
                skill_name = (
                    tool_args.get("skill_name", "")
                    if isinstance(tool_args, dict)
                    else ""
                )
                ctx.emit_skill_used(skill_name or "skill")

            box_w = draw_tool_box_top(tool_name, tool_args)

            tool = agent._tool_map.get(tool_name)
            error = False
            t0 = time.perf_counter()

            if tool is None:
                msg = f"Unknown tool: {tool_name}"
                error = True
            else:
                msg, error = await run_tool_with_spinner(tool, tool_args, box_w)

            elapsed_ms = (time.perf_counter() - t0) * 1000

            ctx.emit_tool_end(tool_name, tool_args, msg, elapsed_ms, error)

            if ctx.bridge:
                safe_args = (
                    {k: v for k, v in tool_args.items() if k != "runtime"}
                    if isinstance(tool_args, dict)
                    else {}
                )
                ctx.bridge.activity(
                    "tool_start",
                    name=tool_name,
                    input=json.dumps(safe_args, default=str)[:200],
                )

            draw_tool_box_bottom(box_w, result=msg, elapsed_ms=elapsed_ms, error=error)

            tool_msgs.append(ToolMessage(content=msg, tool_call_id=tool_id))

        full_msgs.extend(tool_msgs)

    print(f"\n  {Color.error('⚠ Max tool iterations reached')}")
    last_text = ""
    for msg in reversed(full_msgs):
        if isinstance(msg, AIMessage) and msg.content:
            last_text = str(msg.content)
            break
    # Detect skill usage at max-iterations exit
    user_input = ""
    for m in messages:
        if hasattr(m, "type") and m.type == "human":
            user_input = str(m.content) if m.content else ""
    ctx.detect_skill_usage(user_input, last_text)
    return (last_text, full_msgs)
