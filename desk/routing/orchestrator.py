"""Subsystem Six: Mature Routing Engine Orchestrator and Process Supervisor.
Handles binary discovery, Java runtime compatibility probing, version detection,
headless execution enforcement, canonical pass configuration, real-time logging,
watchdog-driven stagnation detection, and execution timeout control.
Zero external dependencies.
"""
from __future__ import annotations
import os
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

        # 3. Check candidate JARs in tools_dir
        if not shutil.which("java"):
            raise RuntimeError("Java executable ('java') not found on system PATH. Install Java JRE/JDK 17+.")

        for jar_name in self.CANDIDATE_JARS:
            jar_path = os.path.join(self.tools_dir, jar_name)
            if os.path.exists(jar_path):
                compat, ver = self._probe_jar_compatibility(jar_path)
                if compat:
                    return ("JAR", jar_path, ver)

        raise RuntimeError(
            f"No compatible Freerouting engine found in '{self.tools_dir}'. "
            "Installed JARs may require a newer Java runtime, or no Java JRE is installed."
        )

    def _probe_jar_compatibility(self, jar_path: str) -> Tuple[bool, str]:
        """Tests whether a JAR can be loaded by the installed Java VM without class version errors."""
        try:
            cmd = ["java", "-jar", jar_path, "--help"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
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
    def ensure_headless_config(working_dir: str, job_timeout_str: str = "00:05:00") -> str:
        """Writes a strict headless freerouting.json configuration into working_dir.
        Fixes BN-004 (modal GUI hang) and BN-007 (pass 999 termination loop).
        """
        cfg_path = os.path.join(working_dir, "freerouting.json")
        cfg = {
            "gui": {
                "enabled": False,
                "currentLocale": "en"
            },
            "router": {
                "job_timeout": job_timeout_str,
                "autorouter": {
                    "max_passes": 30
                }
            }
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return cfg_path

    def execute_routing(
        self,
        dsn_path: str,
        ses_path: str,
        max_passes: int = 30,
        timeout_sec: float = 300.0,
        working_dir: Optional[str] = None,
        explicit_engine: Optional[str] = None,
        stagnation_patience: int = 6,
        log_callback: Optional[Any] = None
    ) -> EngineExecutionResult:
        """Executes the routing engine with full process supervision, streaming logs,
        watchdog stagnation detection, and bounded timeout.
        """
        if not os.path.exists(dsn_path):
            raise FileNotFoundError(f"Input DSN file not found: {dsn_path}")

        wd = working_dir or os.path.dirname(os.path.abspath(ses_path))
        os.makedirs(wd, exist_ok=True)

        engine_type, engine_path, engine_ver = self.discover_engine(explicit_engine)

        # 1. Prepare headless configuration in working directory
        mins = max(1, int(timeout_sec // 60))
        secs = int(timeout_sec % 60)
        timeout_str = f"00:{mins:02d}:{secs:02d}"
        self.ensure_headless_config(wd, job_timeout_str=timeout_str)

        # 2. Build canonical command line
        cmd: List[str] = []
        if engine_type == "JAR":
            cmd = ["java", "-jar", engine_path]
        else:
            cmd = [engine_path]

        # Use canonical CLI arguments
        cmd.extend([
            "-de", os.path.abspath(dsn_path),
            "-do", os.path.abspath(ses_path),
            "-mp", str(max_passes),
            "-mt", "1",
            "--gui.enabled=false"
        ])

        # If newer release supports canonical nested argument
        if "v2.5" in engine_ver or "v2.4" in engine_ver:
            cmd.append(f"--router.autorouter.max_passes={max_passes}")

        t0 = time.time()
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []

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

        passes_completed = 0
        unrouted_history: List[int] = []
        initial_unrouted: Optional[int] = None
        final_unrouted: Optional[int] = None
        stagnated = False

        def read_stdout():
            nonlocal passes_completed, initial_unrouted, final_unrouted, stagnated
            for line in proc.stdout:
                clean_line = line.strip()
                if clean_line:
                    stdout_lines.append(clean_line)
                    if log_callback:
                        log_callback(clean_line)

                    # Parse pass metrics from standard Freerouting logs:
                    # e.g., "Pass 1: unrouted connections: 14"
                    # or "Pass 2 completed with 8 unrouted"
                    low = clean_line.lower()
                    if "pass " in low and ("unrouted" in low or "connections" in low or "completed" in low):
                        passes_completed += 1
                        import re
                        m = re.search(r"(\d+)\s+unrouted", low)
                        if m:
                            count = int(m.group(1))
                            if initial_unrouted is None:
                                initial_unrouted = count
                            final_unrouted = count
                            unrouted_history.append(count)

                            # Watchdog stagnation detection
                            if len(unrouted_history) >= stagnation_patience:
                                last_k = unrouted_history[-stagnation_patience:]
                                if len(set(last_k)) == 1:
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

            if elapsed > timeout_sec:
                timed_out = True
                proc.kill()
                break

            if stagnated and passes_completed >= 5:
                # Terminate cleanly on plateau
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break

            time.sleep(0.2)

        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        dur = round(time.time() - t0, 2)

        ses_exists = os.path.exists(ses_path)
        ses_size = os.path.getsize(ses_path) if ses_exists else 0

        # Determine status
        if timed_out:
            status = "TIMEOUT"
            err_msg = f"Routing engine exceeded timeout budget of {timeout_sec:.1f}s"
            success = False
        elif stagnated:
            status = "STAGNATED"
            err_msg = f"Unrouted score stalled at {final_unrouted} for {stagnation_patience} consecutive passes"
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
            error_message=err_msg
        )
