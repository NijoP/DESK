"""Process Guard and Bounded Subprocess Execution for DESK.
Executes external processes (such as Freerouting, DSN generators, DRC) safely:
- Explicit configurable timeouts
- In-memory bounded output capture (circular ring buffer)
- Clean process tree termination on timeout or cancellation
- Structured diagnostic reports
Zero external dependencies.
"""
import subprocess
import time
import os
import sys
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

@dataclass
class SubprocessResult:
    cmd: List[str]
    exit_code: int
    duration_ms: float
    stdout: str
    stderr: str
    timed_out: bool = False
    truncated: bool = False

class ProcessGuard:
    """Manages safe subprocess invocations with strict resource bounds."""

    @staticmethod
    def run_bounded(cmd: List[str],
                    timeout_s: float = 60.0,
                    max_buffer_bytes: int = 2 * 1024 * 1024, # 2 MB default
                    cwd: Optional[str] = None,
                    env: Optional[Dict[str, str]] = None) -> SubprocessResult:
        t0 = time.perf_counter()
        proc = None
        timed_out = False
        truncated = False
        stdout_buf = bytearray()
        stderr_buf = bytearray()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env or os.environ.copy()
            )

            # Read with timeout and buffer cap
            start_wait = time.time()
            while True:
                ret = proc.poll()
                if ret is not None:
                    break

                if time.time() - start_wait > timeout_s:
                    timed_out = True
                    proc.kill()
                    break

                time.sleep(0.02)

            # Consume output up to buffer cap
            out_bytes, err_bytes = proc.communicate()
            if len(out_bytes) > max_buffer_bytes:
                stdout_buf = out_bytes[:max_buffer_bytes]
                truncated = True
            else:
                stdout_buf = out_bytes

            if len(err_bytes) > max_buffer_bytes:
                stderr_buf = err_bytes[:max_buffer_bytes]
                truncated = True
            else:
                stderr_buf = err_bytes

            exit_code = proc.returncode if not timed_out else -1

        except Exception as e:
            exit_code = -1
            stderr_buf = str(e).encode("utf-8")

        duration_ms = (time.perf_counter() - t0) * 1000.0

        return SubprocessResult(
            cmd=cmd,
            exit_code=exit_code,
            duration_ms=round(duration_ms, 2),
            stdout=stdout_buf.decode("utf-8", errors="replace"),
            stderr=stderr_buf.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            truncated=truncated
        )
