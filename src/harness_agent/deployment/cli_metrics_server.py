"""Lightweight HTTP server for CLI agent metrics monitoring.

Acts as a **session aggregator**: multiple CLI instances push metrics to a single
server on one port. The dashboard shows all sessions with a dropdown selector.

Runs in a daemon thread alongside the interactive CLI, serving
/metrics, /dashboard, /health, /ui, and push endpoints. Uses only stdlib
so there are zero additional dependencies.

Usage::

    # Host mode (first CLI): starts the server
    server, port = start_metrics_server(metrics, start_time, memory, port=2025)

    # Client mode (subsequent CLIs): push via HTTP POST to existing server
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import threading
import time
import types
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.monitoring.dashboard import (
    build_dashboard_response,
)
from harness_agent.monitoring.metrics import AgentMetrics


def _load_static_html(filename: str) -> str:
    """Load a static HTML file from the ui/ directory (cached at import time)."""
    ui_dir = Path(__file__).resolve().parent / "ui"
    html_path = ui_dir / filename
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return f"<html><body><h1>{filename} not found</h1></body></html>"


_DASHBOARD_HTML: str = _load_static_html("dashboard.html")
_ACTIVITY_HTML: str = _load_static_html("activity.html")

# ---------------------------------------------------------------------------
# Per-session storage — one aggregator serves many CLI instances
# ---------------------------------------------------------------------------

_MAX_TOOL_HISTORY = 100
_MAX_ACTIVITY = 200

_METRICS_FIELD_MAP: dict[str, str] = {
    "model_calls": "model_calls",
    "model_errors": "model_errors",
    "token_usage_total": "total_tokens",
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "tool_calls": "tool_calls",
    "tool_errors": "tool_errors",
    "total_tasks": "total_tasks",
    "completed_tasks": "completed_tasks",
    "subagent_spawn_count": "subagent_spawns",
    "subagent_completes": "subagent_completes",
    "hitl_approvals": "hitl_approvals",
    "hitl_rejections": "hitl_rejections",
}

_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()


def _get_or_create_session(session_id: str) -> dict[str, Any]:
    """Get or create a session data bag (not thread-safe — caller must lock)."""
    if session_id not in _sessions:
        _sessions[session_id] = {
            "session_id": session_id,
            "name": session_id,
            "agent_id": session_id,
            "pid": os.getpid(),
            "started_at": time.time(),
            "metrics": AgentMetrics(),
            "tool_history": [],
            "activity_log": [],
            "session_metrics": {},
            "memory": None,
        }
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# Public recording API (host mode — called directly from CLI in same process)
# ---------------------------------------------------------------------------


def record_tool_history(
    name: str,
    input_str: str,
    output_str: str,
    latency_ms: float,
    success: bool = True,
    *,
    session_id: str = "default",
) -> None:
    """Record a tool call to the shared history (called by CLI agent)."""
    with _sessions_lock:
        s = _get_or_create_session(session_id)
        s["tool_history"].append({
            "name": name,
            "input": input_str[:200],
            "output": output_str[:500],
            "latency_ms": round(latency_ms, 2),
            "success": success,
            "timestamp": time.time(),
        })
        if len(s["tool_history"]) > _MAX_TOOL_HISTORY:
            s["tool_history"].pop(0)


def record_activity(
    event_type: str,
    *,
    session_id: str = "default",
    **kwargs: Any,
) -> None:
    """Record an activity event (called by CLI agent)."""
    with _sessions_lock:
        s = _get_or_create_session(session_id)
        entry: dict[str, Any] = {"type": event_type, "time": time.monotonic()}
        entry.update(kwargs)
        s["activity_log"].append(entry)
        if len(s["activity_log"]) > _MAX_ACTIVITY:
            s["activity_log"].pop(0)


def record_session(
    thread_id: str,
    *,
    session_id: str = "default",
    **kwargs: Any,
) -> None:
    """Upsert per-thread metrics within a CLI session."""
    with _sessions_lock:
        s = _get_or_create_session(session_id)
        sm = s["session_metrics"]
        sess = sm.get(thread_id)
        if sess is None:
            sess = {
                "thread_id": thread_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "api_calls": 0,
                "tool_calls": 0,
                "turns": 0,
                "created_at": time.time(),
            }
            sm[thread_id] = sess
        for key, value in kwargs.items():
            if key in ("input_tokens", "output_tokens", "api_calls", "tool_calls", "turns"):
                sess[key] = sess.get(key, 0) + int(value)
            else:
                sess[key] = value
        sess["last_active"] = time.monotonic()


def register_session(session_id: str, name: str, agent_id: str, pid: int = 0) -> None:
    """Register a CLI session (called via POST /register or host init)."""
    with _sessions_lock:
        s = _get_or_create_session(session_id)
        s["name"] = name or agent_id
        s["agent_id"] = agent_id
        s["pid"] = pid or os.getpid()
    print(f"[aggregator] session registered: {session_id} (pid={s['pid']}, "
          f"total={len(_sessions)})")


def unregister_session(session_id: str) -> None:
    """Remove a CLI session (called via POST /unregister or atexit)."""
    with _sessions_lock:
        _sessions.pop(session_id, None)


def get_session_ids() -> list[str]:
    """Return sorted list of active session IDs."""
    with _sessions_lock:
        return sorted(_sessions.keys())


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler — serves GET (dashboard) and POST (client push)."""

    # Injected by factory
    metrics: AgentMetrics
    start_time: float
    memory: HybridMemory | None
    agent_id: str
    sandbox_type: str
    session_id: str = "default"
    harness_info: types.MappingProxyType[str, Any] = types.MappingProxyType({})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}

    def _query_param(self, key: str, default: str = "") -> str:
        try:
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            return qs.get(key, [default])[0]
        except Exception:
            return default

    def _resolve_session_id(self) -> str:
        """Resolve session_id from query param, falling back to first available."""
        sid = self._query_param("session_id")
        if sid:
            return sid
        ids = get_session_ids()
        return ids[0] if ids else "default"

    def _uptime(self) -> float:
        return time.monotonic() - self.start_time

    def _get_session(self, session_id: str) -> dict[str, Any]:
        with _sessions_lock:
            return _sessions.get(session_id, {})

    # ------------------------------------------------------------------
    # Route dispatch
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip("/") or "/"

        routes: dict[str, Any] = {
            "/health": self._handle_health,
            "/metrics": self._handle_metrics,
            "/dashboard": self._handle_dashboard,
            "/tool-history": self._handle_tool_history,
            "/activity": self._handle_activity,
            "/sessions": self._handle_sessions,
            "/registry": self._handle_registry,
            "/harness": self._handle_harness,
            "/ui": self._handle_ui,
            "/ui/activity": self._handle_ui_activity,
            "/": self._handle_root,
        }

        handler = routes.get(path)
        if handler:
            try:
                handler()
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self) -> None:
        from urllib.parse import urlparse
        path = urlparse(self.path).path.rstrip("/") or "/"

        post_routes: dict[str, Any] = {
            "/register": self._handle_post_register,
            "/unregister": self._handle_post_unregister,
            "/push/tool-history": self._handle_post_tool_history,
            "/push/activity": self._handle_post_activity,
            "/push/session": self._handle_post_session,
            "/push/metrics": self._handle_post_metrics,
        }

        handler = post_routes.get(path)
        if handler:
            try:
                handler()
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e)}, status=500)
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ------------------------------------------------------------------
    # GET handlers (all support ?session_id= filter)
    # ------------------------------------------------------------------

    def _handle_health(self) -> None:
        self._send_json({
            "status": "healthy",
            "agent_id": self.agent_id,
            "sandbox_type": self.sandbox_type,
        })

    def _handle_metrics(self) -> None:
        sid = self._resolve_session_id()
        s = self._get_session(sid)
        metrics = s.get("metrics") if s else None
        data = metrics.to_dict() if metrics else {}
        self._send_json(data)

    def _handle_dashboard(self) -> None:
        sid = self._resolve_session_id()
        s = self._get_session(sid)
        metrics = s.get("metrics") if s else None
        if metrics is None:
            self._send_json({"error": "session not found"}, status=404)
            return
        uptime = self._uptime()
        memory_count = len(self.memory) if self.memory else 0
        response = build_dashboard_response(
            metrics=metrics,
            uptime_seconds=uptime,
            memory_item_count=memory_count,
        )
        self._send_json(response.model_dump())

    def _handle_tool_history(self) -> None:
        sid = self._resolve_session_id()
        s = self._get_session(sid)
        history = s.get("tool_history", []) if s else []
        count = 20
        with contextlib.suppress(ValueError):
            count = int(self._query_param("count", "20"))
        self._send_json(history[-count:])

    def _handle_activity(self) -> None:
        sid = self._resolve_session_id()
        s = self._get_session(sid)
        log = s.get("activity_log", []) if s else []
        count = 50
        with contextlib.suppress(ValueError):
            count = int(self._query_param("count", "50"))
        self._send_json(log[-count:])

    def _handle_sessions(self) -> None:
        sid = self._resolve_session_id()
        s = self._get_session(sid)
        sm = s.get("session_metrics", {}) if s else {}
        self._send_json(
            sorted(
                sm.values(),
                key=lambda x: x.get("last_active", 0),
                reverse=True,
            )
        )

    def _handle_registry(self) -> None:
        """Return all active CLI sessions."""
        result = []
        with _sessions_lock:
            for sid, s in _sessions.items():
                result.append({
                    "session_id": sid,
                    "name": s.get("name", sid),
                    "agent_id": s.get("agent_id", ""),
                    "pid": s.get("pid", 0),
                    "started_at": s.get("started_at", 0),
                })
        self._send_json(result)

    def _handle_harness(self) -> None:
        """Return harness configuration info (skills, rules, hooks, subagents)."""
        info = self.harness_info if hasattr(self.harness_info, "get") else {}
        self._send_json({
            "skills": info.get("skills", []),
            "rules": info.get("rules", []),
            "hooks": info.get("hooks", []),
            "subagents": info.get("subagents", []),
        })

    def _handle_ui(self) -> None:
        html = self._inject_harness_info(_DASHBOARD_HTML)
        self._send_html(html)

    def _handle_ui_activity(self) -> None:
        html = self._inject_harness_info(_ACTIVITY_HTML)
        self._send_html(html)

    def _inject_harness_info(self, html: str) -> str:
        """Inject harness info into HTML so counts show immediately."""
        info = self.harness_info if hasattr(self.harness_info, "get") else {}
        skills_n = len(info.get("skills", []))
        rules_n = len(info.get("rules", []))
        hooks_n = len(info.get("hooks", []))
        subagents_n = len(info.get("subagents", []))
        # Replace the initial "0 skills", "0 subagents" etc. with real counts
        html = html.replace(
            'id="nd-skill-info">0 skills<',
            f'id="nd-skill-info">{skills_n} skills<',
        )
        html = html.replace(
            'id="nd-subagent-info">0 subagents<',
            f'id="nd-subagent-info">{subagents_n} subagents<',
        )
        html = html.replace(
            'id="nd-rule-info">0 rules<',
            f'id="nd-rule-info">{rules_n} rules<',
        )
        html = html.replace(
            'id="nd-hook-info">0 hooks<',
            f'id="nd-hook-info">{hooks_n} hooks<',
        )
        return html

    def _handle_root(self) -> None:
        self.send_response(302)
        self.send_header("Location", "/ui")
        self.end_headers()

    # ------------------------------------------------------------------
    # POST handlers — client CLI pushes data to aggregator
    # ------------------------------------------------------------------

    def _handle_post_register(self) -> None:
        body = self._read_body()
        sid = body.get("session_id") or uuid.uuid4().hex[:8]
        name = body.get("name", sid)
        agent_id = body.get("agent_id", sid)
        pid = body.get("pid", 0)
        # If session_id already taken by another process, make it unique
        with _sessions_lock:
            existing = _sessions.get(sid)
            if existing and existing.get("pid") != pid:
                sid = f"{sid}-{pid}"
        register_session(sid, name, agent_id, pid=pid)
        self._send_json({"session_id": sid, "status": "registered"})

    def _handle_post_unregister(self) -> None:
        body = self._read_body()
        sid = body.get("session_id", "")
        unregister_session(sid)
        self._send_json({"status": "unregistered"})

    def _handle_post_tool_history(self) -> None:
        body = self._read_body()
        sid = body.get("session_id", "default")
        record_tool_history(
            name=body.get("name", "?"),
            input_str=body.get("input_str", ""),
            output_str=body.get("output_str", ""),
            latency_ms=body.get("latency_ms", 0),
            success=body.get("success", True),
            session_id=sid,
        )
        with _sessions_lock:
            s = _get_or_create_session(sid)
            metrics = s["metrics"]
        metrics.record_tool_call(
            body.get("name", "?"),
            body.get("latency_ms", 0),
            success=body.get("success", True),
        )
        self._send_json({"status": "ok"})

    def _handle_post_activity(self) -> None:
        body = self._read_body()
        sid = body.pop("session_id", "default")
        event_type = body.pop("event_type", "unknown")
        record_activity(event_type, session_id=sid, **body)
        self._send_json({"status": "ok"})

    def _handle_post_session(self) -> None:
        body = self._read_body()
        sid = body.pop("session_id", "default")
        thread_id = body.pop("thread_id", "")
        record_session(thread_id, session_id=sid, **body)
        self._send_json({"status": "ok"})

    def _handle_post_metrics(self) -> None:
        body = self._read_body()
        sid = body.get("session_id", "default")
        with _sessions_lock:
            s = _get_or_create_session(sid)
            metrics_data = body.get("metrics", {})
            m = s["metrics"]
            for dict_key, attr_name in _METRICS_FIELD_MAP.items():
                val = metrics_data.get(dict_key, 0)
                if val:
                    setattr(m, attr_name, getattr(m, attr_name, 0) + int(val))
        self._send_json({"status": "ok"})


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def start_metrics_server(
    metrics: AgentMetrics,
    start_time: float,
    memory: HybridMemory | None = None,
    *,
    port: int = 2025,
    agent_id: str = "harness-agent-cli",
    sandbox_type: str = "docker",
    session_name: str = "",
    session_id: str = "",
    harness_info: dict[str, Any] | None = None,
) -> tuple[HTTPServer, int]:
    """Start a background metrics HTTP aggregator server.

    Args:
        metrics: Shared AgentMetrics instance (host CLI records to it).
        start_time: ``time.monotonic()`` value from CLI startup.
        memory: Optional HybridMemory for the memory panel.
        port: TCP port to listen on (default 2025).
        agent_id: Agent identifier for health checks.
        sandbox_type: Sandbox type for health checks.
        session_name: Human-readable label for the UI session selector.
        session_id: Unique session identifier (auto-generated if empty).
        harness_info: Dict with keys ``skills``, ``rules``, ``hooks``,
            ``subagents`` — each a list of name strings or info dicts.

    Returns:
        Tuple of (running HTTPServer, actual_port_bound).

    Raises:
        OSError: If the port cannot be bound.
    """
    name = session_name or os.environ.get("HARNESS_SESSION_NAME", "")
    sid = session_id or name or agent_id

    # Inject state into the handler class
    _MetricsHandler.metrics = metrics
    _MetricsHandler.start_time = start_time
    _MetricsHandler.memory = memory
    _MetricsHandler.agent_id = agent_id
    _MetricsHandler.sandbox_type = sandbox_type
    _MetricsHandler.session_id = sid
    _MetricsHandler.harness_info = types.MappingProxyType(harness_info or {})

    host = os.environ.get("HARNESS_MONITORING_HOST", "127.0.0.1")
    server = HTTPServer((host, port), _MetricsHandler)

    # Register AFTER successful bind (don't register if port is taken)
    register_session(sid, name, agent_id)
    with _sessions_lock:
        _sessions[sid]["metrics"] = metrics
    atexit.register(unregister_session, sid)

    thread = threading.Thread(
        target=server.serve_forever,
        name="cli-metrics-server",
        daemon=True,
    )
    thread.start()

    return server, port
