"""Subsystem Six: Mature Routing Engine Orchestrator and Process Supervisor.
Handles binary discovery, Java runtime compatibility probing, version detection,
headless execution enforcement, canonical pass configuration, real-time logging,
watchdog-driven stagnation detection, and execution timeout control.
Zero external dependencies.
"""
from __future__ import annotations
import os
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
    PASS_RX = re.compile(r"pass\s*#?(\d+).*?completed in\s*([0-9.]+)\s*seconds(?:.*?score of\s*([0-9.]+))?.*?\((\d+)\s+unrouted\)", re.I)
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
                   "score": float(m.group(3)) if m.group(3) else None, "unrouted": int(m.group(4))}
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
    env = os.environ.get("DESK_JAVA", "").strip()
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
        target = explicit_path or os.environ.get("FREEROUTING_BIN") or os.environ.get("FREEROUTING_JAR")
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
        for jar_name in self.CANDIDATE_JARS:
            jar_path = os.path.join(self.tools_dir, jar_name)
            if not os.path.exists(jar_path):
                continue
            compat, ver = self._probe_jar_compatibility(jar_path)
            if compat:
                found.append((self._version_tuple(ver), jar_path, ver))
            else:
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
        ver_t = self._version_tuple(engine_ver)

        # 1. Prepare headless configuration (per-run file for v2.2+, global file for v2.1)
        mins = max(1, int(timeout_sec // 60))
        secs = int(timeout_sec % 60)
        timeout_str = f"00:{mins:02d}:{secs:02d}"
        settings = dict(stagnation_pass_limit=stagnation_patience, priority_net_classes=priority_net_classes,
                        plane_nets=plane_nets, via_costs=via_costs, max_threads=max_threads)
        cfg = self.build_config(timeout_str, max_passes=max_passes, **settings)
        self.ensure_headless_config(wd, job_timeout_str=timeout_str, max_passes=max_passes, **settings)
        global_backup = self.install_global_config(cfg) if ver_t < (2, 2) else None

        # 2. Build canonical command line
        cmd: List[str] = []
        if engine_type == "JAR":
            cmd = [self.java, "-jar", engine_path]
        else:
            cmd = [engine_path]

        design_arg = os.path.abspath(dsn_path)
        if input_ses and os.path.exists(input_ses):
            design_arg += "+" + os.path.abspath(input_ses)
        cmd.extend([
            "-de", design_arg,
            "-do", os.path.abspath(ses_path),
            "-mp", str(max_passes),
            "-mt", str(max_threads),
            "--gui.enabled=false"
        ])
        if ver_t >= (2, 2):
            cmd.append(f"--router.autorouter.max_passes={max_passes}")
            cmd.append(f"--router.autorouter.stagnation_pass_limit={int(stagnation_patience)}")
            cmd.append(f"--router.job_timeout={timeout_str}")
            if priority_net_classes:
                cmd.append("--router.autorouter.priority_net_classes=" + ",".join(priority_net_classes))
            if plane_nets:
                cmd.append("--router.plane_nets=" + ",".join(plane_nets))
            if via_costs is not None:
                cmd.append(f"--router.via_costs={int(via_costs)}")

        t0 = time.time()
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        tracker = PassTracker(patience=stagnation_patience)
        pin_map = DSNPinMap.from_file(dsn_path)
        progress_path = os.path.join(wd, "progress.json")
        problem_nets: Dict[str, int] = {}

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
        publish("starting")

        # 3. Supervised execution with background reader threads
        proc = subprocess.Popen(
            cmd,
            cwd=wd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        stagnated = False

        def read_stdout():
            nonlocal stagnated
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
                            stagnated = True

        def read_stderr():
            for line in proc.stderr:
                clean_line = line.strip()
                if clean_line:
                    stderr_lines.append(clean_line)

        t_out = threading.Thread(target=read_stdout, daemon=True)
        t_err = threading.Thread(target=read_stderr, daemon=True)
        t_out.start()
        t_err.start()

        # 4. Supervised loop: check process termination, timeout, or stagnation
        timed_out = False
        while proc.poll() is None:
            now = time.time()
            elapsed = now - t0

            # Freerouting's own job_timeout equals timeout_sec; give it a grace period to exit by itself and write
            # the SES (-do) with its best board instead of killing it at the same instant and losing the result.
            if elapsed > timeout_sec + 120.0:
                timed_out = True
                self._graceful_stop(proc)
                break

            if stagnated and tracker.passes >= 5:
                # Terminate cleanly on plateau. For v2.1 the SES is only written at job end, so
                # terminate() (not kill) gives the JVM its shutdown hook; v2.2+ stops itself via
                # stagnation_pass_limit before we get here.
                self._graceful_stop(proc)
                break

            time.sleep(0.2)

        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        dur = round(time.time() - t0, 2)
        self.restore_global_config(global_backup)
        ses_exists = os.path.exists(ses_path)
        publish("finished" if ses_exists else ("timeout" if timed_out else "stopped"))

        ses_size = os.path.getsize(ses_path) if ses_exists else 0
        passes_completed = tracker.passes
        initial_unrouted = tracker.initial_unrouted
        final_unrouted = tracker.last_unrouted

        # Determine status
        if timed_out:
            status = "TIMEOUT"
            err_msg = f"Routing engine exceeded timeout budget of {timeout_sec:.1f}s"
            success = False
        elif ses_exists and ses_size > 0 and proc.returncode != 0 and (final_unrouted or 0) > 0:
            status = "TIMEOUT_PARTIAL"
            err_msg = f"Engine stopped at its job_timeout with {final_unrouted} unrouted; partial SES kept"
            success = True
        elif stagnated:
            status = "STAGNATED"
            err_msg = (f"No new best unrouted count for {stagnation_patience} passes "
                       f"(best {tracker.best_unrouted} at pass {tracker.best_pass}, last {final_unrouted})")
            # If SES exists and has routed content, it is a partial success
            success = ses_exists and ses_size > 0
        elif proc.returncode != 0:
            status = "CRASHED"
            err_msg = f"Engine process exited with non-zero code {proc.returncode}"
            success = False
        elif not ses_exists or ses_size == 0:
            status = "NO_SES"
            err_msg = "Engine finished but did not generate a valid non-empty SES file"
            success = False
        else:
            status = "SUCCESS"
            err_msg = None
            success = True

        # Write log file to working dir
        log_path = os.path.join(wd, "freerouting.log")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(stdout_lines + stderr_lines))
        except Exception:
            pass

        return EngineExecutionResult(
            success=success,
            status=status,
            engine_name="Freerouting",
            engine_version=engine_ver,
            engine_path=engine_path,
            command=cmd,
            duration_sec=dur,
            returncode=proc.returncode or 0,
            passes_completed=passes_completed,
            initial_unrouted=initial_unrouted,
            final_unrouted=final_unrouted,
            ses_generated=ses_exists,
            ses_path=ses_path if ses_exists else None,
            ses_size_bytes=ses_size,
            stdout_summary="\n".join(stdout_lines[:50]),
            stderr_summary="\n".join(stderr_lines[:50]),
            error_message=err_msg,
            best_unrouted=tracker.best_unrouted,
            best_pass=tracker.best_pass,
            pass_history=list(tracker.history),
            restores_seen=tracker.restores,
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
