"""
DESK Local Mission Control HTTP Server and Server-Sent Events (SSE) Engine.

Provides an event-driven, read-only monitoring interface bound strictly to 127.0.0.1,
enabling clients to observe real-time engineering execution, pipeline stages, metrics,
and acceptance verification.
Zero external dependencies.
"""

from __future__ import annotations

import errno
import http.server
import json
import os
import queue
import re
import socket
import sys
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from desk.runtime.events import Event, EventBus, get_event_bus
from desk.runtime.projection import ExecutionProjection, get_execution_projection
from desk.runtime.resource_profile import ResourceDetector

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 49630
MAX_PORT_ATTEMPTS = 11
SERVER_VERSION = "1.0.0"

# Path traversal rejection regex
PATH_TRAVERSAL_RE = re.compile(r"(\.\./|\.\.\\|\x00|[a-zA-Z]:[\\/])")


class DeskRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler implementing localhost security and the REST/SSE monitoring API."""

    server_version = f"DESK-MissionControl/{SERVER_VERSION}"

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP server request noise from stderr."""
        pass

    def _is_safe_origin(self) -> bool:
        """Validates that request comes strictly from localhost."""
        origin = self.headers.get("Origin") or self.headers.get("Host") or ""
        # Strip port if present
        host_part = origin.split("://")[-1].split(":")[0] if "://" in origin else origin.split(":")[0]
        return host_part in {"127.0.0.1", "localhost", ""}

    def _send_security_headers(self, content_type: str = "application/json") -> None:
        """Applies essential security headers for localhost isolation."""
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; img-src 'self' data:;")
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Last-Event-ID, Content-Type")

    @staticmethod
    def _sanitize_payload(obj: Any) -> Any:
        """Recursively masks sensitive tokens and keys in JSON dictionaries."""
        if isinstance(obj, dict):
            sanitized = {}
            for k, v in obj.items():
                lower_k = str(k).lower()
                if any(s in lower_k for s in ("secret", "token", "password", "api_key", "credential", "auth")):
                    sanitized[k] = "[REDACTED]"
                else:
                    sanitized[k] = DeskRequestHandler._sanitize_payload(v)
            return sanitized
        elif isinstance(obj, list):
            return [DeskRequestHandler._sanitize_payload(item) for item in obj]
        return obj

    def _send_json(self, status_code: int, data: Any) -> None:
        """Encodes and sends a JSON response with credential sanitization."""
        sanitized_data = self._sanitize_payload(data)
        encoded = json.dumps(sanitized_data, indent=2, default=str).encode("utf-8")
        self.send_response(status_code)
        self._send_security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        """Handles CORS preflight checks."""
        self.send_response(204)
        self._send_security_headers()
        self.end_headers()

    def do_POST(self) -> None:
        """Rejects state-mutating requests (strictly read-only dashboard)."""
        self.send_error(405, "Method Not Allowed: Mission Control is strictly read-only")

    def do_PUT(self) -> None:
        """Rejects state-mutating requests."""
        self.send_error(405, "Method Not Allowed: Mission Control is strictly read-only")

    def do_DELETE(self) -> None:
        """Rejects state-mutating requests."""
        self.send_error(405, "Method Not Allowed: Mission Control is strictly read-only")

    def do_GET(self) -> None:
        """Routes GET requests to API handlers or the Mission Control dashboard."""
        if not self._is_safe_origin():
            self._send_json(403, {"error": "Access forbidden: Unrecognized Origin / Host header"})
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Path traversal guard
        if PATH_TRAVERSAL_RE.search(path):
            self._send_json(400, {"error": "Invalid path: Potential path traversal detected"})
            return

        # Route matching
        if path in {"", "/"}:
            self._handle_dashboard()
        elif path in {"/api/status", "/api/v1/status"}:
            self._handle_status()
        elif path in {"/api/execution", "/api/v1/execution", "/api/executions", "/api/v1/executions"}:
            self._handle_executions()
        elif path in {"/api/events", "/api/v1/events"}:
            self._handle_events(query)
        elif path in {"/api/events/live", "/api/v1/events/stream"}:
            self._handle_sse_stream(query)
        elif path == "/api/rework/session":
            self._handle_rework_session(query)
        elif path == "/api/rework/issues":
            self._handle_rework_issues(query)
        elif path == "/api/rework/plan":
            self._handle_rework_plan(query)
        elif path == "/api/rework/history":
            self._handle_rework_history(query)
        elif path == "/api/v1/health":
            self._handle_health()
        elif path == "/api/v1/projects":
            self._handle_projects()
        elif path == "/api/v1/metrics":
            self._handle_metrics()
        elif path.startswith("/api/v1/executions/"):
            self._handle_execution_subroutes(path, query)
        else:
            self._send_json(404, {"error": f"Endpoint '{path}' not found"})

    def _handle_dashboard(self) -> None:
        """Serves the Mission Control single-page web app."""
        html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "assets", "index.html")
        if not os.path.exists(html_path):
            self._send_json(404, {"error": "Dashboard template not found on disk"})
            return

        try:
            with open(html_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self._send_security_headers("text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_json(500, {"error": f"Failed reading dashboard asset: {str(e)}"})

    def _handle_health(self) -> None:
        """Returns service health status."""
        self._send_json(200, {
            "status": "HEALTHY",
            "service": "DESK Mission Control",
            "version": SERVER_VERSION,
            "timestamp": time.time(),
        })

    def _handle_status(self) -> None:
        """Returns the consolidated execution state projection."""
        projection = get_execution_projection()
        summary = projection.get_summary()
        try:
            from desk.bridge import SessionRegistry
            summary["bridge"] = {
                "port": SessionRegistry.get_port(),
                "status": "CONFIGURED",
            }
        except Exception:
            summary["bridge"] = {"port": 49620, "status": "UNKNOWN"}
        self._send_json(200, summary)

    def _handle_events(self, query: Dict[str, List[str]]) -> None:
        """Returns paginated or full event stream of recent execution events."""
        last_id = query.get("since", [None])[0] or query.get("last_event_id", [None])[0]
        try:
            limit = min(500, max(1, int(query.get("limit", [100])[0])))
        except ValueError:
            limit = 100
        event_bus = get_event_bus()
        events = event_bus.get_events_since(last_id, limit=limit)
        self._send_json(200, [e.to_dict() for e in events])

    def _handle_projects(self) -> None:
        """Discovers available hardware projects under projects/."""
        projects_dir = "projects"
        results = []
        if os.path.exists(projects_dir) and os.path.isdir(projects_dir):
            for d in os.listdir(projects_dir):
                full_path = os.path.join(projects_dir, d)
                if os.path.isdir(full_path):
                    has_req = os.path.exists(os.path.join(full_path, "REQUIREMENTS.md"))
                    has_state = os.path.exists(os.path.join(full_path, "state"))
                    results.append({
                        "project_id": full_path.replace("\\", "/"),
                        "name": d,
                        "has_requirements": has_req,
                        "has_state": has_state,
                    })
        self._send_json(200, results)

    def _handle_metrics(self) -> None:
        """Returns physical host and container hardware telemetry."""
        profile = ResourceDetector.detect()
        self._send_json(200, profile.to_dict())

    def _handle_executions(self) -> None:
        """Returns list of active and recent execution sessions."""
        projection = get_execution_projection()
        self._send_json(200, [{
            "execution_id": projection.execution_id,
            "project_id": projection.project_id,
            "status": projection.status,
            "overall_progress": projection.calculate_overall_progress(),
            "start_time": projection.start_time,
            "completion_time": projection.completion_time,
            "current_stage": projection.current_stage,
            "is_active": projection.status == "RUNNING",
        }])

    def _handle_execution_subroutes(self, path: str, query: Dict[str, List[str]]) -> None:
        """Handles /api/v1/executions/{id}/* routes."""
        projection = get_execution_projection()
        parts = path.strip("/").split("/")
        # Expected: ["api", "v1", "executions", "<id>", optional subpath]
        if len(parts) < 4:
            self._send_json(404, {"error": "Invalid execution route"})
            return

        exec_id = parts[3]
        if exec_id != projection.execution_id and exec_id != "current":
            self._send_json(404, {"error": f"Execution ID '{exec_id}' not found"})
            return

        subroute = parts[4] if len(parts) > 4 else ""

        if subroute == "":
            self._send_json(200, projection.get_summary())
        elif subroute == "events":
            limit = int(query.get("limit", [100])[0]) if "limit" in query else 100
            self._send_json(200, projection.get_timeline(limit=limit))
        elif subroute == "logs":
            level = query.get("level", [None])[0]
            search = query.get("search", [None])[0]
            limit = int(query.get("limit", [200])[0]) if "limit" in query else 200
            self._send_json(200, projection.get_logs(level=level, search=search, limit=limit))
        elif subroute == "artifacts":
            # Collect checkpoints from stages
            artifacts = []
            for st in projection.stages.values():
                artifacts.extend(st.artifacts)
            self._send_json(200, artifacts)
        else:
            self._send_json(404, {"error": f"Subroute '{subroute}' not recognized for execution '{exec_id}'"})

    def _handle_sse_stream(self, query: Dict[str, List[str]]) -> None:
        """Streams real-time execution events via Server-Sent Events (SSE)."""
        last_id = self.headers.get("Last-Event-ID") or (query.get("last_event_id", [None])[0])
        event_bus = get_event_bus()

        self.send_response(200)
        self._send_security_headers("text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        event_queue: queue.Queue[Event] = queue.Queue(maxsize=100)

        def listener(ev: Event) -> None:
            try:
                event_queue.put_nowait(ev)
            except queue.Full:
                pass  # Drop oldest or backpressure if subscriber is slow

        event_bus.subscribe("*", listener)

        try:
            # 1. Send initial connection greeting / replay missed events
            missed = event_bus.get_events_since(last_id, limit=50)
            for ev in missed:
                data = json.dumps(ev.to_dict())
                msg = f"id: {ev.event_id}\nevent: message\ndata: {data}\n\n"
                self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()

            # 2. Main event loop with periodic keepalive heartbeats
            while True:
                try:
                    ev = event_queue.get(timeout=10.0)
                    data = json.dumps(ev.to_dict())
                    msg = f"id: {ev.event_id}\nevent: message\ndata: {data}\n\n"
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Send ping heartbeat
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected gracefully
            pass
        finally:
            event_bus.unsubscribe("*", listener)


class DeskThreadingHTTPServer(http.server.ThreadingHTTPServer):
    """Threading HTTP server that gracefully suppresses abrupt client disconnect traces."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10053, 10054):
            return
        super().handle_error(request, client_address)


class DeskServer:
    """Multi-threaded HTTP monitoring server manager."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.host = host
        self.requested_port = port
        self.actual_port = port
        self.server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    @property
    def url(self) -> str:
        """Returns the active server URL."""
        return f"http://{self.host}:{self.actual_port}"

    @property
    def is_running(self) -> bool:
        """Returns True if the server thread is active."""
        return self._is_running

    def start(self, background: bool = True) -> Tuple[str, int]:
        """
        Binds to an available port starting from requested_port and starts serving.
        Returns (url, actual_port).
        """
        if self._is_running:
            return self.url, self.actual_port

        current_port = self.requested_port
        attempts = 0
        server_instance: Optional[http.server.ThreadingHTTPServer] = None

        while attempts < MAX_PORT_ATTEMPTS:
            try:
                server_instance = DeskThreadingHTTPServer((self.host, current_port), DeskRequestHandler)
                self.actual_port = current_port
                break
            except (OSError, PermissionError) as e:
                # Catch port already in use or Windows reserved socket permissions
                err_code = getattr(e, "errno", None) or getattr(e, "winerror", None)
                if err_code in {errno.EADDRINUSE, errno.EACCES, 10048, 10013, 98} or isinstance(e, PermissionError):
                    current_port += 1
                    attempts += 1
                else:
                    raise

        if server_instance is None:
            raise RuntimeError(f"Failed to bind to any port in range {self.requested_port}..{current_port}")

        self.server = server_instance
        self._is_running = True

        if background:
            self._thread = threading.Thread(target=self._serve_loop, name="DESK-Server-Thread", daemon=True)
            self._thread.start()
        else:
            self._serve_loop()

        return self.url, self.actual_port

    def _serve_loop(self) -> None:
        """Internal server loop."""
        if not self.server:
            return
        try:
            self.server.serve_forever()
        except Exception:
            pass
        finally:
            self._is_running = False

    def stop(self) -> None:
        """Stops the server gracefully."""
        if self.server and self._is_running:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self._is_running = False


# Singleton server instance
_GLOBAL_SERVER: Optional[DeskServer] = None


def get_desk_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> DeskServer:
    """Returns or initializes the global server instance."""
    global _GLOBAL_SERVER
    if _GLOBAL_SERVER is None:
        _GLOBAL_SERVER = DeskServer(host=host, port=port)
    return _GLOBAL_SERVER
