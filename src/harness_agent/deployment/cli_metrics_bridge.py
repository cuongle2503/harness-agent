"""Metrics bridge — routes metric recordings to host or client mode.

Host mode: direct function calls to cli_metrics_server.
Client mode: HTTP POST to an existing aggregator on localhost.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import os
import time
import urllib.request as _ur
from typing import Any

from harness_agent.deployment.cli_metrics_server import (
    record_activity,
    record_session,
    record_tool_history,
    start_metrics_server,
)
from harness_agent.deployment.cli_terminal import Color


class MetricsBridge:
    """Routes metric recordings to either direct calls (host) or HTTP POST (client)."""

    def __init__(
        self, session_id: str, *, http_port: int | None = None
    ) -> None:
        self.sid = session_id
        self._port = http_port
        self._url = f"http://127.0.0.1:{http_port}" if http_port else ""
        self._push_ok = True

    @property
    def is_host(self) -> bool:
        return self._port is None

    def tool_history(self, **kw: Any) -> None:
        if self._port:
            self._post("/push/tool-history", kw)
        else:
            record_tool_history(session_id=self.sid, **kw)

    def activity(self, event_type: str, **kw: Any) -> None:
        if self._port:
            self._post("/push/activity", {"event_type": event_type, **kw})
        else:
            record_activity(event_type, session_id=self.sid, **kw)

    def session(self, thread_id: str, **kw: Any) -> None:
        if self._port:
            self._post("/push/session", {"thread_id": thread_id, **kw})
        else:
            record_session(thread_id, session_id=self.sid, **kw)

    def push_metrics(self, metrics_dict: dict[str, Any]) -> None:
        """Push current metrics snapshot (client mode only)."""
        if not self._port:
            return
        self._post("/push/metrics", {"metrics": metrics_dict})

    def _post(self, path: str, data: dict[str, Any]) -> None:
        """Fire-and-forget HTTP POST to aggregator (no proxy)."""
        body = json.dumps({**data, "session_id": self.sid}).encode("utf-8")
        try:
            req = _ur.Request(
                self._url + path,
                data=body,
                headers={"Content-Type": "application/json"},
            )
            _no_proxy = _ur.ProxyHandler({})
            _ur.build_opener(_no_proxy).open(req, timeout=2)
        except Exception:
            if self._push_ok:
                self._push_ok = False
                print(
                    "\n  ⚠ Metrics push failed (proxy may block localhost "
                    "connections)"
                )


# ---------------------------------------------------------------------------
# Connection logic
# ---------------------------------------------------------------------------


def _try_client_mode(
    port: int, session_id: str, name: str, assistant_id: str
) -> tuple[MetricsBridge, str] | None:
    """Try to register as a client with an existing aggregator.

    Returns (bridge, actual_session_id) on success, None on failure.
    """
    url = f"http://127.0.0.1:{port}"
    _no_proxy = _ur.ProxyHandler({})
    _opener = _ur.build_opener(_no_proxy)
    try:
        body = json.dumps({
            "session_id": session_id,
            "name": name,
            "agent_id": assistant_id,
            "pid": os.getpid(),
        }).encode("utf-8")
        req = _ur.Request(
            f"{url}/register",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        resp = json.loads(_opener.open(req, timeout=3).read())
        actual_sid = resp.get("session_id", session_id)
        bridge = MetricsBridge(actual_sid, http_port=port)
        if actual_sid != session_id:
            note = f'session_id "{session_id}" taken, using "{actual_sid}"'
            print(f"\n  {Color.dim(note)}")
        print(
            f"\n  {Color.success('📊 Dashboard:')} "
            f"{Color.paint(f'http://127.0.0.1:{port}/ui', Color.CYAN)}"
        )
        msg = f'connected to existing aggregator as "{actual_sid}"'
        print(f"  {Color.dim(msg)}")
        atexit.register(unregister_from_aggregator, port, actual_sid)
        return bridge, actual_sid
    except Exception as e:
        msg = f"⚠ Cannot reach aggregator at http://127.0.0.1:{port}: {e}"
        print(f"\n  {Color.warn(msg)}")
        return None


def unregister_from_aggregator(port: int, session_id: str) -> None:
    """Notify aggregator that this session is gone (client mode)."""
    try:
        body = json.dumps({"session_id": session_id}).encode("utf-8")
        req = _ur.Request(
            f"http://127.0.0.1:{port}/unregister",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=2)
    except Exception:
        pass


def connect_metrics_aggregator(
    *,
    port: int,
    session_name: str,
    assistant_id: str,
    metrics: Any,
    memory: Any,
    start_time: float,
    harness_info: dict[str, Any],
) -> tuple[MetricsBridge | None, str, Any]:
    """Connect to the metrics aggregator (host or client mode).

    Returns (bridge_or_None, session_id, server_or_None).
    """
    env_port = os.environ.get("HARNESS_MONITORING_PORT")
    if env_port:
        with contextlib.suppress(ValueError):
            port = int(env_port)

    name = session_name or os.environ.get("HARNESS_SESSION_NAME", "")
    session_id = name or f"{assistant_id}-{os.getpid()}"

    _no_proxy = _ur.ProxyHandler({})
    _opener = _ur.build_opener(_no_proxy)

    aggregator_alive = False
    for attempt in range(5):
        try:
            _opener.open(f"http://127.0.0.1:{port}/health", timeout=1)
            aggregator_alive = True
            break
        except Exception:
            if attempt < 4:
                time.sleep(0.5)

    # Try client mode first
    if aggregator_alive:
        result = _try_client_mode(port, session_id, name, assistant_id)
        if result is not None:
            bridge, actual_sid = result
            return bridge, actual_sid, None

    # Host mode: start aggregator
    try:
        server, actual_port = start_metrics_server(
            metrics=metrics,
            start_time=start_time,
            memory=memory,
            port=port,
            agent_id=assistant_id,
            sandbox_type="docker",
            session_name=name,
            session_id=session_id,
            harness_info=harness_info,
        )
        bridge = MetricsBridge(session_id)
        url = f"http://127.0.0.1:{actual_port}/ui"
        print(
            f"\n  {Color.success('📊 Dashboard:')} "
            f"{Color.paint(url, Color.CYAN)}"
        )
        msg2 = f'aggregator started, session: "{session_id}"'
        print(f"  {Color.dim(msg2)}")
        return bridge, session_id, server
    except OSError:
        print(f"\n  {Color.dim(f'Port {port} in use, trying client mode...')}")
        result = _try_client_mode(port, session_id, name, assistant_id)
        if result is not None:
            bridge, actual_sid = result
            return bridge, actual_sid, None
        print(f"\n  {Color.warn('⚠ Dashboard server: port in use')}")
        print(f"  {Color.dim('Metrics and UI unavailable this session.')}")
        return None, session_id, None
