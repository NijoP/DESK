"""Process Guard and Bounded Subprocess Execution for DESK.
Executes external processes (such as Freerouting, DSN generators, DRC) safely:
- Explicit configurable timeouts
- Continuous streaming drain to prevent pipe deadlocks
- Strictly bounded in-memory buffer (excess discarded without RAM bloat)
- Optional durable disk logging for complete audit logs
- Clean process tree termination on timeout or cancellation (Windows & Linux)
- Structured diagnostic reports
Zero external dependencies.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SubprocessResult:
    cmd: List[str]
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False
    cancelled: bool = False
    pid: int = 0


def kill_process_tree(pid: int) -> None:
    """Terminates an entire process tree across Windows and Linux."""
    if pid <= 0:
        return
    if os.name == "nt":
        try:
            # /F = Forcefully terminate, /T = Tree (child processes), /PID = Target PID
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            )
        except Exception:
            try:
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
                if handle:
                    ctypes.windll.kernel32.TerminateProcess(handle, 1)
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass
    else:
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass


class ProcessGuard:
    """Manages safe subprocess invocations with strict resource bounds."""

    @staticmethod
    def run_bounded(
        cmd: List[str],
        timeout_s: float = 60.0,
        max_buffer_bytes: int = 2 * 1024 * 1024,  # 2 MB default cap
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        log_file_path: Optional[str] = None,
        cancellation_event: Optional[threading.Event] = None,
    ) -> SubprocessResult:
        t0 = time.perf_counter()
        timed_out = False
        cancelled = False
        truncated = False
        stdout_buf = bytearray()
        stderr_buf = bytearray()
        buf_lock = threading.Lock()

        # Optional durable log file
        log_file = None
        if log_file_path:
            os.makedirs(os.path.dirname(os.path.abspath(log_file_path)), exist_ok=True)
            log_file = open(log_file_path, "wb")

        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": cwd,
            "env": env or os.environ.copy(),
        }
        if os.name != "nt":
            # Start new session on POSIX for clean process group kill
            popen_kwargs["start_new_session"] = True

        proc = None
        try:
            proc = subprocess.Popen(cmd, **popen_kwargs)
            pid = proc.pid

            def _drain_stream(stream, target_buf, is_stderr=False):
                nonlocal truncated
                try:
                    for chunk in iter(lambda: stream.read(4096), b""):
                        if not chunk:
                            break
                        if log_file:
                            try:
                                log_file.write(chunk)
                                log_file.flush()
                            except Exception:
                                pass
                        with buf_lock:
                            current_len = len(target_buf)
                            if current_len < max_buffer_bytes:
                                available = max_buffer_bytes - current_len
                                if len(chunk) <= available:
                                    target_buf.extend(chunk)
                                else:
                                    target_buf.extend(chunk[:available])
                                    truncated = True
                            else:
                                truncated = True
                finally:
                    stream.close()

            t_stdout = threading.Thread(target=_drain_stream, args=(proc.stdout, stdout_buf), daemon=True)
            t_stderr = threading.Thread(target=_drain_stream, args=(proc.stderr, stderr_buf, True), daemon=True)
            t_stdout.start()
            t_stderr.start()

            # Poll loop with timeout and cancellation check
            deadline = time.time() + timeout_s
            while True:
                ret = proc.poll()
                if ret is not None:
                    break

                if cancellation_event and cancellation_event.is_set():
                    cancelled = True
                    kill_process_tree(pid)
                    break

                if time.time() > deadline:
                    timed_out = True
                    kill_process_tree(pid)
                    break

                time.sleep(0.01)

            # Wait for drain threads to finish up to 1 second
            t_stdout.join(timeout=1.0)
            t_stderr.join(timeout=1.0)

            # Re-poll returncode
            exit_code = proc.poll()
            if exit_code is None:
                proc.kill()
                exit_code = -1
            if timed_out or cancelled:
                exit_code = -1

        except Exception as e:
            exit_code = -1
            pid = proc.pid if proc else 0
            with buf_lock:
                stderr_buf.extend(str(e).encode("utf-8"))
        finally:
            if log_file:
                try:
                    log_file.close()
                except Exception:
                    pass

        duration_ms = (time.perf_counter() - t0) * 1000.0

        return SubprocessResult(
            cmd=cmd,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 2),
            stdout=stdout_buf.decode("utf-8", errors="replace"),
            stderr=stderr_buf.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            truncated=truncated,
            cancelled=cancelled,
            pid=pid,
        )
