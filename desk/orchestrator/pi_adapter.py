"""Pi Agent CLI Adapter for DESK Multi-Model Orchestration.
Communicates with the installed pi / pi.cmd CLI via structured subprocess calls.

Executable resolution order: explicit argument, DESK_PI_PATH env var, PATH lookup.
Commands are always run as argument lists (never through a shell), so prompt
text that contains shell metacharacters cannot be interpreted by cmd.exe.

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
    if explicit:
        return explicit
    env = os.environ.get("DESK_PI_PATH", "").strip()
    if env:
        return env
    for cand in ("pi", "pi.cmd"):
        found = shutil.which(cand)
        if found:
            return found
    return "pi"


def _schema_instruction(schema: Dict[str, Any]) -> str:
    """Pi has no --json-schema flag, so the contract is stated in the system prompt."""
    return ("Respond with a single JSON object and nothing else: no prose, no markdown fences. "
            "The object must conform to this JSON schema:\n" + json.dumps(schema))


def _extract_json(text: str) -> Optional[Any]:
    """Parse model output as JSON, tolerating a fenced block or surrounding prose."""
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    if "```json" in text:
        sub = text.split("```json", 1)[1].split("```", 1)[0].strip()
        try:
            return json.loads(sub)
        except Exception:
            pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return None


class PiAdapter:

    def __init__(self, executable_path: Optional[str] = None):
        self.exe = _resolve_executable(executable_path)
        self._last_health_ts: float = 0.0

    def _available(self) -> bool:
        return bool(shutil.which(self.exe) or os.path.exists(self.exe))

    def check_health(self, timeout_sec: float = 5.0) -> ProviderHealth:
        """Verify pi CLI availability."""
        t0 = time.time()
        if not self._available():
            return ProviderHealth(
                provider_name="pi",
                available=False,
                cli_path=self.exe,
                last_checked=t0,
                status_message=f"Executable not found: {self.exe} (set DESK_PI_PATH or add pi to PATH)"
            )

        try:
            p = subprocess.run([self.exe, "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout_sec, shell=False)
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

    def build_command(self, task: TaskRequest) -> List[str]:
        cmd = [self.exe, "-p", task.prompt, "--mode", "json", "--no-session"]
        # Extensions are interactive-session features; in a non-interactive worker call they only
        # add startup latency and can abort the run when a user's extension config is broken.
        if os.environ.get("DESK_PI_EXTENSIONS", "").strip() != "1":
            cmd.append("-ne")
        if task.preferred_model:
            cmd.extend(["--model", task.preferred_model])
        if task.thinking_level:
            cmd.extend(["--thinking", task.thinking_level])
        system_parts = []
        if task.system_prompt:
            system_parts.append(task.system_prompt)
        if task.output_schema:
            system_parts.append(_schema_instruction(task.output_schema))
        if system_parts:
            cmd.extend(["--system-prompt", "\n\n".join(system_parts)])
        return cmd

    def execute(self, task: TaskRequest) -> TaskResult:
        """Execute a task request non-interactively using pi -p --mode json."""
        t0 = time.perf_counter()
        model = task.preferred_model or "default"
        timeout = task.timeout_sec or _FALLBACK_TIMEOUT
        cmd = self.build_command(task)

        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, shell=False)
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
            parsed_json = _extract_json(stdout_text)

            if task.output_schema and not isinstance(parsed_json, dict):
                return TaskResult(
                    task_id=task.task_id,
                    success=False,
                    provider="pi",
                    model=model,
                    output_text=stdout_text,
                    latency_ms=latency_ms,
                    execution_level=task.execution_level,
                    error="Schema requested but output contained no JSON object."
                )

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
                error=f"Task timed out after {timeout} seconds."
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
