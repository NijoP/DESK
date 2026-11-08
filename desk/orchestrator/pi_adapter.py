"""Pi Agent CLI Adapter for DESK Multi-Model Orchestration.
Communicates with the installed pi.cmd / pi CLI via structured subprocess calls.
Zero external dependencies.
"""
import os
import sys
import json
import time
import shutil
import subprocess
from typing import Optional, Dict, Any, List
from desk.orchestrator.protocol import TaskRequest, TaskResult, ProviderHealth

class PiAdapter:
    DEFAULT_CMD = r"C:\Users\HP\AppData\Roaming\npm\pi.cmd"

    def __init__(self, executable_path: Optional[str] = None):
        self.exe = executable_path or shutil.which("pi.cmd") or shutil.which("pi") or (self.DEFAULT_CMD if os.path.exists(self.DEFAULT_CMD) else "pi.cmd")
        self._last_health_ts: float = 0.0

    def check_health(self, timeout_sec: float = 5.0) -> ProviderHealth:
        """Verify pi CLI availability."""
        t0 = time.time()
        if not shutil.which(self.exe) and not os.path.exists(self.exe):
            return ProviderHealth(
                provider_name="pi",
                available=False,
                cli_path=self.exe,
                last_checked=t0,
                status_message=f"Executable not found: {self.exe}"
            )

        try:
            cmd = [self.exe, "--help"]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, shell=True)
            if p.returncode == 0:
                self._last_health_ts = t0
                return ProviderHealth(
                    provider_name="pi",
                    available=True,
                    cli_path=self.exe,
                    supported_models=["multi-provider"],
                    last_checked=t0,
                    status_message="Ready (Pi Agent available)"
                )
            else:
                return ProviderHealth(
                    provider_name="pi",
                    available=False,
                    cli_path=self.exe,
                    last_checked=t0,
                    status_message=f"CLI error (rc {p.returncode}): {p.stderr.strip()[:200]}"
                )
        except Exception as e:
            return ProviderHealth(
                provider_name="pi",
                available=False,
                cli_path=self.exe,
                last_checked=t0,
                status_message=f"Health check failed: {str(e)[:200]}"
            )

    def execute(self, task: TaskRequest) -> TaskResult:
        """Execute a task request non-interactively using pi --print --mode json."""
        t0 = time.perf_counter()
        model = task.preferred_model or "default"

        cmd = [self.exe, "-p", task.prompt, "--mode", "json"]
        if task.preferred_model:
            cmd.extend(["--model", task.preferred_model])
        if task.system_prompt:
            cmd.extend(["--system-prompt", task.system_prompt])

        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=task.timeout_sec, shell=True)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            if p.returncode != 0:
                return TaskResult(
                    task_id=task.task_id,
                    success=False,
                    provider="pi",
                    model=model,
                    output_text=p.stderr.strip() or p.stdout.strip(),
                    latency_ms=latency_ms,
                    execution_level=task.execution_level,
                    error=f"pi exited with code {p.returncode}: {p.stderr.strip()[:300]}"
                )

            stdout_text = p.stdout.strip()
            parsed_json = None
            try:
                parsed_json = json.loads(stdout_text)
            except Exception:
                if "```json" in stdout_text:
                    sub = stdout_text.split("```json", 1)[1].split("```", 1)[0].strip()
                    try:
                        parsed_json = json.loads(sub)
                    except Exception:
                        pass

            return TaskResult(
                task_id=task.task_id,
                success=True,
                provider="pi",
                model=model,
                output_text=stdout_text,
                output_json=parsed_json,
                latency_ms=latency_ms,
                execution_level=task.execution_level
            )
        except subprocess.TimeoutExpired:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider="pi",
                model=model,
                output_text="",
                latency_ms=latency_ms,
                execution_level=task.execution_level,
                error=f"Task timed out after {task.timeout_sec} seconds."
            )
        except Exception as e:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider="pi",
                model=model,
                output_text="",
                latency_ms=latency_ms,
                execution_level=task.execution_level,
                error=f"Pi execution error: {str(e)[:300]}"
            )
