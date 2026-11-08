"""DESK Fast ECAD Bridge Architecture.
Provides high-performance, project-isolated, cached execution of JavaScript
inside EasyEDA Pro via the API Gateway.
Zero external dependencies.
"""
import json
import os
import sys
import time
import urllib.request
import io
import socket
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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

class SessionRegistry:
    """Manages active bridge sessions per project, preventing cross-project interference."""
    _sessions: Dict[str, BridgeSession] = {}
    _discovered_port: Optional[int] = None
    _last_port_check: float = 0.0

    @classmethod
    def get_port(cls, timeout: float = 0.05) -> int:
        """Fast port discovery using direct TCP socket connect (sub-millisecond)."""
        if os.environ.get("EDA_PORT"):
            return int(os.environ["EDA_PORT"])
        
        # Cache discovered port for 60 seconds unless invalidated
        now = time.time()
        if cls._discovered_port and (now - cls._last_port_check < 60.0):
            return cls._discovered_port

        for p in range(49620, 49630):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                res = s.connect_ex(("127.0.0.1", p))
                s.close()
                if res == 0:
                    cls._discovered_port = p
                    cls._last_port_check = now
                    return p
            except OSError:
                pass
        
        cls._discovered_port = 49620
        cls._last_port_check = now
        return 49620

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
    def invalidate_session(cls, project_path: Optional[str]):
        if not project_path:
            cls._sessions.clear()
            cls._discovered_port = None
            return
        norm = os.path.abspath(project_path)
        if norm in cls._sessions:
            cls._sessions[norm].is_valid = False
            del cls._sessions[norm]

# Default port constant; actual socket discovery is deferred to get_port() on demand
DEFAULT_PORT: int = 49620
PORT: int = DEFAULT_PORT

def _find_window_for_project(port: int, target_uuids: Tuple[str, ...], timeout: float = 1.0) -> Optional[str]:
    """Finds the specific EasyEDA Pro window hosting the project's documents."""
    if not target_uuids or not any(target_uuids):
        return None
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/eda-windows")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            wins = json.loads(r.read().decode("utf-8")).get("windows", [])
        for w in wins:
            wid = w.get("windowId")
            if not wid: continue
            try:
                chk = urllib.request.Request(
                    f"http://127.0.0.1:{port}/execute",
                    data=json.dumps({
                        "code": "const d=await eda.dmt_SelectControl.getCurrentDocumentInfo(); return d?d.uuid:null;",
                        "windowId": wid
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(chk, timeout=1.0) as cr:
                    cres = json.loads(cr.read().decode("utf-8"))
                    if cres.get("result") in target_uuids:
                        return wid
            except Exception:
                pass
    except Exception:
        pass
    return None

def get_or_create_session(project_path: Optional[str] = None, window_id: Optional[str] = None) -> BridgeSession:
    """Retrieves an existing valid session or establishes an isolated session bound to project."""
    session = SessionRegistry.get_session(project_path)
    now = time.time()
    port = SessionRegistry.get_port()
    endpoint = f"http://127.0.0.1:{port}"

    p_info = {}
    p_path = project_path or os.environ.get("DESK_PROJECT")
    if p_path and os.path.exists(os.path.join(p_path, "project.json")):
        try:
            with open(os.path.join(p_path, "project.json"), encoding="utf-8") as f:
                p_info = json.load(f)
        except Exception:
            pass

    pcb_uuid = p_info.get("pcb_uuid")
    sheet_uuid = p_info.get("sheet_uuid")
    proj_id = p_info.get("name") or (os.path.basename(p_path) if p_path else "unknown")

    # If session is active and verified within 30s, reuse it
    if session and session.is_valid and (now - session.last_health_ts < 30.0):
        if not window_id or session.window_id == window_id:
            return session

    # Resolve target window strictly for this project
    target_win = window_id or p_info.get("window_id") or os.environ.get("EDA_WINDOW_ID")
    if not target_win and (pcb_uuid or sheet_uuid):
        uuids = tuple(u for u in (pcb_uuid, sheet_uuid) if u)
        target_win = _find_window_for_project(port, uuids)
        if target_win and p_path and os.path.exists(os.path.join(p_path, "project.json")):
            try:
                p_info["window_id"] = target_win
                json.dump(p_info, open(os.path.join(p_path, "project.json"), "w", encoding="utf-8"), indent=1)
            except Exception:
                pass

    session = BridgeSession(
        project_id=proj_id,
        project_path=p_path or os.getcwd(),
        endpoint=endpoint,
        port=port,
        window_id=target_win,
        pcb_uuid=pcb_uuid,
        sheet_uuid=sheet_uuid,
        last_health_ts=now,
        is_valid=True
    )
    if p_path:
        SessionRegistry.register_session(session)
    return session

def ex(code: str, timeout: int = 280, retries: int = 1, window_id: Optional[str] = None,
       project_path: Optional[str] = None, is_mutation: bool = False) -> Any:
    """Execute JS body inside EasyEDA Pro.
    Classifies errors, protects against blind retries on mutations, and binds execution to project session.
    """
    from desk.profiler import TelemetryCollector
    collector = TelemetryCollector.get_instance()
    collector.record_bridge_call()

    session = get_or_create_session(project_path, window_id=window_id)
    port = session.port
    target_window = session.window_id

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
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))

            session.last_health_ts = time.time()

            if not resp.get("success"):
                err_msg = str(resp.get("error"))
                # Classified error handling
                if "WRONG SHEET" in err_msg:
                    raise SystemExit(f"Bridge document mismatch: {err_msg}")
                raise SystemExit("EDA error: " + err_msg)

            return resp.get("result")

        except (OSError, TimeoutError) as e:
            # Never blindly repeat a mutating operation on network/bridge timeout
            if is_mutation and isinstance(e, TimeoutError):
                SessionRegistry.invalidate_session(project_path)
                raise SystemExit(f"Mutation timeout: operation may have partially succeeded. "
                                 f"Inspect PCB state before retrying. ({e})")

            # Auto-resolve window if lost
            if session.pcb_uuid or session.sheet_uuid:
                resolved = _find_window_for_project(port, tuple(u for u in (session.pcb_uuid, session.sheet_uuid) if u))
                if resolved and resolved != target_window:
                    target_window = resolved
                    session.window_id = resolved
                    continue

            if attempt == retries:
                SessionRegistry.invalidate_session(project_path)
                raise SystemExit(f"Bridge not reachable on port {port}: {e}\n"
                                 "-> Is EasyEDA Pro open with the API Gateway connected? (see docs/06_EASYEDA_API.md)")
            time.sleep(1)

def check(res: Any) -> Any:
    """Raises SystemExit if EasyEDA JS returned an error dictionary."""
    if isinstance(res, dict) and res.get("error"):
        raise SystemExit(f"STOP: {res}")
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
        raise SystemExit(f"missing {p} (run tools/new_project.py first)")
    with open(p, encoding="utf-8") as f:
        proj = json.load(f)
    for k in ("name", "sheet_uuid", "pcb_uuid"):
        if not proj.get(k):
            raise SystemExit(f"{p}: missing '{k}'")
    return proj

_B64 = ('if(!f) return {error:"NO FILE returned by EasyEDA"}; const ab=await f.arrayBuffer(); const u=new Uint8Array(ab);'
        'let s=""; const ch=0x8000;'
        'for(let i=0;i<u.length;i+=ch){s+=String.fromCharCode.apply(null,u.subarray(i,Math.min(i+ch,u.length)));} return {name:f.name,b64:btoa(s)};')

def fetch_file(js_get: str, dest_dir: str, prefix: str = "", timeout: int = 280, window_id: Optional[str] = None, project_path: Optional[str] = None) -> str:
    """Fetches binary/text file from EasyEDA Pro in chunks, avoiding massive memory allocations."""
    code = f'{js_get}\n{_B64}'
    res = ex(code, timeout=timeout, retries=1, window_id=window_id, project_path=project_path)
    if not isinstance(res, dict) or "b64" not in res:
        raise SystemExit("fetch_file: EasyEDA did not return file: " + str(res)[:200])
    import base64
    raw = base64.b64decode(res["b64"])
    os.makedirs(dest_dir, exist_ok=True)
    out = os.path.join(dest_dir, prefix + (res.get("name") or "out.bin"))
    with open(out, "wb") as f:
        f.write(raw)
    return out
