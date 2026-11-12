"""Subsystem Six: Mature Routing Engine Orchestrator and Process Supervisor.
Handles binary discovery, Java runtime compatibility probing, version detection,
headless execution enforcement, canonical pass configuration, real-time logging,
watchdog-driven stagnation detection, and execution timeout control.
Zero external dependencies.
"""
from __future__ import annotations
import os
from desk import config as deskcfg
import re
import sys
import json
import time
import shutil
import hashlib
import subprocess
import threading
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


@dataclass
class EngineExecutionResult:
    """Detailed outcome of an external routing engine run."""
    success: bool
    status: str  # "SUCCESS", "TIMEOUT", "STAGNATED", "CRASHED", "INCOMPATIBLE"
    engine_name: str
    engine_version: str
    engine_path: str
    command: List[str]
    duration_sec: float
    returncode: int
    passes_completed: int
    initial_unrouted: Optional[int] = None
    final_unrouted: Optional[int] = None
    ses_generated: bool = False
    ses_path: Optional[str] = None
    ses_size_bytes: int = 0
    stdout_summary: str = ""
    stderr_summary: str = ""
    error_message: Optional[str] = None
    best_unrouted: Optional[int] = None      # lowest unrouted count seen in any pass
    best_pass: Optional[int] = None
    pass_history: List[Dict[str, Any]] = field(default_factory=list)  # [{pass, seconds, score, unrouted}]
    restores_seen: int = 0                   # engine "Restoring an earlier board" events
    engine_config: Dict[str, Any] = field(default_factory=dict)


class PassTracker:
    """Parses Freerouting pass lines and decides when a run has stopped improving.

    Stagnation is "no new best unrouted count for `patience` passes", not "identical counts":
    Freerouting 2.x oscillates (64, 51, 51, 27, 18, 11, 12, 11, 27 ...) so an identical-count
    rule never fires while the run burns its whole timeout.
    """
    # v2.1: "pass #3 ... completed in 24.56 seconds with the score of 711.80 (51 unrouted), ..."
    # v2.5: "pass #3 ... completed in 13.77 seconds with score 912.81 (17 unrouted and 48 violations), ..."
    PASS_RX = re.compile(r"pass\s*#?(\d+).*?completed in\s*([0-9.]+)\s*seconds(?:.*?score(?: of)?\s*([0-9.]+))?"
                         r".*?\((\d+)\s+unrouted(?:\s+and\s+(\d+)\s+violations?)?\)", re.I)
    ALT_RX = re.compile(r"pass\s*#?(\d+)\D.*?(\d+)\s+unrouted", re.I)

    def __init__(self, patience: int = 6):
        self.patience = max(1, int(patience))
        self.history: List[Dict[str, Any]] = []
        self.best_unrouted: Optional[int] = None
        self.best_pass: Optional[int] = None
        self.restores = 0

    def feed(self, line: str) -> Optional[Dict[str, Any]]:
        low = line.lower()
        if "restoring an earlier board" in low:
            self.restores += 1
            return None
        m = self.PASS_RX.search(line)
        rec = None
        if m:
            rec = {"pass": int(m.group(1)), "seconds": float(m.group(2)),
                   "score": float(m.group(3)) if m.group(3) else None, "unrouted": int(m.group(4)),
                   "violations": int(m.group(5)) if m.group(5) else None}
        else:
            m2 = self.ALT_RX.search(line)
            if m2 and ("completed" in low or "unrouted" in low):
                rec = {"pass": int(m2.group(1)), "seconds": None, "score": None, "unrouted": int(m2.group(2))}
        if rec is None:
            return None
        self.history.append(rec)
        if self.best_unrouted is None or rec["unrouted"] < self.best_unrouted:
            self.best_unrouted = rec["unrouted"]
            self.best_pass = rec["pass"]
        return rec

    @property
    def passes(self) -> int:
        return len(self.history)

    @property
    def last_unrouted(self) -> Optional[int]:
        return self.history[-1]["unrouted"] if self.history else None

    @property
    def initial_unrouted(self) -> Optional[int]:
        return self.history[0]["unrouted"] if self.history else None

    def passes_since_best(self) -> int:
        if self.best_pass is None:
            return 0
        return sum(1 for r in self.history if r["pass"] > self.best_pass)

    def stagnated(self) -> bool:
        if self.best_unrouted == 0:
            return False  # done, let the engine finish and write
        return self.passes_since_best() >= self.patience



def find_java(tools_dir: Optional[str] = None) -> str:
    """Java executable for the engine: DESK_JAVA env, then a JDK bundled under library/tools/jdk*/bin,
    then `java` on PATH. A bundled JDK lets Freerouting >= 2.2 (class file 69 = Java 25) run on a host
    whose system Java is older (KF-20261111-006)."""
    env = (deskcfg.get("DESK_JAVA") or "").strip()
    if env and os.path.exists(env):
        return env
    if tools_dir and os.path.isdir(tools_dir):
        cands = []
        for name in sorted(os.listdir(tools_dir), reverse=True):
            if not name.lower().startswith("jdk"):
                continue
            base = os.path.join(tools_dir, name)
            for root, dirs, files in os.walk(base):
                for exe in ("java.exe", "java"):
                    if exe in files and os.path.basename(root) == "bin":
                        cands.append(os.path.join(root, exe))
                if len(root[len(base):].split(os.sep)) > 3:
                    dirs[:] = []
        if cands:
            return cands[0]
    return shutil.which("java") or "java"


class DSNPinMap:
    """Maps DSN pin ids (u1-<padid>) and net names from the (network) block, so engine messages that name
    pins can be reported as net names (rework item D)."""
    NET_RX = re.compile(r"\(net\s+(\S+)\s*\(pins\s+([^)]*)\)", re.S)
    PIN_RX = re.compile(r"\bu\d+-[0-9a-fA-F]{6,}\b")

    def __init__(self, dsn_text: str = ""):
        self.pin_to_net: Dict[str, str] = {}
        for m in self.NET_RX.finditer(dsn_text or ""):
            for pin in m.group(2).split():
                self.pin_to_net[pin] = m.group(1)

    def nets_in(self, text: str) -> List[str]:
        return sorted({self.pin_to_net[p] for p in self.PIN_RX.findall(text or "") if p in self.pin_to_net})

    @classmethod
    def from_file(cls, dsn_path: str) -> "DSNPinMap":
        try:
            with open(dsn_path, encoding="utf-8", errors="ignore") as f:
                return cls(f.read())
        except Exception:
            return cls("")


def write_progress(path: str, payload: Dict[str, Any]) -> None:
    """Atomic progress.json for the Captain / Mission Control; never raises."""
    try:
        from desk.fsutil import atomic_write_json
        atomic_write_json(path, payload, indent=1)
    except Exception:
        pass


class RoutingEngineOrchestrator:
    """Supervisor for detailed routing backends (Freerouting JAR / native executable)."""

    CANDIDATE_JARS = [
        "freerouting.jar",
        "freerouting-2.5.0.jar",
        "freerouting-2.4.1.jar",
        "freerouting-2.2.4.jar",
        "freerouting-2.0.1.jar",
    ]

    def __init__(self, tools_dir: Optional[str] = None):
        if not tools_dir:
            # Default to <repo_root>/library/tools
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tools_dir = os.path.join(base, "library", "tools")
        self.tools_dir = tools_dir
        self.last_discovery_note = ""
        self.java = find_java(tools_dir)

    def discover_engine(self, explicit_path: Optional[str] = None) -> Tuple[str, str, str]:
        """Discovers a working routing engine binary / JAR compatible with the host environment.
        Returns: (engine_type, path_or_jar, version_string)
        engine_type is 'NATIVE' or 'JAR'.
        """
        # 1. Check explicit path from env or parameter
        target = explicit_path or deskcfg.get("FREEROUTING_BIN") or deskcfg.get("FREEROUTING_JAR")
        if target and os.path.exists(target):
            is_jar = target.lower().endswith(".jar")
            if is_jar:
                compat, ver = self._probe_jar_compatibility(target)
                if compat:
                    return ("JAR", target, ver)
            else:
                compat, ver = self._probe_native_compatibility(target)
                if compat:
                    return ("NATIVE", target, ver)

        # 2. Check for native executable in tools_dir or on PATH
        for exe_name in ["freerouting.exe", "freerouting"]:
            p = os.path.join(self.tools_dir, exe_name)
            if os.path.exists(p) and os.access(p, os.X_OK):
                compat, ver = self._probe_native_compatibility(p)
                if compat:
                    return ("NATIVE", p, ver)
            which_p = shutil.which(exe_name)
            if which_p:
                compat, ver = self._probe_native_compatibility(which_p)
                if compat:
                    return ("NATIVE", which_p, ver)

        # 3. Check candidate JARs in tools_dir: probe every one and pick the HIGHEST compatible version.
        #    (Previously the first match won, so freerouting.jar = v2.1.0 was used while v2.5.0 sat beside it.)
        if not (os.path.exists(self.java) or shutil.which(self.java)):
            raise RuntimeError("Java executable not found (DESK_JAVA, library/tools/jdk*/bin, or PATH). Install Java 25 "
                               "for Freerouting >= 2.2 or Java 17+ for 2.1.")

        found: List[Tuple[Tuple[int, ...], str, str]] = []
        incompatible: List[str] = []
        # Probe newest first (by the version in the file name; the unversioned freerouting.jar last) and stop at
        # the first JAR that starts: each failed probe can cost its full timeout.
        present = [n for n in self.CANDIDATE_JARS if os.path.exists(os.path.join(self.tools_dir, n))]
        present.sort(key=lambda n: (self._version_tuple(n) if re.search(r"\d", n) else (0,)), reverse=True)
        for jar_name in present:
            jar_path = os.path.join(self.tools_dir, jar_name)
            compat, ver = self._probe_jar_compatibility(jar_path)
            if compat:
                found.append((self._version_tuple(ver), jar_path, ver))
                break
            incompatible.append(f"{jar_name} ({ver})")
        if found:
            found.sort(key=lambda t: t[0], reverse=True)
            self.last_discovery_note = (
                f"selected {os.path.basename(found[0][1])} {found[0][2]}; incompatible: {incompatible}" if incompatible
                else f"selected {os.path.basename(found[0][1])} {found[0][2]}")
            return ("JAR", found[0][1], found[0][2])

        raise RuntimeError(
            f"No compatible Freerouting engine found in '{self.tools_dir}'. "
            + (f"Present but needing a newer Java: {incompatible}. " if incompatible else "")
            + "Install a Java runtime matching the JAR (v2.2+ needs Java 25) or set FREEROUTING_JAR."
        )

    @staticmethod
    def _version_tuple(ver: str) -> Tuple[int, ...]:
        nums = re.findall(r"\d+", ver or "")
        return tuple(int(n) for n in nums[:3]) if nums else (0,)

    @staticmethod
    def global_config_path() -> str:
        """Freerouting 2.1.0 ignores the per-run freerouting.json and reads this file instead (INC-007)."""
        base = os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"
        return os.path.join(base, "freerouting", "freerouting.json")

    def _probe_jar_compatibility(self, jar_path: str) -> Tuple[bool, str]:
        """Tests whether a JAR can be loaded by the installed Java VM without class version errors."""
        try:
            cmd = [self.java, "-jar", jar_path, "--help"]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
            combined = proc.stdout + proc.stderr

            if "UnsupportedClassVersionError" in combined:
                return (False, "UnsupportedClassVersionError")

            # Extract version if present
            ver = "v2.x"
            for line in combined.splitlines():
                if "Freerouting v" in line:
                    parts = line.split("Freerouting v")
                    if len(parts) > 1:
                        ver = "v" + parts[1].split()[0].strip()
                        break

            # If help printed or exit code indicates CLI flag error (standard for freerouting missing -de/-do)
            if "Both an input file and an output file must be specified" in combined or proc.returncode in (0, 1):
                return (True, ver)
            return (False, "Execution failed")
        except subprocess.TimeoutExpired as e:
            # Freerouting 2.1.0 prints its banner within ~2 s and then blocks on its online version check
            # ("New version available") for > 60 s, so `--help` times out although the JVM loaded the JAR.
            # A banner without UnsupportedClassVersionError proves class-version compatibility (UPS_1000 F-007).
            out = e.stdout or b""
            err = e.stderr or b""
            combined = (out.decode("utf-8", "replace") if isinstance(out, bytes) else out) + \
                       (err.decode("utf-8", "replace") if isinstance(err, bytes) else err)
            if "Freerouting v" in combined and "UnsupportedClassVersionError" not in combined:
                ver = "v" + combined.split("Freerouting v", 1)[1].split()[0].strip()
                return (True, ver)
            return (False, f"probe timed out without a Freerouting banner: {e}")
        except Exception as e:
            return (False, str(e))

    def _probe_native_compatibility(self, exe_path: str) -> Tuple[bool, str]:
        """Tests whether a native executable can execute."""
        try:
            proc = subprocess.run([exe_path, "--help"], capture_output=True, text=True, timeout=10)
            combined = proc.stdout + proc.stderr
            ver = "native"
            for line in combined.splitlines():
                if "Freerouting" in line:
                    ver = line.strip()
                    break
            return (True, ver)
        except Exception as e:
            return (False, str(e))

    @staticmethod
    def compute_file_sha256(filepath: str) -> str:
        """Computes SHA-256 of the engine binary for cryptographic provenance."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def build_config(job_timeout_str: str = "00:05:00",
                     max_passes: int = 30,
                     stagnation_pass_limit: Optional[int] = None,
                     priority_net_classes: Optional[List[str]] = None,
                     plane_nets: Optional[List[str]] = None,
                     via_costs: Optional[int] = None,
                     optimizer_passes: int = 3,
                     max_threads: Optional[int] = None) -> Dict[str, Any]:
        """Freerouting settings DESK's intelligence can actually drive (docs/settings.md, v2.x):

        * autorouter.priority_net_classes  <- DensePCBIntelligence.priority_net_order (DSN has one class per net)
        * plane_nets                        <- placement.json planes
        * autorouter.stagnation_pass_limit  <- stop when the engine itself sees no improvement (v2.2+)
        * via_costs                         <- raised on boards with few routable layers
        Keys unknown to an older engine are ignored by it.
        """
        router: Dict[str, Any] = {
            "job_timeout": job_timeout_str,
            "max_passes": max_passes,                      # Freerouting 2.1.x key (router.max_passes)
            "autorouter": {"enabled": True, "max_passes": max_passes},   # 2.4+ key
            "optimizer": {"enabled": optimizer_passes > 0, "max_passes": max(0, optimizer_passes)},
        }
        if stagnation_pass_limit is not None:
            router["autorouter"]["stagnation_pass_limit"] = int(stagnation_pass_limit)
        if priority_net_classes:
            router["autorouter"]["priority_net_classes"] = list(priority_net_classes)
        if plane_nets:
            router["plane_nets"] = list(plane_nets)
        if via_costs is not None:
            router["via_costs"] = int(via_costs)
        if max_threads is not None:
            router["max_threads"] = int(max_threads)
            router["optimizer"]["max_threads"] = int(max_threads)
        return {"gui": {"enabled": False, "currentLocale": "en"},
                "profile": {"allow_telemetry": False, "allow_contact": False},
                "router": router}

    @classmethod
    def ensure_headless_config(cls, working_dir: str, job_timeout_str: str = "00:05:00", max_passes: int = 30,
                               **settings) -> str:
        """Writes the headless freerouting.json into working_dir (v2.2+ reads it from the CWD).
        Fixes BN-004 (modal GUI hang) and BN-007 (pass 999 termination loop)."""
        cfg_path = os.path.join(working_dir, "freerouting.json")
        cfg = cls.build_config(job_timeout_str, max_passes=max_passes, **settings)
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg_path

    @staticmethod
    def legacy_router_keys(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Freerouting 2.1.x only understands a flat router block (job_timeout, max_passes, optimizer.max_passes,
        scoring.*). Unknown nested keys can make it fall back to its defaults (12 h / 9999 passes, observed
        2026-11-12), so only the keys it knows are merged into its global file."""
        r = cfg.get("router", {})
        out: Dict[str, Any] = {"job_timeout": r.get("job_timeout"), "max_passes": r.get("max_passes")}
        if "optimizer" in r and "max_passes" in r["optimizer"]:
            out["optimizer"] = {"max_passes": r["optimizer"]["max_passes"]}
        if "max_threads" in r:
            out["optimizer"] = {**out.get("optimizer", {}), "max_threads": r["max_threads"]}
        if "via_costs" in r:
            out["scoring"] = {"via_costs": r["via_costs"]}
        return {k: v for k, v in out.items() if v is not None}

    @classmethod
    def install_global_config(cls, cfg: Dict[str, Any]) -> Optional[str]:
        """Freerouting 2.1.0 only honours %TEMP%/freerouting/freerouting.json (INC-007). Merge DESK's
        router settings into it for the duration of a run; returns the backup path to restore afterwards,
        or None when nothing was written."""
        path = cls.global_config_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            existing: Dict[str, Any] = {}
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    existing = json.load(f)
            backup = path + ".desk-backup"
            with open(backup, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
            merged = dict(existing)
            merged.setdefault("gui", {}).update(cfg.get("gui", {}))
            router = dict(merged.get("router", {}))
            for k, v in cls.legacy_router_keys(cfg).items():
                if isinstance(v, dict) and isinstance(router.get(k), dict):
                    router[k] = {**router[k], **v}
                else:
                    router[k] = v
            merged["router"] = router
            merged.setdefault("profile", {}).update({"allow_telemetry": False, "allow_contact": False})
            with open(path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            return backup
        except Exception:
            return None

    @classmethod
    def restore_global_config(cls, backup: Optional[str]) -> None:
        if not backup or not os.path.exists(backup):
            return
        try:
            os.replace(backup, cls.global_config_path())
        except Exception:
            pass

    # ---- execute_routing, split into testable pieces (T-15) -------------------------------------------
    @staticmethod
    def timeout_str(timeout_sec: float) -> str:
        """Freerouting job_timeout string (HH:MM:SS) for a budget in seconds; minimum one minute."""
        mins = max(1, int(timeout_sec // 60))
        secs = int(timeout_sec % 60)
        return f"00:{mins:02d}:{secs:02d}"

    def prepare_engine_config(self, wd: str, engine_ver: str, timeout_sec: float, max_passes: int,
                              stagnation_patience: int, priority_net_classes: Optional[List[str]],
                              plane_nets: Optional[List[str]], via_costs: Optional[int], max_threads: int
                              ) -> Tuple[Dict[str, Any], Optional[str], str]:
        """Headless configuration for one run: per-run file for v2.2+, global file for v2.1 (INC-007).
        Returns (cfg, global_backup_path_or_None, timeout_str)."""
        timeout_str = self.timeout_str(timeout_sec)
        settings = dict(stagnation_pass_limit=stagnation_patience, priority_net_classes=priority_net_classes,
                        plane_nets=plane_nets, via_costs=via_costs, max_threads=max_threads)
        cfg = self.build_config(timeout_str, max_passes=max_passes, **settings)
        self.ensure_headless_config(wd, job_timeout_str=timeout_str, max_passes=max_passes, **settings)
        global_backup = self.install_global_config(cfg) if self._version_tuple(engine_ver) < (2, 2) else None
        return cfg, global_backup, timeout_str

    def build_command(self, engine_type: str, engine_path: str, engine_ver: str, dsn_path: str, ses_path: str,
                      max_passes: int, max_threads: int, timeout_str: str, stagnation_patience: int,
                      priority_net_classes: Optional[List[str]] = None, plane_nets: Optional[List[str]] = None,
                      via_costs: Optional[int] = None, input_ses: Optional[str] = None) -> List[str]:
        """Canonical Freerouting command line. Pure (no process, no file writes), so it is unit-tested without Java."""
        cmd: List[str] = [self.java, "-jar", engine_path] if engine_type == "JAR" else [engine_path]
        design_arg = os.path.abspath(dsn_path)
        if input_ses and os.path.exists(input_ses):
            design_arg += "+" + os.path.abspath(input_ses)
        cmd.extend(["-de", design_arg, "-do", os.path.abspath(ses_path), "-mp", str(max_passes),
                    "-mt", str(max_threads), "--gui.enabled=false"])
        if self._version_tuple(engine_ver) >= (2, 2):
            cmd.append(f"--router.autorouter.max_passes={max_passes}")
            if deskcfg.get_bool("DESK_FR_STAGNATION_FLAG", False):
                # documented for newer builds; v2.5.0 rejects it ("No field found ... stagnation_pass_limit")
                cmd.append(f"--router.autorouter.stagnation_pass_limit={int(stagnation_patience)}")
            cmd.append(f"--router.job_timeout={timeout_str}")
            if priority_net_classes:
                cmd.append("--router.autorouter.priority_net_classes=" + ",".join(priority_net_classes))
            if plane_nets:
                cmd.append("--router.plane_nets=" + ",".join(plane_nets))
            if via_costs is not None:
                cmd.append(f"--router.via_costs={int(via_costs)}")
        return cmd

    def supervise(self, cmd: List[str], wd: str, timeout_sec: float, t0: float, tracker: "PassTracker",
                  pin_map: "DSNPinMap", problem_nets: Dict[str, int], publish: Any, log_callback: Optional[Any]
                  ) -> Tuple["subprocess.Popen", List[str], List[str], bool, bool]:
        """Start the engine, stream its output through the pass tracker, publish progress, and stop it on
        budget overrun (or on stagnation on POSIX). Returns (proc, stdout_lines, stderr_lines, timed_out, stagnated)."""
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        state = {"stagnated": False}
        proc = subprocess.Popen(cmd, cwd=wd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                bufsize=1, universal_newlines=True)

        def read_stdout():
            for line in proc.stdout:
                clean_line = line.strip()
                if clean_line:
                    stdout_lines.append(clean_line)
                    if log_callback:
                        log_callback(clean_line)
                    for net in pin_map.nets_in(clean_line):
                        problem_nets[net] = problem_nets.get(net, 0) + 1
                    rec = tracker.feed(clean_line)
                    if rec is not None:
                        publish("routing")
                        if tracker.stagnated():
                            state["stagnated"] = True

        def read_stderr():
            for line in proc.stderr:
                clean_line = line.strip()
                if clean_line:
                    stderr_lines.append(clean_line)

        t_out = threading.Thread(target=read_stdout, daemon=True)
        t_err = threading.Thread(target=read_stderr, daemon=True)
        t_out.start()
        t_err.start()

        timed_out = False
        while proc.poll() is None:
            elapsed = time.time() - t0
            # Freerouting's own job_timeout equals timeout_sec; give it a grace period to exit by itself and write
            # the SES (-do) with its best board instead of killing it at the same instant and losing the result.
            if elapsed > timeout_sec + 120.0:
                timed_out = True
                self._graceful_stop(proc)
                break
            if state["stagnated"] and tracker.passes >= 5 and os.name != "nt":
                # POSIX: SIGINT lets the JVM run its shutdown hooks. On Windows a child JVM cannot be
                # stopped gracefully and the SES is written only when the engine ends on its own
                # (measured 2026-11-12: a plateau terminate at pass 17 lost a 4-unrouted board), so on
                # Windows the plateau is only recorded; the run ends via max_passes/job_timeout.
                # Use execute_routing_chunked() for bounded runs that always keep a SES.
                self._graceful_stop(proc)
                break
            time.sleep(0.2)
        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        return proc, stdout_lines, stderr_lines, timed_out, state["stagnated"]

    @staticmethod
    def classify_outcome(timed_out: bool, stagnated: bool, returncode: Optional[int], ses_exists: bool, ses_size: int,
                         final_unrouted: Optional[int], timeout_sec: float, stagnation_patience: int,
                         best_unrouted: Optional[int] = None, best_pass: Optional[int] = None
                         ) -> Tuple[str, Optional[str], bool]:
        """Map the raw facts of a run to (status, error_message, success). Pure; unit-tested.

        Order matters and is unchanged from the original implementation: an explicit budget overrun first,
        then a partial SES written at the engine's own job_timeout, then stagnation, then crash, then no SES."""
        if timed_out:
            return "TIMEOUT", f"Routing engine exceeded timeout budget of {timeout_sec:.1f}s", False
        if ses_exists and ses_size > 0 and returncode != 0 and (final_unrouted or 0) > 0:
            return "TIMEOUT_PARTIAL", f"Engine stopped at its job_timeout with {final_unrouted} unrouted; partial SES kept", True
        if stagnated:
            msg = (f"No new best unrouted count for {stagnation_patience} passes "
                   f"(best {best_unrouted} at pass {best_pass}, last {final_unrouted})")
            return "STAGNATED", msg, bool(ses_exists and ses_size > 0)   # partial success if copper was written
        if returncode != 0:
            return "CRASHED", f"Engine process exited with non-zero code {returncode}", False
        if not ses_exists or ses_size == 0:
            return "NO_SES", "Engine finished but did not generate a valid non-empty SES file", False
        return "SUCCESS", None, True

    @staticmethod
    def _progress_publisher(progress_path: str, engine_ver: str, t0: float, tracker: "PassTracker",
                            timeout_sec: float, problem_nets: Dict[str, int]):
        """Closure that writes state/route/progress.json (read by Mission Control) for a phase name."""
        def publish(phase: str) -> None:
            write_progress(progress_path, {
                "phase": phase, "engine": engine_ver, "elapsed_s": round(time.time() - t0, 1),
                "passes": tracker.passes, "initial_unrouted": tracker.initial_unrouted,
                "last_unrouted": tracker.last_unrouted, "best_unrouted": tracker.best_unrouted,
                "best_pass": tracker.best_pass, "passes_since_best": tracker.passes_since_best(),
                "restores": tracker.restores, "budget_s": timeout_sec,
                "problem_nets": sorted(problem_nets, key=lambda n: -problem_nets[n])[:20],
                "history": tracker.history[-50:],
            })
        return publish

    def execute_routing(
        self,
        dsn_path: str,
        ses_path: str,
        max_passes: int = 30,
        timeout_sec: float = 300.0,
        working_dir: Optional[str] = None,
        explicit_engine: Optional[str] = None,
        stagnation_patience: int = 6,
        log_callback: Optional[Any] = None,
        priority_net_classes: Optional[List[str]] = None,
        plane_nets: Optional[List[str]] = None,
        input_ses: Optional[str] = None,
        via_costs: Optional[int] = None,
        max_threads: int = 1,
    ) -> EngineExecutionResult:
        """Executes the routing engine with full process supervision, streaming logs,
        improvement-based stagnation detection, and bounded timeout.

        priority_net_classes: DSN class names (= net names in EasyEDA exports) the engine should route
            first; from DensePCBIntelligence.priority_net_order.
        plane_nets: nets served by copper planes (pad-to-plane vias instead of corridors).
        input_ses: a previous session to start from (-de board.dsn+previous.ses), which keeps routed
            copper so a run continues a partial result instead of rerouting the whole board.
        """
        if not os.path.exists(dsn_path):
            raise FileNotFoundError(f"Input DSN file not found: {dsn_path}")
        wd = working_dir or os.path.dirname(os.path.abspath(ses_path))
        os.makedirs(wd, exist_ok=True)

        engine_type, engine_path, engine_ver = self.discover_engine(explicit_engine)
        cfg, global_backup, timeout_str = self.prepare_engine_config(
            wd, engine_ver, timeout_sec, max_passes, stagnation_patience, priority_net_classes, plane_nets,
            via_costs, max_threads)
        cmd = self.build_command(engine_type, engine_path, engine_ver, dsn_path, ses_path, max_passes, max_threads,
                                 timeout_str, stagnation_patience, priority_net_classes, plane_nets, via_costs, input_ses)

        t0 = time.time()
        tracker = PassTracker(patience=stagnation_patience)
        pin_map = DSNPinMap.from_file(dsn_path)
        progress_path = os.path.join(wd, "progress.json")
        problem_nets: Dict[str, int] = {}

        publish = self._progress_publisher(progress_path, engine_ver, t0, tracker, timeout_sec, problem_nets)
        publish("starting")

        proc, stdout_lines, stderr_lines, timed_out, stagnated = self.supervise(
            cmd, wd, timeout_sec, t0, tracker, pin_map, problem_nets, publish, log_callback)
        dur = round(time.time() - t0, 2)
        self.restore_global_config(global_backup)
        ses_exists = os.path.exists(ses_path)
        publish("finished" if ses_exists else ("timeout" if timed_out else "stopped"))
        ses_size = os.path.getsize(ses_path) if ses_exists else 0

        status, err_msg, success = self.classify_outcome(
            timed_out, stagnated, proc.returncode, ses_exists, ses_size, tracker.last_unrouted, timeout_sec,
            stagnation_patience, tracker.best_unrouted, tracker.best_pass)

        try:
            with open(os.path.join(wd, "freerouting.log"), "w", encoding="utf-8") as f:
                f.write("\n".join(stdout_lines + stderr_lines))
        except OSError:
            pass

        return EngineExecutionResult(
            success=success, status=status, engine_name="Freerouting", engine_version=engine_ver,
            engine_path=engine_path, command=cmd, duration_sec=dur, returncode=proc.returncode or 0,
            passes_completed=tracker.passes, initial_unrouted=tracker.initial_unrouted,
            final_unrouted=tracker.last_unrouted, ses_generated=ses_exists,
            ses_path=ses_path if ses_exists else None, ses_size_bytes=ses_size,
            stdout_summary="\n".join(stdout_lines[:50]), stderr_summary="\n".join(stderr_lines[:50]),
            error_message=err_msg, best_unrouted=tracker.best_unrouted, best_pass=tracker.best_pass,
            pass_history=list(tracker.history), restores_seen=tracker.restores,
            engine_config=cfg.get("router", {}),
        )

    @staticmethod
    def _graceful_stop(proc: "subprocess.Popen", wait_s: float = 30.0) -> None:
        """Ask the engine to stop and give it time to write its output. POSIX: SIGINT runs the JVM shutdown
        hooks; Windows has no equivalent for a child console process, so terminate() is used and the SES is
        only present if the engine wrote it itself (engines >= 2.2 do on stagnation/max_passes)."""
        import signal
        try:
            if os.name != "nt":
                proc.send_signal(signal.SIGINT)
            else:
                proc.terminate()
            proc.wait(timeout=wait_s)
        except subprocess.TimeoutExpired:
            proc.kill()
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def smoke_test(self, dsn_path: str, working_dir: str, max_passes: int = 2, timeout_sec: float = 90.0) -> EngineExecutionResult:
        """Rework item B: before any long run, prove on this host that the engine starts, routes and WRITES a
        SES. A smoke run that returns no SES is a tool defect; the caller must not start a 15-minute run."""
        ses = os.path.join(working_dir, "smoke.ses")
        try:
            os.remove(ses)
        except OSError:
            pass
        res = self.execute_routing(dsn_path=dsn_path, ses_path=ses, max_passes=max_passes, timeout_sec=timeout_sec,
                                   working_dir=working_dir, stagnation_patience=max_passes)
        res.status = res.status if res.ses_generated else "SMOKE_NO_SES"
        res.success = bool(res.ses_generated)
        if not res.ses_generated:
            res.error_message = (f"smoke run produced no SES with engine {res.engine_version} on this host: "
                                 "the engine cannot return a partial board here (KF-20261111-006). Install Java 25 so "
                                 "Freerouting >= 2.2 is used, or route with EasyEDA's native autorouter.")
        return res

    def execute_routing_chunked(
        self,
        dsn_path: str,
        ses_path: str,
        working_dir: str,
        chunk_passes: int = 6,
        max_chunks: int = 8,
        plateau_chunks: int = 2,
        budget_sec: float = 1200.0,
        chunk_timeout_sec: float = 300.0,
        log_callback: Optional[Any] = None,
        first_passes: int = 2,
        safety: Optional[float] = None,
        checkpoint_dir: Optional[str] = None,
        engine_version_hint: str = "",
        **engine_kwargs,
    ) -> EngineExecutionResult:
        """Bounded, resumable routing that NEVER discards a valid SES (UPS_1000 F-012; INC-20261112-009).

        * Every chunk is sized from the pass durations measured so far (`desk.routing.adaptive.ChunkPlanner`):
          the first chunk runs `first_passes` passes to measure the board; later chunks fit as many passes as
          `safety` x `chunk_timeout_sec` allows (at most `chunk_passes`), or one pass with a longer window when a
          single pass is slower than the window. A static four-pass / 300 s chunk is what lost every UPS_1000 run.
        * The best valid SES lives in a `RoutingCheckpoint` (`checkpoint_dir`, default <working_dir>/checkpoint);
          a candidate is adopted only after it parses and carries routes, and only when it improves on the best.
          A chunk that times out, crashes or writes a corrupt file leaves the checkpoint untouched.
        * The engine profile (`desk.routing.engine_profiles`) says whether the engine can end a chunk by itself.
          Freerouting 2.1.x ignores max_passes and job_timeout on this host, so with that engine the run is
          refused up front (status ENGINE_UNBOUNDABLE) instead of burning the budget and importing nothing.
        * Each chunk's outcome is named (`adaptive.chunk_outcome`) so the supervisor can tell CHUNK_TIMEOUT from
          ENGINE_TIMEOUT, SES_NOT_GENERATED, SES_CORRUPTED, SES_NOT_IMPROVED and ENGINE_IGNORES_LIMITS.
        Stops when a chunk reaches 0 unrouted, when `plateau_chunks` consecutive chunks fail to improve, when a
        chunk returns no SES, when `max_chunks` or `budget_sec` is reached.
        """
        from desk.routing.adaptive import ChunkPlanner, PassStats
        t0 = time.time()
        run = self._chunk_setup(dsn_path, working_dir, checkpoint_dir, engine_version_hint, engine_kwargs,
                                chunk_timeout_sec, chunk_passes, first_passes, safety)
        run.update(budget_sec=budget_sec, plateau_chunks=plateau_chunks, cfg_meta={
            "chunk_passes": chunk_passes, "max_chunks": max_chunks, "plateau_chunks": plateau_chunks, "budget_sec": budget_sec,
            "chunk_timeout_sec": chunk_timeout_sec, "first_passes": first_passes, "safety": run["safety"],
            "engine_profile": run["profile"].to_dict()})
        ckpt = run["ckpt"]
        if run["profile"].boundable is False:
            return self._unboundable_result(run, ses_path, t0)
        planner: ChunkPlanner = run["planner"]
        stats = PassStats()
        history: List[Dict[str, Any]] = []
        plans: List[Dict[str, Any]] = []
        outcomes: List[str] = []
        failure_category: Optional[str] = None
        since_improvement = 0
        last: Optional[EngineExecutionResult] = None
        for chunk in range(1, max_chunks + 1):
            remaining = budget_sec - (time.time() - t0)
            if remaining < 30.0:
                outcomes.append("BUDGET_EXHAUSTED")
                break
            plan = planner.plan(stats, remaining)
            plans.append({"chunk": chunk, **plan.to_dict()})
            if plan.passes <= 0:
                outcomes.append("BUDGET_EXHAUSTED")
                break
            last, rec, outcome = self._run_chunk(run, chunk, plan, remaining, dsn_path, working_dir, log_callback, engine_kwargs, stats)
            history.append(rec)
            outcomes.append(outcome)
            write_progress(os.path.join(working_dir, "progress_chunks.json"), {
                "chunks": history, "best_unrouted": ckpt.best_unrouted, "observed_best_unrouted": ckpt.state.observed_best_unrouted,
                "elapsed_s": round(time.time() - t0, 1), "budget_s": budget_sec, "plans": plans, "outcomes": outcomes,
                "checkpoint": ckpt.summary()})
            verdict = self._chunk_verdict(outcome, rec, plan, last, stats, ckpt, plateau_chunks, since_improvement)
            since_improvement = verdict["since_improvement"]
            if verdict.get("note"):
                outcomes.append(verdict["note"])
            if verdict.get("stop"):
                failure_category = verdict.get("failure_category")
                break
        ckpt.export(ses_path)
        return self._chunked_result(ses_path, history, ckpt.best_unrouted, last, round(time.time() - t0, 2), run["cfg_meta"],
                                    outcomes=outcomes, plans=plans, failure_category=failure_category, checkpoint=ckpt.summary())

    def _chunk_setup(self, dsn_path: str, working_dir: str, checkpoint_dir: Optional[str], engine_version_hint: str,
                     engine_kwargs: Dict[str, Any], chunk_timeout_sec: float, chunk_passes: int, first_passes: int,
                     safety: Optional[float]) -> Dict[str, Any]:
        """Engine profile, checkpoint (seeded from `input_ses` when given) and planner for a chunked run."""
        from desk.routing.adaptive import ChunkPlanner
        from desk.routing.checkpoint import RoutingCheckpoint
        from desk.routing.engine_profiles import profile_for, UNKNOWN as UNKNOWN_PROFILE
        input_ses = engine_kwargs.pop("input_ses", None)
        input_unrouted = engine_kwargs.pop("input_unrouted", None)
        engine_ver = engine_version_hint
        if not engine_ver:
            try:
                _, _, engine_ver = self.discover_engine(engine_kwargs.get("explicit_engine"))
            except Exception:
                engine_ver = ""
        profile = profile_for(engine_ver) if engine_ver else UNKNOWN_PROFILE
        try:
            dsn_sha = self.compute_file_sha256(dsn_path)
        except Exception:
            dsn_sha = ""
        ckpt = RoutingCheckpoint(checkpoint_dir or os.path.join(working_dir, "checkpoint"), dsn_sha256=dsn_sha,
                                 engine_version=engine_ver)
        if input_ses and os.path.exists(input_ses) and not ckpt.has_best():
            ckpt.offer(input_ses, int(input_unrouted) if input_unrouted is not None else None, chunk=0, meta={"source": "input_ses"})
            if not ckpt.has_best():
                import shutil as _sh      # operator-supplied SES with unknown count still seeds the continuation
                _sh.copyfile(input_ses, ckpt.best_path)
                ckpt.state.best_ses = ckpt.best_path
                ckpt._save()
        if safety is None:
            try:
                safety = float(deskcfg.get("DESK_FR_CHUNK_SAFETY") or 0.6)
            except (TypeError, ValueError):
                safety = 0.6
        planner = ChunkPlanner(window_s=chunk_timeout_sec, safety=safety, min_passes=1, max_passes=chunk_passes,
                               first_passes=first_passes, profile=profile)
        return {"engine_ver": engine_ver, "profile": profile, "ckpt": ckpt, "planner": planner, "safety": safety}

    def _unboundable_result(self, run: Dict[str, Any], ses_path: str, t0: float) -> EngineExecutionResult:
        """The engine cannot end a chunk by itself (Freerouting 2.1.x on this host): refuse before burning the budget."""
        ckpt, profile, engine_ver = run["ckpt"], run["profile"], run["engine_ver"]
        msg = (f"engine {engine_ver} ({profile.name}) ignores max_passes and job_timeout on this host and writes its SES "
               "only at 100 %; a bounded chunk cannot end by itself and stopping the JVM loses the board "
               "(KF-20261111-006, UPS_1000 attempts 5-6). Use Freerouting >= 2.5 with the bundled JDK 25 "
               "(library/tools/jdk25) or set FREEROUTING_JAR to it.")
        res = self._chunked_result(ses_path, [], ckpt.best_unrouted, None, round(time.time() - t0, 2), run["cfg_meta"],
                                   outcomes=["ENGINE_UNBOUNDABLE"], plans=[], failure_category="EXTERNAL_TOOL_UNSUPPORTED",
                                   checkpoint=ckpt.summary(), error=msg)
        res.status, res.engine_version = "ENGINE_UNBOUNDABLE", engine_ver
        if ckpt.export(ses_path):
            res.ses_generated, res.ses_path, res.ses_size_bytes = True, ses_path, os.path.getsize(ses_path)
        return res

    def _run_chunk(self, run: Dict[str, Any], chunk: int, plan: Any, remaining: float, dsn_path: str, working_dir: str,
                   log_callback: Optional[Any], engine_kwargs: Dict[str, Any], stats: Any
                   ) -> Tuple[EngineExecutionResult, Dict[str, Any], str]:
        """Run one chunk from the checkpoint, offer its SES to the checkpoint, name the outcome."""
        from desk.routing.adaptive import chunk_outcome
        from desk.routing.engine_profiles import profile_for
        ckpt = run["ckpt"]
        chunk_ses = os.path.join(working_dir, f"chunk_{chunk:02d}.ses")
        try:
            os.remove(chunk_ses)
        except OSError:
            pass
        res = self.execute_routing(
            dsn_path=dsn_path, ses_path=chunk_ses, max_passes=plan.passes, timeout_sec=min(plan.timeout_s, remaining),
            working_dir=working_dir, stagnation_patience=max(plan.passes, 99),   # never stop a chunk early
            log_callback=log_callback, input_ses=ckpt.resume_input(), **engine_kwargs)
        if res.engine_version and res.engine_version != run["engine_ver"]:
            run["engine_ver"] = res.engine_version
            run["profile"] = profile_for(res.engine_version)
            run["planner"].profile = run["profile"]
            run["cfg_meta"]["engine_profile"] = run["profile"].to_dict()
        stats.extend_from_history(res.pass_history)
        for p in res.pass_history:
            ckpt.observe_pass(p.get("unrouted"))
        final = res.final_unrouted if res.final_unrouted is not None else res.best_unrouted
        offer = ckpt.offer(chunk_ses, final, chunk, meta={"status": res.status, "passes": res.passes_completed,
                                                          "seconds": res.duration_sec}) if res.ses_generated else None
        accepted = bool(offer and offer.get("accepted"))
        ses_valid = None if offer is None else bool(offer["validation"]["valid"])
        outcome = chunk_outcome(timed_out=res.status == "TIMEOUT", passes=res.passes_completed, ses_generated=res.ses_generated,
                                ses_valid=ses_valid, returncode=res.returncode, planned_passes=plan.passes if plan.bounded else None,
                                unrouted_final=final, improved=accepted, status=res.status)
        rec = {"chunk": chunk, "status": res.status, "outcome": outcome, "passes": res.passes_completed, "planned_passes": plan.passes,
               "seconds": res.duration_sec, "initial_unrouted": res.initial_unrouted, "final_unrouted": final, "ses": res.ses_generated,
               "ses_valid": ses_valid, "accepted": accepted, "pass_history": res.pass_history}
        return res, rec, outcome

    @staticmethod
    def _chunk_verdict(outcome: str, rec: Dict[str, Any], plan: Any, res: EngineExecutionResult, stats: Any, ckpt: Any,
                       plateau_chunks: int, since_improvement: int) -> Dict[str, Any]:
        """Decide whether the chunked run continues. Pure apart from `stats` (a measured pass may be added)."""
        tool_defects = {"ENGINE_IGNORES_LIMITS": "EXTERNAL_TOOL_UNSUPPORTED", "ZERO_PASSES_TIMEOUT": "ROUTER_ENGINE_CRASH",
                        "ENGINE_CRASH": "ROUTER_ENGINE_CRASH", "SES_NOT_GENERATED": "ROUTER_SES_MISSING",
                        "SES_CORRUPTED": "ROUTER_SES_INVALID"}
        if outcome in tool_defects:
            return {"stop": True, "failure_category": tool_defects[outcome], "since_improvement": since_improvement}
        if outcome == "CHUNK_TIMEOUT":
            if plan.confidence == "UNVERIFIED" and res.passes_completed > 0 and not stats.n:
                stats.add(res.duration_sec / max(1, res.passes_completed))   # widen once from the measured rate
                return {"stop": False, "since_improvement": since_improvement}
            return {"stop": True, "failure_category": "ROUTER_ENGINE_TIMEOUT", "since_improvement": since_improvement}
        if rec["final_unrouted"] is None:
            return {"stop": True, "failure_category": "ROUTER_SES_INVALID", "since_improvement": since_improvement}
        since = 0 if rec["accepted"] else since_improvement + 1
        if rec["final_unrouted"] == 0:
            return {"stop": True, "failure_category": None, "since_improvement": since, "note": "FULL_ROUTING_SUCCESS"}
        if since >= plateau_chunks:
            return {"stop": True, "failure_category": "ROUTER_STAGNATION" if ckpt.best_unrouted else None,
                    "since_improvement": since, "note": "PLATEAU"}
        return {"stop": False, "since_improvement": since}

    @staticmethod
    def _chunked_result(ses_path: str, history: List[Dict[str, Any]], best_unrouted: Optional[int],
                        last: Optional[EngineExecutionResult], dur: float, cfg: Dict[str, Any],
                        outcomes: Optional[List[str]] = None, plans: Optional[List[Dict[str, Any]]] = None,
                        failure_category: Optional[str] = None, checkpoint: Optional[Dict[str, Any]] = None,
                        error: Optional[str] = None) -> EngineExecutionResult:
        """Assemble the aggregate result of a chunked run (pure; the SES has already been copied into place).

        `success` means a valid SES exists. It does NOT mean the board is routed: `final_unrouted` / `best_unrouted`
        carry the remaining connections and `status` is SUCCESS only at 0 unrouted."""
        ok = os.path.exists(ses_path) and os.path.getsize(ses_path) > 0
        status = ("SUCCESS" if ok and best_unrouted == 0 else
                  "PLATEAU_PARTIAL" if ok else
                  (last.status if last else "NO_RUN"))
        observed = (checkpoint or {}).get("observed_best_unrouted")
        hist_msg = "\n".join(f"chunk {h['chunk']}: {h['status']} [{h.get('outcome', '')}] {h['initial_unrouted']} -> {h['final_unrouted']} "
                              f"in {h['seconds']}s" for h in history)
        err = error
        if err is None and not ok:
            err = (last.error_message if last else "no chunk ran")
            if failure_category:
                err = f"[{failure_category}] {err}"
        return EngineExecutionResult(
            success=ok,
            status=status,
            engine_name="Freerouting",
            engine_version=last.engine_version if last else str((checkpoint or {}).get("engine_version") or ""),
            engine_path=last.engine_path if last else "",
            command=last.command if last else [],
            duration_sec=dur,
            returncode=last.returncode if last else 0,
            passes_completed=sum(h["passes"] for h in history),
            initial_unrouted=history[0]["initial_unrouted"] if history else None,
            final_unrouted=best_unrouted,
            ses_generated=ok,
            ses_path=ses_path if ok else None,
            ses_size_bytes=os.path.getsize(ses_path) if ok else 0,
            stdout_summary=hist_msg,
            stderr_summary=last.stderr_summary if last else "",
            error_message=None if ok and not failure_category else err,
            best_unrouted=best_unrouted if best_unrouted is not None else observed,
            best_pass=None,
            pass_history=[p for h in history for p in h["pass_history"]],
            restores_seen=sum(getattr(x, "restores_seen", 0) for x in [last] if x),
            engine_config={**cfg, "chunks": [{k: v for k, v in h.items() if k != "pass_history"} for h in history],
                           "chunk_outcomes": list(outcomes or []), "plans": list(plans or []),
                           "failure_category": failure_category, "observed_best_unrouted": observed,
                           "checkpoint": checkpoint or {}},
        )
