"""DESK environment doctor.

Checks every prerequisite a hardware engineer needs before the first live
operation and prints a fix for each failure. Read-only with respect to projects
and EasyEDA documents; its only write is its own probe cache.

    python desk.py doctor [--project projects/<P>] [--json] [--no-cache]

Speed (T-18): the probes that launch a process (java -version, node --version,
Freerouting JAR compatibility) are cached in <repo>/state/doctor_cache.json for
DESK_DOCTOR_CACHE_TTL_S seconds (default one day), keyed by the executable's path
and modification time so a replaced JDK or JAR is re-probed. The bridge port scan
probes all ten ports concurrently. All checks run in a bounded thread pool.

Zero external dependencies.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, List, Optional

from desk import config as deskcfg
from desk._version import __version__

OK, WARN, FAIL = "OK", "WARN", "FAIL"

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(_REPO, "state", "doctor_cache.json")
_USE_CACHE = True


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""

    def to_dict(self):
        return asdict(self)


# ---- probe cache -----------------------------------------------------------------------------
def _cache_load() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_store(key: str, sig: str, value: Any) -> None:
    """Always stores (even with --no-cache, which only bypasses reading) so the next run is warm."""
    try:
        d = _cache_load()
        d[key] = {"sig": sig, "ts": time.time(), "value": value}
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        tmp = CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass


def _cached(key: str, sig: str, compute: Callable[[], Any]) -> Any:
    """Return the cached value for (key, sig) if younger than the TTL, else compute, store and return it."""
    ttl = deskcfg.get_int("DESK_DOCTOR_CACHE_TTL_S", 86400) or 0
    ent = _cache_load().get(key) if _USE_CACHE else None
    if ent and ent.get("sig") == sig and (time.time() - float(ent.get("ts", 0))) < ttl:
        return ent.get("value")
    value = compute()
    _cache_store(key, sig, value)
    return value


def _sig(path: Optional[str]) -> str:
    """Executable identity: absolute path plus mtime and size, so an upgrade invalidates the cache."""
    if not path:
        return "none"
    try:
        st = os.stat(path)
        return f"{os.path.abspath(path)}|{int(st.st_mtime)}|{st.st_size}"
    except OSError:
        return f"{path}|missing"


# ---- primitive probes -------------------------------------------------------------------------
def _port_open(port: int, timeout: float = 0.1) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except OSError:
        return False


def _version(cmd: List[str], timeout: float = 8.0) -> Optional[str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return out.strip().splitlines()[0] if out.strip() else ""
    except Exception:
        return None


# ---- checks ----------------------------------------------------------------------------------
def check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 9)
    return Check("Python", OK if ok else FAIL, f"{v.major}.{v.minor}.{v.micro}",
                 "" if ok else "Install Python 3.9 or newer.")


def check_config() -> Check:
    cfg = deskcfg.get_config()
    probs = cfg.validate()
    if probs:
        return Check("Configuration", FAIL, f"{len(probs)} problem(s): " + "; ".join(probs)[:200],
                     "Run python desk.py config show and fix the listed keys.")
    n_env = sum(1 for r in cfg.as_rows() if r["source"] == "env")
    n_file = sum(1 for r in cfg.as_rows() if r["source"] in ("user", "repo"))
    return Check("Configuration", OK, f"valid ({n_env} from env, {n_file} from files, rest defaults)")


def check_bridge() -> Check:
    port_env = deskcfg.get("EDA_PORT")
    ports = [int(port_env)] if port_env and port_env.isdigit() else list(range(49620, 49630))
    with ThreadPoolExecutor(max_workers=len(ports)) as pool:
        live = [p for p, up in zip(ports, pool.map(_port_open, ports)) if up]
    if live:
        return Check("EasyEDA API bridge", OK, f"listening on 127.0.0.1:{live[0]}")
    return Check("EasyEDA API bridge", FAIL, "no bridge on 49620-49629",
                 "Open EasyEDA Pro, enable the 'Run API Gateway' extension, and start the bridge "
                 "(docs/06_EASYEDA_API.md). Set EDA_PORT if it listens elsewhere.")


def check_node() -> Check:
    node = shutil.which("node")
    if not node:
        return Check("Node.js", WARN, "not on PATH",
                     "Install Node.js 18+ if you run the bridge server locally.")
    ver = _cached("node", _sig(node), lambda: _version(["node", "--version"]) or node)
    return Check("Node.js", OK, ver)


def _java_path() -> Optional[str]:
    try:
        from desk.routing.orchestrator import find_java
        java = find_java(os.path.join(_REPO, "library", "tools"))
    except Exception:
        java = shutil.which("java")
    if not java or not (os.path.exists(java) or shutil.which(java)):
        return None
    return java


def check_java() -> Check:
    java = _java_path()
    if not java:
        return Check("Java runtime", FAIL, "java not found (DESK_JAVA, library/tools/jdk*/bin, PATH)",
                     "Install Java 25 (needed by Freerouting >= 2.2) or set DESK_JAVA; Java 17+ only runs Freerouting 2.1.")
    ver = _cached("java", _sig(java), lambda: _version([java, "-version"]) or java)
    import re as _re
    m = _re.search(r'version "(\d+)', ver or "")
    major = int(m.group(1)) if m else 0
    if 0 < major < 25:
        return Check("Java runtime", WARN, f"{ver} ({java})",
                     "Only Freerouting 2.1.0 runs on this Java; it never returns a partial board (KF-20261111-006). "
                     "Install a Java 25 JDK (e.g. unzip Temurin 25 into library/tools/jdk25/) or set DESK_JAVA.")
    return Check("Java runtime", OK, f"{ver} ({java})")


def _engine_sig() -> str:
    tools = os.path.join(_REPO, "library", "tools")
    parts = [_sig(_java_path())]
    for name in ("FREEROUTING_JAR", "FREEROUTING_BIN"):
        parts.append(f"{name}={deskcfg.get(name) or ''}")
    try:
        for n in sorted(os.listdir(tools)):
            if n.lower().endswith(".jar") or n.lower().startswith("freerouting"):
                parts.append(_sig(os.path.join(tools, n)))
    except OSError:
        parts.append("no-tools-dir")
    return "|".join(parts)


def check_freerouting() -> Check:
    def probe() -> Dict[str, Any]:
        from desk.routing.orchestrator import RoutingEngineOrchestrator
        orch = RoutingEngineOrchestrator()
        try:
            kind, path, ver = orch.discover_engine()
            return {"ok": True, "kind": kind, "path": path, "ver": ver,
                    "note": getattr(orch, "last_discovery_note", "") or ""}
        except RuntimeError as e:
            return {"ok": False, "error": str(e)[:160]}
    try:
        r = _cached("freerouting", _engine_sig(), probe)
    except Exception as e:
        return Check("Freerouting engine", WARN, f"discovery error: {str(e)[:120]}")
    if not r.get("ok"):
        return Check("Freerouting engine", FAIL, r.get("error", "not found"),
                     "Download a Freerouting JAR into library/tools/ (git-ignored) or set FREEROUTING_JAR.")
    if "incompatible" in r.get("note", ""):
        return Check("Freerouting engine", WARN, f"{r['kind']} {r['ver']} at {r['path']}; {r['note']}",
                     "Newer Freerouting JARs are present but need a newer Java (v2.2+ needs Java 25). Install it to get "
                     "completion-based scoring and best-board restore.")
    return Check("Freerouting engine", OK, f"{r['kind']} {r['ver']} at {r['path']}")


def check_easyeda_cli() -> Check:
    try:
        from desk.eda.easyeda_pro import get_easyeda_manager
        doc = get_easyeda_manager().cli.doctor()
        st = doc.get("status", "NOT_INSTALLED")
        if st == "OK":
            return Check("EasyEDA Pro CLI", OK, doc.get("binary_path") or "")
        return Check("EasyEDA Pro CLI", WARN, st,
                     "Optional. Install the easyeda-pro CLI for session inspection and safety barriers.")
    except Exception as e:
        return Check("EasyEDA Pro CLI", WARN, f"check error: {str(e)[:100]}")


def check_model_cli(name: str, env_var: str, candidates: List[str]) -> Check:
    explicit = (deskcfg.get(env_var) or "").strip()
    found = explicit if explicit and (os.path.exists(explicit) or shutil.which(explicit)) else None
    if not found:
        for c in candidates:
            found = shutil.which(c)
            if found:
                break
    if found:
        return Check(f"{name} CLI", OK, found)
    return Check(f"{name} CLI", WARN, "not found",
                 f"Optional for the L1-L4 model router. Install {name} or set {env_var}.")


def check_model_config() -> Check:
    keys = ["DESK_L1_MODEL_PI", "DESK_L2_MODEL_PI", "DESK_FRONTIER_MODEL"]
    present = {k: deskcfg.get(k) for k in keys if deskcfg.get(k)}
    if not present:
        return Check("Model tier config", WARN, "no DESK_L*_MODEL_* variables set",
                     "Optional. Set DESK_L1_MODEL_PI / DESK_L2_MODEL_PI / DESK_FRONTIER_MODEL to route cheap tiers.")
    return Check("Model tier config", OK, ", ".join(f"{k}={v}" for k, v in present.items()))


def check_nvidia_key() -> Check:
    key_env = deskcfg.get("DESK_HTTP_API_KEY_ENV") or "NVIDIA_API_KEY"
    if deskcfg.get(key_env):
        return Check("NVIDIA API key", OK, f"{key_env} is set (value not shown)")
    return Check("NVIDIA API key", WARN, f"{key_env} not set",
                 "Optional. Needed for the nvidia provider and desk.py agent (or store it with desk.py auth configure).")


def check_project(project: Optional[str]) -> List[Check]:
    if not project:
        return [Check("Project", WARN, "no --project given", "Pass --project projects/<NAME> to validate its binding.")]
    pj = os.path.join(project, "project.json")
    if not os.path.exists(pj):
        return [Check("Project", FAIL, f"{pj} missing", "Run python tools/new_project.py <NAME> first.")]
    try:
        with open(pj, encoding="utf-8") as h:
            info = json.load(h)
    except Exception as e:
        return [Check("Project", FAIL, f"{pj} unreadable: {str(e)[:80]}", "Restore project.json from git.")]
    out = [Check("Project", OK, project)]
    for k in ("sheet_uuid", "pcb_uuid"):
        v = str(info.get(k, "") or "")
        if not v or "PASTE" in v.upper():
            out.append(Check(f"project.json {k}", FAIL, "not bound",
                             "Open the project in EasyEDA Pro and run python tools/ping.py, then paste the uuid."))
        else:
            out.append(Check(f"project.json {k}", OK, v[:12] + "…"))
    dump = os.path.join(project, "state", "pcb_dump.json")
    out.append(Check("state/pcb_dump.json", OK if os.path.exists(dump) else WARN,
                     "present" if os.path.exists(dump) else "missing",
                     "" if os.path.exists(dump) else "Run python tools/pcb_dump.py <project> before PCB tools."))
    lock = os.path.join(project, "state", "write.lock")
    if os.path.exists(lock):
        out.append(Check("write.lock", WARN, "a writer lock exists",
                         "If no DESK tool is running: python tools/desk.py recover <project>."))
    return out


def check_weft() -> Check:
    """Weft is the workflow runtime for orchestrated runs. Missing Weft is a warning here: the deterministic
    engines and every other tool work without it; `desk.py weft run` itself refuses to start."""
    try:
        from desk.weft import runtime as weft_runtime
        st = weft_runtime.WeftRuntime().status()
    except Exception as e:
        return Check("weft", WARN, f"could not probe Weft: {e}", "python tools/desk.py weft status")
    if not st["available"]:
        return Check("weft", WARN, f"Weft runtime not installed ({st['reason']}); orchestrated workflows cannot run",
                     "install the pinned Weft: docs/weft/02_INSTALL.md (Windows needs WSL2 and Docker)")
    if st.get("pinMatch") is False:
        return Check("weft", FAIL, f"Weft checkout {str(st.get('checkoutCommit'))[:12]} differs from the DESK pin {st['pin'][:12]}",
                     "check out the pinned commit and re-run its setup.sh")
    if not st["daemon"]["running"]:
        return Check("weft", WARN, f"Weft {st.get('version')} installed but its runtime is not running", "weft daemon start")
    return Check("weft", OK, f"Weft {st.get('version')} ({st['kind']}), runtime running, pin {st['pin'][:12]}")


# ---- runner ----------------------------------------------------------------------------------
def _probes() -> List[Callable[[], Check]]:
    return [
        check_python, check_config, check_bridge, check_node, check_java, check_freerouting, check_easyeda_cli,
        lambda: check_model_cli("pi", "DESK_PI_PATH", ["pi", "pi.cmd"]),
        lambda: check_model_cli("agy", "DESK_AGY_PATH", ["agy", "agy.exe"]),
        check_model_config, check_nvidia_key, check_weft,
    ]


def run(project: Optional[str] = None, use_cache: bool = True, max_workers: int = 6) -> List[Check]:
    global _USE_CACHE
    _USE_CACHE = use_cache
    probes = _probes()

    def safe(fn: Callable[[], Check]) -> Check:
        try:
            return fn()
        except Exception as e:  # a broken probe must not hide the others
            return Check(getattr(fn, "__name__", "probe"), WARN, f"probe error: {str(e)[:120]}")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        checks = list(pool.map(safe, probes))
    checks.extend(check_project(project))
    return checks


def render(checks: List[Check]) -> str:
    lines = [f"DESK DOCTOR  v{__version__}", "=" * 72]
    for c in checks:
        lines.append(f"[{c.status:4}] {c.name:<24} {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"       fix: {c.fix}")
    fails = sum(1 for c in checks if c.status == FAIL)
    warns = sum(1 for c in checks if c.status == WARN)
    lines.append("=" * 72)
    lines.append(f"{fails} failed, {warns} warnings, {len(checks) - fails - warns} ok")
    return "\n".join(lines)


def main(argv: List[str]) -> int:
    project = argv[argv.index("--project") + 1] if "--project" in argv and argv.index("--project") + 1 < len(argv) else None
    t0 = time.perf_counter()
    checks = run(project, use_cache="--no-cache" not in argv)
    ms = round((time.perf_counter() - t0) * 1000)
    if "--json" in argv:
        print(json.dumps({"version": __version__, "elapsed_ms": ms, "checks": [c.to_dict() for c in checks]}, indent=2))
    else:
        print(render(checks))
        print(f"({ms} ms)")
    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
