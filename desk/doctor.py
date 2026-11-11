"""DESK environment doctor.

Checks every prerequisite a hardware engineer needs before the first live
operation and prints a fix for each failure. Read-only: it never writes to a
project and never touches EasyEDA documents.

    python desk.py doctor [--project projects/<P>] [--json]

Zero external dependencies.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""

    def to_dict(self):
        return asdict(self)


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


def check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 9)
    return Check("Python", OK if ok else FAIL, f"{v.major}.{v.minor}.{v.micro}",
                 "" if ok else "Install Python 3.9 or newer.")


def check_bridge() -> Check:
    port_env = os.environ.get("EDA_PORT")
    ports = [int(port_env)] if port_env and port_env.isdigit() else list(range(49620, 49630))
    live = [p for p in ports if _port_open(p)]
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
    return Check("Node.js", OK, _version(["node", "--version"]) or node)


def check_java() -> Check:
    java = shutil.which("java")
    if not java:
        return Check("Java runtime", FAIL, "java not on PATH",
                     "Install a Java 17+ JRE/JDK; tools/route.py needs it to run Freerouting.")
    return Check("Java runtime", OK, _version(["java", "-version"]) or java)


def check_freerouting() -> Check:
    try:
        from desk.routing.orchestrator import RoutingEngineOrchestrator
        orch = RoutingEngineOrchestrator()
        try:
            kind, path, ver = orch.discover_engine()
            return Check("Freerouting engine", OK, f"{kind} {ver} at {path}")
        except RuntimeError as e:
            return Check("Freerouting engine", FAIL, str(e)[:160],
                         "Download a Freerouting JAR into library/tools/ (git-ignored) or set FREEROUTING_JAR.")
    except Exception as e:
        return Check("Freerouting engine", WARN, f"discovery error: {str(e)[:120]}")


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
    explicit = os.environ.get(env_var, "").strip()
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
    present = {k: os.environ.get(k) for k in keys if os.environ.get(k)}
    if not present:
        return Check("Model tier config", WARN, "no DESK_L*_MODEL_* variables set",
                     "Optional. Set DESK_L1_MODEL_PI / DESK_L2_MODEL_PI / DESK_FRONTIER_MODEL to route cheap tiers.")
    return Check("Model tier config", OK, ", ".join(f"{k}={v}" for k, v in present.items()))


def check_nvidia_key() -> Check:
    if os.environ.get("NVIDIA_API_KEY"):
        return Check("NVIDIA API key", OK, "NVIDIA_API_KEY is set (value not shown)")
    return Check("NVIDIA API key", WARN, "NVIDIA_API_KEY not set",
                 "Optional. Needed only when Pi routes to the nvidia provider.")


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


def run(project: Optional[str] = None) -> List[Check]:
    checks = [
        check_python(), check_bridge(), check_node(), check_java(), check_freerouting(),
        check_easyeda_cli(),
        check_model_cli("pi", "DESK_PI_PATH", ["pi", "pi.cmd"]),
        check_model_cli("agy", "DESK_AGY_PATH", ["agy", "agy.exe"]),
        check_model_config(), check_nvidia_key(),
    ]
    checks.extend(check_project(project))
    return checks


def render(checks: List[Check]) -> str:
    lines = ["DESK DOCTOR", "=" * 72]
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
    checks = run(project)
    if "--json" in argv:
        print(json.dumps([c.to_dict() for c in checks], indent=2))
    else:
        print(render(checks))
    return 1 if any(c.status == FAIL for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
