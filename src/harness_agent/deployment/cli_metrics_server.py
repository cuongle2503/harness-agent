"""Lightweight HTTP server for CLI agent metrics monitoring.

Runs in a daemon thread alongside the interactive CLI, serving
/metrics, /dashboard, /health, and /ui endpoints. Uses only stdlib
so there are zero additional dependencies.

Usage::

    server = start_metrics_server(metrics, start_time, memory, port=2025)
    # ... CLI runs ...
    server.shutdown()  # or just exit process (daemon thread dies)
"""

from __future__ import annotations

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from harness_agent.monitoring.dashboard import (
    build_dashboard_response,
)
from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.memory.hybrid_memory import HybridMemory


def _load_static_html(filename: str) -> str:
    """Load a static HTML file from the ui/ directory (cached at import time)."""
    ui_dir = Path(__file__).resolve().parent / "ui"
    html_path = ui_dir / filename
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return f"<html><body><h1>{filename} not found</h1></body></html>"


_DASHBOARD_HTML: str = _load_static_html("dashboard.html")
_ACTIVITY_HTML: str = _load_static_html("activity.html")

# Shared tool history (written by CLI agent, read by /tool-history endpoint)
_tool_history: list[dict[str, Any]] = []
_MAX_TOOL_HISTORY = 100


def record_tool_history(
    name: str, input_str: str, output_str: str,
    latency_ms: float, success: bool = True,
) -> None:
    """Record a tool call to the shared history (called by CLI agent)."""
    import time as _t
    _tool_history.append({
        "name": name,
        "input": input_str[:200],
        "output": output_str[:500],
        "latency_ms": round(latency_ms, 2),
        "success": success,
        "timestamp": _t.time(),
    })
    if len(_tool_history) > _MAX_TOOL_HISTORY:
        _tool_history.pop(0)


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP request handler that serves metrics JSON and dashboard UI.

    Injected class attributes (set by ``start_metrics_server``):
        metrics: AgentMetrics
        start_time: float
        memory: HybridMemory | None
        agent_id: str
        sandbox_type: str
    """

    # Injected by factory
    metrics: AgentMetrics
    start_time: float
    memory: HybridMemory | None
    agent_id: str
    sandbox_type: str

    # Suppress per-request log lines
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str, status: int = 200) -> None:
        """Send an HTML response."""
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _uptime(self) -> float:
        """Return uptime in seconds."""
        import time as _time
        return _time.monotonic() - self.start_time

    # ------------------------------------------------------------------
    # Route dispatch
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        """Route GET requests."""
        path = self.path.rstrip("/") or "/"

        routes: dict[str, Any] = {
            "/health": self._handle_health,
            "/metrics": self._handle_metrics,
            "/dashboard": self._handle_dashboard,
            "/tool-history": self._handle_tool_history,
            "/ui": self._handle_ui,
            "/ui/activity": self._handle_ui_activity,
            "/": self._handle_root,
        }

        handler = routes.get(path)
        if handler:
            handler()
        else:
            self._send_json({"error": "not found", "path": path}, status=404)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ------------------------------------------------------------------
    # Endpoint handlers
    # ------------------------------------------------------------------

    def _handle_health(self) -> None:
        self._send_json({
            "status": "healthy",
            "agent_id": self.agent_id,
            "sandbox_type": self.sandbox_type,
        })

    def _handle_metrics(self) -> None:
        data = self.metrics.to_dict()
        self._send_json(data)

    def _handle_dashboard(self) -> None:
        uptime = self._uptime()
        memory_count = len(self.memory) if self.memory else 0
        response = build_dashboard_response(
            metrics=self.metrics,
            uptime_seconds=uptime,
            memory_item_count=memory_count,
        )
        self._send_json(response.model_dump())

    def _handle_ui(self) -> None:
        self._send_html(_DASHBOARD_HTML)

    def _handle_ui_activity(self) -> None:
        self._send_html(_ACTIVITY_HTML)

    def _handle_tool_history(self) -> None:
        """Return recent tool calls with details."""
        count = 20
        try:
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            count = int(qs.get("count", [20])[0])
        except Exception:
            pass
        self._send_json(_tool_history[-count:])

    def _handle_root(self) -> None:
        self.send_response(302)
        self.send_header("Location", "/ui")
        self.end_headers()


def start_metrics_server(
    metrics: AgentMetrics,
    start_time: float,
    memory: HybridMemory | None = None,
    *,
    port: int = 2025,
    agent_id: str = "harness-agent-cli",
    sandbox_type: str = "docker",
) -> HTTPServer:
    """Start a background metrics HTTP server for the CLI agent.

    Args:
        metrics: Shared AgentMetrics instance (the CLI records to it).
        start_time: ``time.monotonic()`` value from CLI startup.
        memory: Optional HybridMemory for the memory panel.
        port: TCP port to listen on (default 2025).
        agent_id: Agent identifier for health checks.
        sandbox_type: Sandbox type for health checks.

    Returns:
        The running HTTPServer instance (call ``shutdown()`` to stop).
    """
    # Inject state into the handler class
    _MetricsHandler.metrics = metrics
    _MetricsHandler.start_time = start_time
    _MetricsHandler.memory = memory
    _MetricsHandler.agent_id = agent_id
    _MetricsHandler.sandbox_type = sandbox_type

    server = HTTPServer(("127.0.0.1", port), _MetricsHandler)

    thread = threading.Thread(
        target=server.serve_forever,
        name="cli-metrics-server",
        daemon=True,
    )
    thread.start()

    return server
