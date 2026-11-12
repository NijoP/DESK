"""AGY CLI (Google/Gemini) Adapter for DESK Multi-Model Orchestration.
Communicates with the installed agy.exe CLI via structured subprocess calls.
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

_FALLBACK_TIMEOUT = 60.0


def _resolve_executable(explicit: Optional[str]) -> str:
    """Resolution order: explicit argument, DESK_AGY_PATH env var, PATH lookup."""
    if explicit:
        return explicit
    from desk import config as deskcfg
    env = (deskcfg.get("DESK_AGY_PATH") or "").strip()
    if env:
        return env
    return shutil.which("agy") or "agy"


class AGYAdapter:

    def __init__(self, executable_path: Optional[str] = None):
        self.exe = _resolve_executable(executable_path)
        self._cached_models: List[str] = []
        self._last_health_ts: float = 0.0

    def check_health(self, timeout_sec: float = 5.0) -> ProviderHealth:
        """Verify agy executable availability and list available models."""
        t0 = time.time()
        if not shutil.which(self.exe) and not os.path.exists(self.exe):
            return ProviderHealth(
                provider_name="agy",
                available=False,
                cli_path=self.exe,
                last_checked=t0,
                status_message=f"Executable not found: {self.exe} (set DESK_AGY_PATH or add agy to PATH)"
            )

        try:
            cmd = [self.exe, "models"]
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_sec, shell=False)
            if p.returncode == 0:
                models = []
                for line in p.stdout.splitlines():
                    parts = line.strip().split("\t")
                    if parts and parts[0] and not parts[0].startswith("Fetching"):
                        models.append(parts[0])
                self._cached_models = models
                self._last_health_ts = t0
                return ProviderHealth(
                    provider_name="agy",
                    available=True,
                    cli_path=self.exe,
                    supported_models=models,
                    last_checked=t0,
                    status_message=f"Ready ({len(models)} models available)"
                )
            else:
                return ProviderHealth(
                    provider_name="agy",
                    available=False,
                    cli_path=self.exe,
                    last_checked=t0,
                    status_message=f"CLI error (rc {p.returncode}): {p.stderr.strip()[:200]}"
                )
        except Exception as e:
            return ProviderHealth(
                provider_name="agy",
                available=False,
                cli_path=self.exe,
                last_checked=t0,
                status_message=f"Health check failed: {str(e)[:200]}"
            )

    def execute(self, task: TaskRequest) -> TaskResult:
        """Execute a task request non-interactively using agy.exe --print."""
        t0 = time.perf_counter()
        model = task.preferred_model or ("gemini-3.8-flash-high" if task.execution_level >= 2 else "gemini-3.8-flash-low")
        timeout = task.timeout_sec or _FALLBACK_TIMEOUT

        cmd = [self.exe, "--print", task.prompt, "--model", model, "--output-format", "json"]

        if task.output_schema:
            try:
                cmd.extend(["--json-schema", json.dumps(task.output_schema)])
            except Exception:
                pass

        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            if p.returncode != 0:
                return TaskResult(
                    task_id=task.task_id,
                    success=False,
                    provider="agy",
                    model=model,
                    output_text=p.stderr.strip() or p.stdout.strip(),
                    latency_ms=latency_ms,
                    execution_level=task.execution_level,
                    error=f"agy exited with code {p.returncode}: {p.stderr.strip()[:300]}"
                )

            stdout_text = p.stdout.strip()
            parsed_json = None
            try:
                parsed_json = json.loads(stdout_text)
            except Exception:
                # Attempt to extract JSON markdown block if wrapped
                if "```json" in stdout_text:
                    sub = stdout_text.split("```json", 1)[1].split("```", 1)[0].strip()
                    try:
                        parsed_json = json.loads(sub)
                    except Exception:
                        pass

            return TaskResult(
                task_id=task.task_id,
                success=True,
                provider="agy",
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
                provider="agy",
                model=model,
                output_text="",
                latency_ms=latency_ms,
                execution_level=task.execution_level,
                error=f"Task timed out after {timeout} seconds."
            )
        except Exception as e:
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return TaskResult(
                task_id=task.task_id,
                success=False,
                provider="agy",
                model=model,
                output_text="",
                latency_ms=latency_ms,
                execution_level=task.execution_level,
                error=f"AGY execution error: {str(e)[:300]}"
            )
