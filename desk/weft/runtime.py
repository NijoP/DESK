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

    def run(self, staged: str, name: str, inputs: Dict[str, str], durable: bool = True) -> Dict[str, Any]:
        where = self.place(staged, name)
        args = ["--json", "run", "--detach"] + (["--durable"] if durable else [])
        for node, value in inputs.items():
            args += ["--from", f"{node}={json.dumps({'value': value})}"]
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
