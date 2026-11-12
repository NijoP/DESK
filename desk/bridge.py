"""DESK Fast ECAD Bridge Architecture.
Provides high-performance, project-isolated, cached execution of JavaScript
inside EasyEDA Pro via the API Gateway.
Zero external dependencies.
"""
import json
import os
from desk import config as deskcfg
import sys
import time
import urllib.request
import urllib.error
import io
import socket
import select
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Typed errors live in desk/errors.py; every one subclasses SystemExit, so a CLI tool that does not
# catch them still exits with the message, while library callers can catch the precise type.
from desk.errors import (  # noqa: E402
    BridgeError, BridgeUnreachable, BridgeDocumentMismatch, BridgeScriptError, BridgeMutationTimeout, ProjectError,
)


@dataclass
class BridgeSession:
    project_id: str
    project_path: str
    endpoint: str
    port: int
    window_id: Optional[str]
    pcb_uuid: Optional[str]
    sheet_uuid: Optional[str]
    last_health_ts: float
    is_valid: bool = True
    project_uuid: Optional[str] = None
    bound_by: str = "unbound"           # explicit | project.json | env | uuid-scan | unbound
    window_generation: int = 0
    rotations: List[Dict[str, Any]] = field(default_factory=list)
    last_response_meta: Dict[str, Any] = field(default_factory=dict)

class SessionRegistry:
    """Manages active bridge sessions per project, preventing cross-project interference."""
    _sessions: Dict[str, BridgeSession] = {}
    _discovered_port: Optional[int] = None
    _last_port_check: float = 0.0
    _cache_ttl: float = 60.0

    @classmethod
    def _get_cache_path(cls) -> str:
        return os.path.join(os.path.expanduser("~/.desk"), "bridge_endpoint.json")

    @classmethod
    def _read_persistent_cache(cls) -> Optional[int]:
        try:
            path = cls._get_cache_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ts = data.get("timestamp", 0)
                if time.time() - ts < cls._cache_ttl:
                    return int(data.get("port", 49620))
        except Exception:
            pass
        return None

    @classmethod
    def _write_persistent_cache(cls, port: int) -> None:
        try:
            path = cls._get_cache_path()
            from desk.fsutil import atomic_write_json
            atomic_write_json(path, {"port": port, "timestamp": time.time(), "pid": os.getpid()}, indent=None)
        except Exception:
            pass

    @classmethod
    def _probe_single_port(cls, port: int, timeout: float = 0.015) -> bool:
        """Fast non-blocking or short-timeout direct check on a single port."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            res = s.connect_ex(("127.0.0.1", port))
            s.close()
            return res == 0
        except OSError:
            return False

    @classmethod
    def _probe_ports_concurrent(cls, ports: List[int], timeout: float = 0.03) -> Optional[int]:
        """Probes multiple ports concurrently using non-blocking sockets and select."""
        sockets = []
        try:
            for p in ports:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setblocking(False)
                s.connect_ex(("127.0.0.1", p))
                sockets.append((p, s))

            r, w, x = select.select([], [s for _, s in sockets], [], timeout)
            for p, s in sockets:
                if s in w:
                    try:
                        err = s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                        if err == 0:
                            return p
                    except OSError:
                        pass
        except Exception:
            pass
        finally:
            for _, s in sockets:
                try:
                    s.close()
                except OSError:
                    pass
        return None

    @classmethod
    def get_port(cls, timeout: float = 0.03, force_probe: bool = False) -> int:
        """
        Fast, hardware-adaptive port discovery with multi-tier caching:
        1. Explicit EDA_PORT environment variable (0ms)
        2. In-memory validated cache (0ms)
        3. Persistent disk cache validation (sub-millisecond)
        4. Priority check of default port 49620 (< 2ms if running)
        5. Concurrent non-blocking probe across 49620..49629 (< 35ms worst-case)
        """
        # 1. Environment variable override
        if deskcfg.get("EDA_PORT"):
            return int(deskcfg.get("EDA_PORT"))

        now = time.time()
        # 2. In-memory cache
        if not force_probe and cls._discovered_port and (now - cls._last_port_check < cls._cache_ttl):
            return cls._discovered_port

        # 3. Persistent disk cache check
        if not force_probe:
            cached_port = cls._read_persistent_cache()
            if cached_port:
                if cls._probe_single_port(cached_port, timeout=0.015):
                    cls._discovered_port = cached_port
                    cls._last_port_check = now
                    return cached_port

        # 4. Fast direct probe of default port (49620)
        if cls._probe_single_port(49620, timeout=0.015):
            cls._discovered_port = 49620
            cls._last_port_check = now
            cls._write_persistent_cache(49620)
            return 49620

        # 5. Concurrent non-blocking probe across candidates (49621..49629)
        candidate_ports = [p for p in range(49621, 49630)]
        found_port = cls._probe_ports_concurrent(candidate_ports, timeout=timeout)
        if found_port is not None:
            cls._discovered_port = found_port
            cls._last_port_check = now
            cls._write_persistent_cache(found_port)
            return found_port

        # Fallback to default port and cache to prevent repetitive scanning
        cls._discovered_port = 49620
        cls._last_port_check = now
        return 49620

    @classmethod
    def invalidate_port_cache(cls) -> None:
        """Invalidates both in-memory and persistent port cache."""
        cls._discovered_port = None
        cls._last_port_check = 0.0
        try:
            path = cls._get_cache_path()
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    @classmethod
    def get_session(cls, project_path: Optional[str] = None) -> Optional[BridgeSession]:
        if not project_path:
            return next(iter(cls._sessions.values()), None) if cls._sessions else None
        norm = os.path.abspath(project_path)
        return cls._sessions.get(norm)

    @classmethod
    def register_session(cls, session: BridgeSession):
        norm = os.path.abspath(session.project_path)
        cls._sessions[norm] = session

    @classmethod
    def invalidate_session(cls, project_path: Optional[str] = None):
        if not project_path:
            cls._sessions.clear()
            cls.invalidate_port_cache()
            return
        norm = os.path.abspath(project_path)
        if norm in cls._sessions:
            cls._sessions[norm].is_valid = False
            del cls._sessions[norm]

# Default port constant; actual socket discovery is deferred to get_port() on demand
DEFAULT_PORT: int = 49620
PORT: int = DEFAULT_PORT

class GatewayHTTP:
    """The gateway as the reliability layer sees it (desk.reliability.project_isolation.GatewayClient)."""

    def __init__(self, port: int, timeout: float = 5.0):
        self.port = port
        self.timeout = timeout

    def windows(self) -> List[Dict[str, Any]]:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/eda-windows")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        wins = data.get("windows", []) if isinstance(data, dict) else []
        active = data.get("activeWindowId") if isinstance(data, dict) else None
        for w in wins:
            if isinstance(w, dict) and active and w.get("windowId") == active:
                w["active"] = True
        return wins

    def execute(self, window_id: Optional[str], code: str, timeout: float = 5.0) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": code}
        if window_id:
            payload["windowId"] = window_id
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/execute", data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8")
                data = json.loads(body)
                err = data.get("error") if isinstance(data, dict) else body
            except Exception:
                err = str(e)
            return {"success": False, "error": str(err), "http_status": e.code}


def _resolver(port: int):
    from desk.reliability.project_isolation import SessionResolver
    return SessionResolver(GatewayHTTP(port))


def _find_window_for_project(port: int, target_uuids: Tuple[str, ...], timeout: float = 1.0,
                             project_uuid: Optional[str] = None) -> Optional[str]:
    """The ONE window hosting the project (by project uuid) or whose active document is one of `target_uuids`.
    Returns None when no window or more than one window matches: ambiguity is never resolved by guessing."""
    if not project_uuid and not (target_uuids and any(target_uuids)):
        return None
    try:
        from desk.reliability.project_isolation import SessionResolver
        res = SessionResolver(GatewayHTTP(port, timeout=max(timeout, 1.0)))
        wins = res.discover()
        hits = [w for w in wins if SessionResolver.matches(w, project_uuid or "", tuple(u for u in target_uuids if u))]
        return hits[0].window_id if len(hits) == 1 else None
    except Exception:
        return None


def get_or_create_session(project_path: Optional[str] = None, window_id: Optional[str] = None) -> BridgeSession:
    """Retrieves an existing valid session or establishes an isolated session bound to project.

    Binding order: explicit `window_id`, `project.json["window_id"]`, `EDA_WINDOW_ID`, then the unique window that
    hosts the project uuid / document uuids. When nothing resolves the session is UNBOUND (`window_id=None`): a read
    then goes to the active window and says so; a mutation is refused by `ex()` (KF-20261112-008)."""
    session = SessionRegistry.get_session(project_path)
    now = time.time()
    port = SessionRegistry.get_port()
    endpoint = f"http://127.0.0.1:{port}"

    p_info = {}
    p_path = project_path or deskcfg.get("DESK_PROJECT")
    if p_path and os.path.exists(os.path.join(p_path, "project.json")):
        try:
            with open(os.path.join(p_path, "project.json"), encoding="utf-8") as f:
                p_info = json.load(f)
        except Exception:
            pass

    pcb_uuid = p_info.get("pcb_uuid")
    sheet_uuid = p_info.get("sheet_uuid")
    project_uuid = p_info.get("project_uuid")
    proj_id = p_info.get("name") or (os.path.basename(p_path) if p_path else "unknown")

    # If session is active and verified within 30s, reuse it
    if session and session.is_valid and (now - session.last_health_ts < 30.0):
        if not window_id or session.window_id == window_id:
            return session

    # Resolve target window strictly for this project
    bound_by = "unbound"
    target_win = window_id or p_info.get("window_id") or deskcfg.get("EDA_WINDOW_ID")
    if target_win:
        bound_by = "explicit" if window_id else ("project.json" if p_info.get("window_id") else "env")
    if not target_win and (project_uuid or pcb_uuid or sheet_uuid):
        uuids = tuple(u for u in (pcb_uuid, sheet_uuid) if u)
        target_win = _find_window_for_project(port, uuids, project_uuid=project_uuid)
        if target_win:
            bound_by = "uuid-scan"
            _persist_window_id(p_path, p_info, target_win)

    session = BridgeSession(
        project_id=proj_id,
        project_path=p_path or os.getcwd(),
        endpoint=endpoint,
        port=port,
        window_id=target_win,
        pcb_uuid=pcb_uuid,
        sheet_uuid=sheet_uuid,
        last_health_ts=now,
        is_valid=True,
        project_uuid=project_uuid,
        bound_by=bound_by,
    )
    if p_path:
        SessionRegistry.register_session(session)
    return session


def _persist_window_id(p_path: Optional[str], p_info: Dict[str, Any], window_id: str) -> None:
    if not (p_path and os.path.exists(os.path.join(p_path, "project.json"))):
        return
    try:
        from desk.fsutil import atomic_write_json
        p_info["window_id"] = window_id
        atomic_write_json(os.path.join(p_path, "project.json"), p_info, indent=1)
    except Exception:
        pass


def rebind_session(session: BridgeSession, reason: str) -> str:
    """The bound window id is gone (gateway reconnect rotates every id): rediscover the ONE window that hosts the
    project by uuid, store it, bump the generation. Raises IdentityUnverified when no or several windows match;
    never falls back to the active window."""
    from desk.reliability.project_isolation import ProjectSession
    ps = ProjectSession(project_id=session.project_id, project_path=session.project_path,
                        project_uuid=session.project_uuid or "", schematic_uuid=session.sheet_uuid or "",
                        pcb_uuid=session.pcb_uuid or "", gateway_endpoint=session.endpoint, window_id=session.window_id)
    ps.invalidate(reason)
    _resolver(session.port).resolve(ps)          # raises IdentityUnverified on 0 or >1 matches
    old = session.window_id
    session.window_id = ps.window_id
    session.window_generation += 1
    session.rotations.append({"ts": time.time(), "from": old, "to": ps.window_id, "reason": str(reason)[:200]})
    pj = os.path.join(session.project_path or "", "project.json")
    if session.project_path and os.path.exists(pj):
        try:
            with open(pj, encoding="utf-8") as f:
                p_info = json.load(f)
        except Exception:
            p_info = {}
        _persist_window_id(session.project_path, p_info, ps.window_id or "")
    return ps.window_id or ""


_MUTATING_RX = __import__("re").compile(
    r"\.(create|delete|modify|importChanges|importAutoRouteSesFile|setNetlist|clearRouting|rebuildCopperRegion|"
    r"createPanel|overwrite[A-Za-z]*|modifyPcbName|save)\s*\(")


def looks_mutating(code: str) -> bool:
    """A script that calls a creating/deleting/modifying/saving API is a mutation whatever the caller says."""
    return bool(_MUTATING_RX.search(code or ""))


def ex(code: str, timeout: int = 280, retries: int = 1, window_id: Optional[str] = None,
       project_path: Optional[str] = None, is_mutation: bool = False, allow_unbound: bool = False) -> Any:
    """Execute JS body inside EasyEDA Pro.
    Classifies errors, protects against blind retries on mutations, and binds execution to project session.

    Reliability rules (desk/reliability):
    * a mutating script (flag or `looks_mutating`) is refused without a verified window binding unless
      `allow_unbound` / DESK_ALLOW_UNBOUND_WINDOW=1 says the operator accepts the active window;
    * "window no longer connected" means the script did NOT run: the session is rebound by project uuid
      (exactly one match, else IdentityUnverified) and the call is sent once more to the new id;
    * a timeout on a mutating script is never repeated (BridgeMutationTimeout, journalled dirty);
    * the gateway port has a circuit breaker so a dead gateway fails fast after three attempts.
    """
    from desk.profiler import TelemetryCollector
    from desk.reliability.project_isolation import is_window_disconnected_error
    from desk.reliability.circuit_breaker import BreakerRegistry
    from desk.errors import IdentityUnverified
    collector = TelemetryCollector.get_instance()
    collector.record_bridge_call()

    session = get_or_create_session(project_path, window_id=window_id)
    port = session.port
    target_window = session.window_id
    mutating = bool(is_mutation) or looks_mutating(code)
    if mutating and not target_window and not allow_unbound and not deskcfg.get_bool("DESK_ALLOW_UNBOUND_WINDOW", False):
        raise IdentityUnverified(
            f"STOP: mutating script for project '{session.project_id}' has no verified EasyEDA window binding; it would "
            "run in whichever window is ACTIVE (KF-20261112-008). Bind the project first: python tools/rebind.py "
            "projects/<P> (matches the project uuid), or set EDA_WINDOW_ID, or project.json window_id.",
            project_id=session.project_id, bound_by=session.bound_by)
    breaker = BreakerRegistry.get(f"gateway:{port}", failure_threshold=3, recovery_timeout_s=20.0)
    breaker.check()
    rebound_once = False

    for attempt in range(retries + 1):
        payload = {"code": code}
        if target_window:
            payload["windowId"] = target_window
        body = json.dumps(payload).encode("utf-8")

        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/execute",
                data=body,
                headers={"Content-Type": "application/json"}
            )
            t_req = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))

            session.last_health_ts = time.time()
            session.last_response_meta = {"ts": session.last_health_ts, "ms": round((time.time() - t_req) * 1000.0, 1),
                                          "success": bool(resp.get("success")), "window_id": target_window,
                                          "error": str(resp.get("error") or "")[:200]}
            breaker.record_success()

            if not resp.get("success"):
                err_msg = str(resp.get("error"))
                if "WRONG SHEET" in err_msg:
                    raise BridgeDocumentMismatch(f"Bridge document mismatch: {err_msg}", active=resp.get("result"))
                if is_window_disconnected_error(err_msg) and not rebound_once:
                    rebound_once = True
                    target_window = rebind_session(session, err_msg)
                    continue   # the gateway refused before executing: safe to resend once
                raise BridgeScriptError("EDA error: " + err_msg)

            return resp.get("result")

        except urllib.error.HTTPError as e:
            try:
                raw_body = e.read().decode("utf-8")
                err_data = json.loads(raw_body)
                err_detail = err_data.get("error") or raw_body
            except Exception:
                err_detail = str(e)
            session.last_response_meta = {"ts": time.time(), "success": False, "http_status": e.code,
                                          "window_id": target_window, "error": str(err_detail)[:200]}
            if is_window_disconnected_error(str(err_detail)) and not rebound_once:
                rebound_once = True
                target_window = rebind_session(session, str(err_detail))
                continue
            raise BridgeScriptError(f"EasyEDA JavaScript Runtime Error: {err_detail}", http_status=e.code)

        except (OSError, TimeoutError) as e:
            is_timeout = isinstance(e, (TimeoutError, socket.timeout)) or "timed out" in str(e).lower()
            if not is_timeout:
                breaker.record_failure(str(e))
            # Never blindly repeat a mutating operation on network/bridge timeout
            if mutating and is_timeout:
                SessionRegistry.invalidate_session(project_path)
                raise BridgeMutationTimeout(f"Mutation timeout: operation may have partially succeeded. "
                                            f"Inspect PCB state before retrying. ({e})")

            # Auto-resolve window if lost
            if session.pcb_uuid or session.sheet_uuid or session.project_uuid:
                resolved = _find_window_for_project(port, tuple(u for u in (session.pcb_uuid, session.sheet_uuid) if u),
                                                    project_uuid=session.project_uuid)
                if resolved and resolved != target_window:
                    target_window = resolved
                    session.window_id = resolved
                    continue

            if attempt == retries:
                SessionRegistry.invalidate_session(project_path)
                raise BridgeUnreachable(f"Bridge not reachable on port {port}: {e}\n"
                                        "-> Is EasyEDA Pro open with the API Gateway connected? (see docs/06_EASYEDA_API.md)",
                                        port=port)
            time.sleep(1)

def check(res: Any) -> Any:
    """Raises BridgeScriptError (a SystemExit) if EasyEDA JS returned an error dictionary."""
    if isinstance(res, dict) and res.get("error"):
        raise BridgeScriptError(f"STOP: {res}", result=res)
    return res

def guard(doc_uuid: str, open_doc: bool = True) -> str:
    """JS prefix that verifies active document and only opens + delays if not already active."""
    if not open_doc:
        return (f'const __D=await eda.dmt_SelectControl.getCurrentDocumentInfo();'
                f'if(!__D||__D.uuid!=="{doc_uuid}") return {{error:"WRONG SHEET", active:__D&&__D.uuid}};\n')
    return (f'let __D=await eda.dmt_SelectControl.getCurrentDocumentInfo();'
            f'if(!__D||__D.uuid!=="{doc_uuid}"){{'
            f'await eda.dmt_EditorControl.openDocument("{doc_uuid}");'
            f'await new Promise(r=>setTimeout(r,600));'
            f'__D=await eda.dmt_SelectControl.getCurrentDocumentInfo();}}'
            f'if(!__D||__D.uuid!=="{doc_uuid}") return {{error:"WRONG SHEET", active:__D&&__D.uuid}};\n')

def load_project(path: str) -> Dict[str, Any]:
    p = os.path.join(path, "project.json")
    if not os.path.exists(p):
        raise ProjectError(f"missing {p} (run tools/new_project.py first)", path=p)
    with open(p, encoding="utf-8") as f:
        proj = json.load(f)
    for k in ("name", "sheet_uuid", "pcb_uuid"):
        if not proj.get(k):
            raise ProjectError(f"{p}: missing '{k}'", path=p, key=k)
    return proj

_B64 = ('if(!f) return {error:"NO FILE returned by EasyEDA"}; const ab=await f.arrayBuffer(); const u=new Uint8Array(ab);'
        'let s=""; const ch=0x8000;'
        'for(let i=0;i<u.length;i+=ch){s+=String.fromCharCode.apply(null,u.subarray(i,Math.min(i+ch,u.length)));} return {name:f.name,b64:btoa(s)};')

def fetch_file(js_get: str, dest_dir: str, prefix: str = "", timeout: int = 280, window_id: Optional[str] = None, project_path: Optional[str] = None) -> str:
    """Fetches binary/text file from EasyEDA Pro in chunks, avoiding massive memory allocations."""
    code = f'{js_get}\n{_B64}'
    res = ex(code, timeout=timeout, retries=1, window_id=window_id, project_path=project_path)
    if not isinstance(res, dict) or "b64" not in res:
        raise BridgeScriptError("fetch_file: EasyEDA did not return file: " + str(res)[:200])
    import base64
    raw = base64.b64decode(res["b64"])
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, prefix + (res.get("name") or "out.bin"))
    with open(out, "wb") as f:
        f.write(raw)
    return out
