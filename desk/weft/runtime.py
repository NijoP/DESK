"""Detect and drive the Weft runtime.

Weft has no native Windows build: its installer is a bash script, its runtime needs Docker, and upstream says to
run it inside WSL. So the `weft` command is looked for natively (Linux, macOS) and then through WSL (Windows).

There is no fallback orchestrator. When Weft is missing, `require()` raises WeftUnavailable and the caller reports
that the orchestrated workflow cannot proceed. The deterministic DESK engines stay usable on their own.

Two ways to compile-check a workflow:
  weft-cli           `weft validate` from a Weft install (the reference)
  compiler-harness   integrations/weft/validator, a small program that links upstream's own compiler and catalog
                     loader; it checks programs on a machine with no Weft runtime (see docs/weft/02_INSTALL.md)

Every command goes through an injectable runner so the adapter is testable without Weft.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from desk.weft import staging

Runner = Callable[[List[str], Optional[str], Optional[str], float], Tuple[int, str, str]]

# `weft wait` exit codes (upstream docs/src/running/cli.md)
WAIT_STATES = {0: "completed", 10: "failed_or_cancelled", 11: "waiting_for_input", 12: "still_running"}


class WeftUnavailable(RuntimeError):
    pass


def _run(argv: List[str], cwd: Optional[str] = None, stdin: Optional[str] = None, timeout: float = 60.0) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(argv, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]}: no answer in {timeout:g} s"


def _clean(text: str) -> str:
    return text.replace("\x00", "").strip()


class WeftRuntime:
    def __init__(self, runner: Runner = _run, platform: str = sys.platform, which: Callable[[str], Optional[str]] = shutil.which):
        self.runner = runner
        self.platform = platform
        self.which = which
        self._kind: Optional[str] = None
        self._probed = False

    # ---- detection ----------------------------------------------------------------------------------------
    def kind(self) -> Optional[str]:
        """'native', 'wsl' or None."""
        if not self._probed:
            self._probed = True
            if self.which("weft"):
                self._kind = "native"
            elif self.platform.startswith("win") and self.which("wsl.exe"):
                rc, out, _ = self.runner(["wsl.exe", "-e", "sh", "-lc", "command -v weft"], None, None, 20.0)
                if rc == 0 and _clean(out):
                    self._kind = "wsl"
        return self._kind

    def available(self) -> bool:
        return self.kind() is not None

    def require(self) -> str:
        k = self.kind()
        if k is None:
            raise WeftUnavailable(
                "Weft is not installed, so the orchestrated workflow cannot proceed. DESK does not fall back to another "
                "orchestrator. Install the pinned Weft (docs/weft/02_INSTALL.md); on Windows that means WSL2 and Docker.")
        return k

    def _weft(self, args: List[str], cwd: Optional[str] = None, stdin: Optional[str] = None, timeout: float = 120.0,
              linux_cwd: Optional[str] = None) -> Tuple[int, str, str]:
        k = self.require()
        if k == "native":
            return self.runner(["weft"] + args, cwd, stdin, timeout)
        quoted = " ".join(_sh(a) for a in ["weft"] + args)
        script = (f"cd {_sh(linux_cwd)} && " if linux_cwd else "") + quoted
        rc, out, err = self.runner(["wsl.exe", "-e", "bash", "-lc", script], None, stdin, timeout)
        return rc, _clean(out), _clean(err)

    def status(self) -> Dict[str, Any]:
        pin = staging.pin()
        k = self.kind()
        info: Dict[str, Any] = {"available": k is not None, "kind": k, "pin": pin["commit"], "pinVersion": pin["changelog_version"]}
        if k is None:
            info["reason"] = "no `weft` command" + (" natively or in WSL" if self.platform.startswith("win") else "")
            return info
        rc, out, err = self._weft(["--version"], timeout=20.0)
        info["version"] = _clean(out) if rc == 0 else None
        rc, out, err = self._weft(["daemon", "status"], timeout=30.0)
        text = _clean(out) or _clean(err)
        info["daemon"] = {"running": rc == 0 and "running at" in text, "detail": text.splitlines()[0] if text else ""}
        info["checkoutCommit"] = self.checkout_commit()
        info["pinMatch"] = None if info["checkoutCommit"] is None else info["checkoutCommit"] == pin["commit"]
        return info

    def checkout_commit(self) -> Optional[str]:
        """HEAD of the Weft checkout the install was built from (~/weft unless WEFT_DIR says otherwise)."""
        k = self.kind()
        if k == "native":
            d = os.environ.get("WEFT_DIR") or os.path.join(os.path.expanduser("~"), "weft")
            rc, out, _ = self.runner(["git", "-C", d, "rev-parse", "HEAD"], None, None, 15.0)
        elif k == "wsl":
            rc, out, _ = self.runner(["wsl.exe", "-e", "bash", "-lc", 'git -C "${WEFT_DIR:-$HOME/weft}" rev-parse HEAD'], None, None, 20.0)
        else:
            return None
        out = _clean(out)
        return out if rc == 0 and len(out) == 40 else None

    # ---- project placement --------------------------------------------------------------------------------
    def place(self, staged: str, name: str) -> Dict[str, Optional[str]]:
        """Where the runtime sees the staged project. For WSL it is copied into the Linux home."""
        k = self.require()
        if k == "native":
            if not os.path.isdir(os.path.join(staged, "nodes", "base_catalog")):
                self.runner(["weft", "catalog", "update"], staged, None, 300.0)
            return {"cwd": staged, "linux_cwd": None}
        target = f"$HOME/.desk-weft/{name}"
        script = (f'set -e; src="$(wslpath {_sh(staged)})"; mkdir -p "$HOME/.desk-weft"; '
                  f'if [ -d "{target}/nodes/base_catalog" ]; then mv "{target}/nodes/base_catalog" "$HOME/.desk-weft/.{name}.catalog"; fi; '
                  f'rm -rf "{target}"; cp -r "$src" "{target}"; '
                  f'if [ -d "$HOME/.desk-weft/.{name}.catalog" ]; then mv "$HOME/.desk-weft/.{name}.catalog" "{target}/nodes/base_catalog"; '
                  f'else cd "{target}" && weft catalog update; fi; echo "{target}"')
        rc, out, err = self.runner(["wsl.exe", "-e", "bash", "-lc", script], None, None, 600.0)
        if rc != 0:
            raise WeftUnavailable(f"could not place the project inside WSL: {_clean(err) or _clean(out)}")
        return {"cwd": None, "linux_cwd": _clean(out).splitlines()[-1]}

    # ---- commands -----------------------------------------------------------------------------------------
    def validate(self, staged: str, name: str) -> Dict[str, Any]:
        where = self.place(staged, name)
        with open(os.path.join(staged, "src", "main.weft"), encoding="utf-8") as f:
            source = f.read()
        rc, out, err = self._weft(["validate", "--file", "src/main.weft"], cwd=where["cwd"], stdin=source, timeout=300.0,
                                  linux_cwd=where["linux_cwd"])
        return _diagnostics("weft-cli", rc, out, err)

    def check_run(self, staged: str, name: str, inputs: Dict[str, str]) -> Dict[str, Any]:
        """Whether Weft would admit the run `run()` starts (`weft run --check`): nothing is built or run."""
        where = self.place(staged, name)
        rc, out, err = self._weft(["--json", "run", "--check"] + flag_args(run_flags(inputs, durable=False)), cwd=where["cwd"],
                                  timeout=300.0, linux_cwd=where["linux_cwd"])
        return _check_result("weft-cli", rc, out, err)

    def run(self, staged: str, name: str, inputs: Dict[str, str], durable: bool = True) -> Dict[str, Any]:
        where = self.place(staged, name)
        args = ["--json", "run", "--detach"] + flag_args(run_flags(inputs, durable))
        rc, out, err = self._weft(args, cwd=where["cwd"], timeout=1800.0, linux_cwd=where["linux_cwd"])
        run_id, phases = None, []
        for line in out.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            phases.append(obj)
            detail = obj.get("detail") if isinstance(obj.get("detail"), dict) else obj
            if isinstance(detail, dict) and detail.get("runId"):
                run_id = detail["runId"]
        failed = rc != 0 or any(p.get("phase") == "error" for p in phases)
        return {"ok": not failed and run_id is not None, "runId": run_id, "exit": rc, "phases": phases[-5:], "stderr": err[-2000:]}

    def runs(self, tag: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        args = ["--json", "runs", "--limit", str(limit)] + (["--tag", tag] if tag else [])
        rc, out, err = self._weft(args, timeout=60.0)
        try:
            return {"ok": rc == 0, "runs": json.loads(out) if out.strip() else [], "stderr": err[-500:]}
        except ValueError:
            return {"ok": False, "runs": [], "stderr": (err or out)[-500:]}

    def run_state(self, run_id: str) -> Dict[str, Any]:
        """Where a run stands, from `weft wait` with a one-second window."""
        rc, out, err = self._weft(["wait", run_id, "--timeout", "1s", "--waiting-for-input"], timeout=60.0)
        return {"runId": run_id, "state": WAIT_STATES.get(rc, "unknown"), "exit": rc, "detail": (_clean(out) or _clean(err))[-500:]}

    def reseed(self, staged: str, name: str, run_id: str) -> Dict[str, Any]:
        """Start a new run that reuses the completed nodes of an earlier one (`weft run --seed`)."""
        where = self.place(staged, name)
        rc, out, err = self._weft(["--json", "run", "--detach", "--durable", f"--seed={run_id}"], cwd=where["cwd"], timeout=1800.0,
                                  linux_cwd=where["linux_cwd"])
        new_id = None
        for line in out.splitlines():
            try:
                obj = json.loads(line)
                detail = obj.get("detail") if isinstance(obj.get("detail"), dict) else obj
                new_id = detail.get("runId") or new_id
            except (ValueError, AttributeError):
                continue
        return {"ok": rc == 0 and new_id is not None, "runId": new_id, "seededFrom": run_id, "exit": rc, "stderr": err[-1000:]}

    def stop(self, run_id: str) -> Dict[str, Any]:
        rc, out, err = self._weft(["--json", "stop", run_id], timeout=60.0)
        return {"ok": rc == 0, "detail": (_clean(out) or _clean(err))[-500:]}


def run_flags(inputs: Dict[str, str], durable: bool) -> Dict[str, Any]:
    """The `weft run` flags for a DESK workflow run, as upstream's `RunFlags` JSON (crates/weft-core/src/run_flags.rs).

    Each run input is a `Text` node; `--from <node>={"value": ...}` hands its `value` input port (catalog/basic/text)
    and starts the cut there. The compiler harness judges these same flags with upstream's admission check.
    """
    flags: Dict[str, Any] = {"from": [f"{node}={json.dumps({'value': value})}" for node, value in inputs.items()]}
    if durable:
        flags["durable"] = True
    return flags


def flag_args(flags: Dict[str, Any]) -> List[str]:
    args: List[str] = []
    for start in flags.get("from", []):
        args += ["--from", start]
    if flags.get("durable"):
        args.append("--durable")
    return args


def _check_result(checker: str, rc: int, out: str, err: str) -> Dict[str, Any]:
    try:
        doc = json.loads(_clean(out).splitlines()[-1]) if _clean(out) else None
    except ValueError:
        doc = None
    if not isinstance(doc, dict) or "ok" not in doc:
        return {"checker": checker, "ok": False, "refusal": (_clean(err) or _clean(out))[-1000:] or f"no answer (exit {rc})", "runs": []}
    return {"checker": checker, "ok": bool(doc["ok"]), "refusal": doc.get("refusal"), "runs": doc.get("runs", []),
            "errors": [d for d in doc.get("diagnostics", []) if d.get("severity") != "warning"]}


def _sh(s: Optional[str]) -> str:
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


def _diagnostics(validator: str, rc: int, out: str, err: str) -> Dict[str, Any]:
    try:
        doc = json.loads(out)
    except ValueError:
        return {"validator": validator, "ok": False, "errors": [{"code": "validator-failed", "message": (err or out)[-1000:]}], "warnings": []}
    diags = doc.get("diagnostics", [])
    errors = [d for d in diags if d.get("severity") != "warning"]
    warnings = [d for d in diags if d.get("severity") == "warning"]
    return {"validator": validator, "ok": not errors and (rc == 0 or validator == "weft-cli"),
            "errors": errors, "warnings": warnings, "nodeTypes": doc.get("nodeTypes")}


# ---- compiler harness ---------------------------------------------------------------------------------------

def harness() -> Optional[Dict[str, str]]:
    """The compiler harness, when one is configured: DESK_WEFT_VALIDATOR (binary) and DESK_WEFT_CHECKOUT (pinned checkout)."""
    exe = os.environ.get("DESK_WEFT_VALIDATOR") or os.path.join(staging.BUILD_DIR, "validator", "target", "release",
                                                              "desk-weft-validate" + (".exe" if sys.platform.startswith("win") else ""))
    checkout = os.environ.get("DESK_WEFT_CHECKOUT") or _read(os.path.join(staging.BUILD_DIR, "validator", "CHECKOUT"))
    if exe and os.path.isfile(exe) and checkout and os.path.isdir(os.path.join(checkout, "catalog")):
        return {"exe": exe, "checkout": checkout}
    return None


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def harness_validate(staged: str, h: Dict[str, str], runner: Runner = _run) -> Dict[str, Any]:
    roots = [os.path.join(h["checkout"], "catalog")] + [os.path.join(staged, "nodes", p) for p in staging.NODE_PACKAGES] + [os.path.join(staged, "src")]
    rc, out, err = runner([h["exe"], staged, os.path.join(staged, "src", "main.weft")] + roots, None, None, 120.0)
    result = _diagnostics("compiler-harness", rc, out, err)
    result["checkout"] = h["checkout"]
    return result


def harness_addresses(staged: str, h: Dict[str, str], node_type: str = "HttpRequest", runner: Runner = _run) -> Dict[str, Any]:
    """Every place of `node_type`, spelled the way `weft connect <node>` takes it (upstream's `project::address_of`)."""
    roots = [os.path.join(h["checkout"], "catalog")] + [os.path.join(staged, "nodes", p) for p in staging.NODE_PACKAGES] + [os.path.join(staged, "src")]
    rc, out, err = runner([h["exe"], "addresses", staged, os.path.join(staged, "src", "main.weft"), node_type] + roots, None, None, 120.0)
    try:
        doc = json.loads(_clean(out))
    except ValueError:
        return {"ok": False, "addresses": [], "detail": (_clean(err) or _clean(out))[-1000:]}
    return {"ok": rc == 0 and bool(doc.get("ok")), "addresses": list(doc.get("addresses", [])), "detail": None}


# ---- human approval through Weft's signal API ----------------------------------------------------------------
# Routes from upstream crates/weft-dispatcher/src/api/mod.rs (outside_caller_routes); the client shape follows
# upstream's own headless e2e client (crates/weft-e2e/src/signal.rs, human.rs). An approve_reject field takes
# "approve" or "reject" (crates/weft-core/src/signal/form/fields.rs). The signal token rides the Authorization
# header and is never printed.

DECISIONS = ("approve", "reject", "skip")


def _http(method: str, url: str, token: Optional[str] = None, body: Optional[Dict[str, Any]] = None, timeout: float = 15.0) -> Tuple[int, Any]:
    import urllib.error
    import urllib.request
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)
    try:
        return status, json.loads(raw) if raw.strip() else None
    except ValueError:
        return status, raw


def waiting_signals(dispatcher: str, signal_token: str) -> Dict[str, Any]:
    """The nodes waiting on a person that this signal token can see (`GET /signal-token/signals`)."""
    status, doc = _http("GET", dispatcher.rstrip("/") + "/signal-token/signals", token=signal_token)
    if status != 200 or not isinstance(doc, list):
        return {"ok": False, "status": status, "signals": [], "detail": doc if isinstance(doc, str) else None}
    keep = ("nodeId", "kind", "runId", "projectId", "title")
    return {"ok": True, "status": status, "signals": [dict({k: s.get(k) for k in keep if k in s}, token=s.get("token")) for s in doc if isinstance(s, dict)]}


def _node_matches(node_id: str, wanted: str) -> bool:
    """`approve.review` matches a listed node id `approve.review`, `approve/review` or `x.approve.review`."""
    have, want = node_id.replace("/", "."), wanted.replace("/", ".")
    return bool(want) and (have == want or have.endswith("." + want))


def answer_signal(dispatcher: str, signal_token: str, node: str, decision: str, field: str = "decision") -> Dict[str, Any]:
    """Answer the ONE waiting approval whose node id ends with `node`. A person's decision, passed explicitly."""
    if decision not in DECISIONS:
        return {"ok": False, "detail": f"decision must be one of {', '.join(DECISIONS)}"}
    listed = waiting_signals(dispatcher, signal_token)
    if not listed["ok"]:
        return {"ok": False, "detail": f"could not list waiting nodes (HTTP {listed['status']})"}
    matches = [s for s in listed["signals"] if _node_matches(str(s.get("nodeId") or ""), node)]
    if len(matches) != 1:
        return {"ok": False, "detail": f"{len(matches)} waiting node(s) match '{node}'; exactly one must (waiting: "
                                       f"{', '.join(str(s.get('nodeId')) for s in listed['signals']) or 'none'})"}
    link = matches[0]["token"]
    base = dispatcher.rstrip("/") + f"/signal/{link}"
    status, doc = (_http("POST", base + "/skip") if decision == "skip" else _http("POST", base, body={field: decision}))
    return {"ok": 200 <= status < 300, "status": status, "nodeId": matches[0].get("nodeId"), "decision": decision,
            "detail": doc if not (200 <= status < 300) else None}


def harness_check_run(staged: str, h: Dict[str, str], flags: Dict[str, Any], runner: Runner = _run) -> Dict[str, Any]:
    """Judge a run of the staged workflow with upstream's admission check (`run_spec::judge`), through the harness."""
    roots = [os.path.join(h["checkout"], "catalog")] + [os.path.join(staged, "nodes", p) for p in staging.NODE_PACKAGES] + [os.path.join(staged, "src")]
    flags_file = os.path.join(staged, "desk-run-flags.json")
    with open(flags_file, "w", encoding="utf-8") as f:
        json.dump(flags, f)
    rc, out, err = runner([h["exe"], "check-run", staged, os.path.join(staged, "src", "main.weft"), flags_file] + roots, None, None, 120.0)
    result = _check_result("compiler-harness", rc, out, err)
    result["checkout"] = h["checkout"]
    return result
