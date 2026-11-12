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

    def do_POST(self) -> None:
        """Handles telemetry ingestion from local tools, strictly read-only for PCB state."""
        if not self._is_safe_origin():
            self._send_json(403, {"error": "Access forbidden: Unrecognized Origin / Host header"})
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in {"/api/events", "/api/v1/events", "/api/telemetry", "/api/v1/telemetry"}:
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode("utf-8")) if body else {}
                event_bus = get_event_bus()
                ev = event_bus.emit(
                    event_type=data.get("event_type", "stage.progress"),
                    stage=data.get("stage", ""),
                    task=data.get("task", ""),
                    status=data.get("status", ""),
                    progress=data.get("progress"),
                    message=data.get("message", ""),
                    metrics=data.get("metrics"),
                    artifacts=data.get("artifacts"),
                    error=data.get("error"),
                    payload=data.get("payload", {})
                )
                self._send_json(200, {"status": "ok", "event_id": ev.event_id})
            except Exception as e:
                self._send_json(400, {"error": f"Invalid telemetry payload: {str(e)}"})
        else:
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
        elif path in {"/api/bridge", "/api/v1/bridge"}:
            self._handle_bridge()
        elif path in {"/api/sync", "/api/v1/sync"}:
            self._handle_sync(query)
        elif path in {"/api/project/select", "/api/v1/project/select"}:
            self._handle_project_select(query)
        elif path in {"/api/execution", "/api/v1/execution", "/api/executions", "/api/v1/executions"}:
            self._handle_executions()
        elif path in {"/api/events", "/api/v1/events"}:
            self._handle_events(query)
        elif path in {"/api/timeline", "/api/v1/timeline"}:
            limit = int(query.get("limit", [100])[0]) if "limit" in query else 100
            self._send_json(200, get_execution_projection().get_timeline(limit=limit))
        elif path in {"/api/logs", "/api/v1/logs"}:
            level = query.get("level", [None])[0]
            search = query.get("search", [None])[0]
            limit = int(query.get("limit", [200])[0]) if "limit" in query else 200
            self._send_json(200, get_execution_projection().get_logs(level=level, search=search, limit=limit))
        elif path in {"/api/events/live", "/api/v1/events/stream"}:
            self._handle_sse_stream(query)
        elif path in {"/api/rework/session", "/api/v1/rework/session"}:
            self._handle_rework_session(query)
        elif path in {"/api/rework/issues", "/api/v1/rework/issues"}:
            self._handle_rework_issues(query)
        elif path in {"/api/rework/plan", "/api/v1/rework/plan"}:
            self._handle_rework_plan(query)
        elif path in {"/api/rework/history", "/api/v1/rework/history"}:
            self._handle_rework_history(query)
        elif path in {"/api/route/progress", "/api/v1/route/progress"}:
            # Routing-stage status from state/route/*.json (progress, pre-flight, dense analysis); file-backed, no ECAD call.
            from desk.runtime.route_progress import load_route_progress
            proj_id = query.get("project", [get_execution_projection().project_id])[0]
            self._send_json(200, load_route_progress(proj_id))
        elif path == "/api/v1/health":
            self._handle_health()
        elif path in {"/api/projects", "/api/v1/projects"}:
            self._handle_projects()
        elif path in {"/api/metrics", "/api/v1/metrics"}:
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

    def _get_bridge_info(self) -> Dict[str, Any]:
        """Probes and returns the active EasyEDA Pro socket connection state."""
        try:
            from desk.bridge import SessionRegistry
            configured_port = SessionRegistry.get_port()
            candidate_ports = list(range(49620, 49630))
            active_port = SessionRegistry._probe_ports_concurrent(candidate_ports, timeout=0.02)
            is_listening = active_port is not None
            port = active_port or configured_port

            window_id = None
            proj_uuid = None
            try:
                from desk.rework import get_latest_rework_session
                r_sess = get_latest_rework_session(get_execution_projection().project_id)
                if r_sess:
                    window_id = r_sess.window_id
                    proj_uuid = r_sess.project_uuid
            except Exception:
                pass

            return {
                "port": port,
                "configured_port": configured_port,
                "actual_port": port,
                "status": "LISTENING" if is_listening else "DISCONNECTED",
                "listening": is_listening,
                "candidate_ports": candidate_ports,
                "mission_control_port": self.server.server_address[1] if self.server else 49630,
                "active_window": window_id,
                "project_uuid": proj_uuid,
                "last_probe_ts": time.time(),
                "instructions": (
                    f"EasyEDA Pro bridge is listening on port {port}."
                    if is_listening else
                    f"EasyEDA Pro bridge is not listening on ports 49620..49629. Open EasyEDA Pro Desktop or run EasyEDA Pro API Gateway to establish live bridge."
                )
            }
        except Exception as e:
            return {
                "port": 49620,
                "configured_port": 49620,
                "actual_port": 49620,
                "status": "DISCONNECTED",
                "listening": False,
                "candidate_ports": list(range(49620, 49630)),
                "mission_control_port": 49630,
                "error": str(e)
            }

    def _handle_bridge(self) -> None:
        """Returns the real-time probe status of the EasyEDA Pro bridge socket."""
        self._send_json(200, self._get_bridge_info())

    def _handle_sync(self, query: Dict[str, List[str]]) -> None:
        """Forces an on-disk artifact re-scan and state projection update."""
        projection = get_execution_projection()
        proj_id = query.get("project", [None])[0]
        projection.sync_from_project_artifacts(proj_id)
        get_event_bus().emit("project.synced", project_id=projection.project_id, message="Project artifacts synchronized from disk")
        summary = projection.get_summary()
        summary["bridge"] = self._get_bridge_info()
        self._send_json(200, summary)

    def _handle_project_select(self, query: Dict[str, List[str]]) -> None:
        """Switches active project and re-syncs state."""
        proj_id = query.get("project", [get_execution_projection().project_id])[0]
        projection = get_execution_projection()
        projection.set_project(proj_id)
        projection.sync_from_project_artifacts(proj_id)
        get_event_bus().emit("project.switched", project_id=proj_id, message=f"Switched active project to {proj_id}")
        summary = projection.get_summary()
        summary["bridge"] = self._get_bridge_info()
        self._send_json(200, summary)

    def _handle_status(self) -> None:
        """Returns the consolidated execution state projection."""
        projection = get_execution_projection()
        summary = projection.get_summary()
        summary["bridge"] = self._get_bridge_info()
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
        current_pid = get_execution_projection().project_id
        if os.path.exists(projects_dir) and os.path.isdir(projects_dir):
            for d in os.listdir(projects_dir):
                full_path = os.path.join(projects_dir, d).replace("\\", "/")
                if os.path.isdir(full_path):
                    has_req = os.path.exists(os.path.join(full_path, "REQUIREMENTS.md"))
                    has_state = os.path.exists(os.path.join(full_path, "state"))
                    has_dump = os.path.exists(os.path.join(full_path, "state", "pcb_dump.json"))
                    has_route = os.path.exists(os.path.join(full_path, "state", "route", "desk_route.ses"))
                    results.append({
                        "project_id": full_path,
                        "name": d,
                        "is_active": full_path == current_pid,
                        "has_requirements": has_req,
                        "has_state": has_state,
                        "has_pcb": has_dump,
                        "has_route": has_route,
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

    def _handle_rework_session(self, query: Dict[str, List[str]]) -> None:
        """Returns the active or latest rework session."""
        proj_id = query.get("project", [get_execution_projection().project_id])[0]
        try:
            from desk.rework import get_latest_rework_session
            session = get_latest_rework_session(proj_id)
            if session:
                self._send_json(200, session.__dict__)
            else:
                self._send_json(404, {"error": "No rework session found"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_rework_issues(self, query: Dict[str, List[str]]) -> None:
        """Returns the issues inventory for the active rework session."""
        proj_id = query.get("project", [get_execution_projection().project_id])[0]
        try:
            from desk.rework import get_latest_rework_session
            session = get_latest_rework_session(proj_id)
            path = None
            if session:
                path = os.path.join(session.project_path, "state", "rework", session.session_id, "issue_inventory.json")
            if not path or not os.path.exists(path):
                # Search all rework subdirs
                rw_dir = os.path.join(proj_id, "state", "rework")
                if os.path.exists(rw_dir):
                    for sub in os.listdir(rw_dir):
                        candidate = os.path.join(rw_dir, sub, "issue_inventory.json")
                        if os.path.exists(candidate):
                            path = candidate
                            break
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    issues = json.load(f)
                self._send_json(200, issues)
            else:
                self._send_json(200, [])
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_rework_plan(self, query: Dict[str, List[str]]) -> None:
        """Returns the repair plan for the active rework session."""
        proj_id = query.get("project", [get_execution_projection().project_id])[0]
        try:
            from desk.rework import get_latest_rework_session, RepairPlanner
            session = get_latest_rework_session(proj_id)
            plan = None
            if session:
                plan = RepairPlanner.load_plan(session.project_path, session.session_id)
            if not plan:
                rw_dir = os.path.join(proj_id, "state", "rework")
                if os.path.exists(rw_dir):
                    for sub in os.listdir(rw_dir):
                        plan_path = os.path.join(rw_dir, sub, "repair_plan.json")
                        if os.path.exists(plan_path):
                            with open(plan_path, "r", encoding="utf-8") as f:
                                self._send_json(200, json.load(f))
                                return
            if plan:
                self._send_json(200, plan.to_dict())
            else:
                self._send_json(200, {"repairs": []})
        except Exception as e:
            self._send_json(500, {"error": str(e)})

    def _handle_rework_history(self, query: Dict[str, List[str]]) -> None:
        """Returns execution history log of completed repairs."""
        proj_id = query.get("project", [get_execution_projection().project_id])[0]
        try:
            from desk.rework import get_latest_rework_session
            session = get_latest_rework_session(proj_id)
            if not session:
                self._send_json(404, {"error": "No rework session found"})
                return
            path = os.path.join(session.project_path, "state", "rework", session.session_id, "repair_history.jsonl")
            history = []
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            history.append(json.loads(line))
            self._send_json(200, history)
        except Exception as e:
            self._send_json(500, {"error": str(e)})

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
        self._monitor_thread: Optional[threading.Thread] = None
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

        self._monitor_thread = threading.Thread(target=self._telemetry_monitor_loop, name="DESK-Telemetry-Monitor", daemon=True)
        self._monitor_thread.start()

        if background:
            self._thread = threading.Thread(target=self._serve_loop, name="DESK-Server-Thread", daemon=True)
            self._thread.start()
        else:
            self._serve_loop()

        return self.url, self.actual_port

    def _telemetry_monitor_loop(self) -> None:
        """Background loop reconciling live telemetry and broadcasting state changes."""
        from desk.runtime.projection import get_execution_projection
        from desk.runtime.events import get_event_bus
        last_status = None
        last_progress = None
        last_stage = None
        while self._is_running:
            try:
                proj = get_execution_projection()
                proj.reconcile_live_telemetry()
                summary = proj.get_summary()
                cur_status = summary.get("status")
                cur_progress = summary.get("overall_progress")
                cur_stage = summary.get("current_stage")
                if (cur_status != last_status) or (cur_progress != last_progress) or (cur_stage != last_stage):
                    last_status = cur_status
                    last_progress = cur_progress
                    last_stage = cur_stage
                    bus = get_event_bus()
                    bus.emit("stage.progress", stage=cur_stage or "", progress=cur_progress, message=summary.get("current_activity", ""))
            except Exception:
                pass
            time.sleep(1.0)

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
