"""The DESK node service: the one door through which Weft reaches DESK's engines.

    GET  /health                 liveness, no secrets, no auth
    GET  /v1/nodes               the node contracts
    POST /v1/nodes/<NodeId>      run one node; the body is the node's inputs, the answer is its envelope

Security, because a Weft worker is a plain process running as the local user and is not a sandbox:
  * binds to loopback unless told otherwise;
  * every /v1 call needs `Authorization: Bearer <token>`; the token comes from DESK_WEFT_TOKEN or a generated
    file only the user can read, and is given to Weft as a stored connection, never written in a .weft file;
  * the only operations are the node contracts: no shell, no file paths, no arbitrary code;
  * a project id is a folder name under the projects root and nothing else;
  * request bodies are capped; live design mutation is refused here outright.
"""
from __future__ import annotations

import hmac
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional

from desk.weft import INTEGRATION_VERSION, contracts, nodes, staging

DEFAULT_PORT = 14500
MAX_BODY = 256 * 1024


def token_path() -> str:
    return os.path.join(staging.BUILD_DIR, "service.token")


def load_or_create_token() -> str:
    env = os.environ.get("DESK_WEFT_TOKEN")
    if env:
        return env
    path = token_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            tok = f.read().strip()
        if tok:
            return tok
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tok = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(tok)
    return tok


def make_server(token: str, host: str = "127.0.0.1", port: int = DEFAULT_PORT, projects_root: Optional[str] = None,
                provider: Optional[Callable[[str, str], Dict[str, Any]]] = None) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("the node service does not start without a token")

    class Handler(BaseHTTPRequestHandler):
        server_version = "DeskWeftNodes/" + INTEGRATION_VERSION

        def log_message(self, fmt: str, *args: Any) -> None:     # request lines carry no bodies and no token
            return

        def _send(self, status: int, doc: Dict[str, Any]) -> None:
            body = json.dumps(doc).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            got = self.headers.get("Authorization", "")
            return got.startswith("Bearer ") and hmac.compare_digest(got[7:].encode("utf-8"), token.encode("utf-8"))

        def do_GET(self) -> None:
            if self.path == "/health":
                return self._send(200, {"service": "desk-weft-nodes", "integration": INTEGRATION_VERSION, "weftPin": staging.pin()["commit"]})
            if not self._authorized():
                return self._send(401, nodes.error_envelope("", "", "UNAUTHORIZED", "missing or wrong service token"))
            if self.path == "/v1/nodes":
                return self._send(200, {"nodes": [c.to_dict() for c in contracts.CONTRACTS]})
            self._send(404, nodes.error_envelope("", "", "UNKNOWN_NODE", "no such path"))

        def do_POST(self) -> None:
            if not self._authorized():
                return self._send(401, nodes.error_envelope("", "", "UNAUTHORIZED", "missing or wrong service token"))
            if not self.path.startswith("/v1/nodes/"):
                return self._send(404, nodes.error_envelope("", "", "UNKNOWN_NODE", "no such path"))
            node_id = self.path[len("/v1/nodes/"):]
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                self.close_connection = True
                if 0 < length <= 4 * MAX_BODY:        # drain a modest overshoot so the caller reads the refusal
                    self.rfile.read(length)
                return self._send(400, nodes.error_envelope(node_id, "", "INVALID_INPUT", f"body must be 0..{MAX_BODY} bytes"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                return self._send(400, nodes.error_envelope(node_id, "", "INVALID_INPUT", "body is not JSON"))
            status, envelope = nodes.execute(node_id, payload, projects_root=projects_root, provider=provider)
            self._send(status, envelope)

    return ThreadingHTTPServer((host, port), Handler)


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
