"""Direct OpenAI-compatible HTTP adapter for DESK's model router.

Why this exists: an L1 classification dispatched through a coding-agent CLI
(`agy`, `pi`) loads the agent's full system prompt and repository context. Measured
on 2026-11-11: 23,683 input tokens and 30 s wall time through `agy`, 4,423 tokens
through `pi -ne`, for a one-line question that needs about 150 tokens. This adapter
sends only the task's system prompt and prompt to a chat-completions endpoint over
stdlib `urllib`, with JSON-object response mode and per-request thinking control.

Default provider: NVIDIA NIM (https://integrate.api.nvidia.com/v1), key from
`NVIDIA_API_KEY` or the DESK credential vault service "nvidia". Any
OpenAI-compatible endpoint works via DESK_HTTP_BASE_URL / DESK_HTTP_API_KEY_ENV.

Zero external dependencies.
"""
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from desk.orchestrator.protocol import TaskRequest, TaskResult, ProviderHealth

_FALLBACK_TIMEOUT = 60.0


def _extract_json(text: str) -> Optional[Any]:
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


class OpenAICompatAdapter:
    """Minimal chat-completions client. Provider name defaults to "nvidia"."""

    def __init__(self, provider_name: str = "nvidia",
                 base_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 api_key_env: Optional[str] = None):
        self.name = provider_name
        self.base_url = (base_url or os.environ.get("DESK_HTTP_BASE_URL")
                         or "https://integrate.api.nvidia.com/v1").rstrip("/")
        self._api_key = api_key
        self._api_key_env = api_key_env or os.environ.get("DESK_HTTP_API_KEY_ENV") or "NVIDIA_API_KEY"
        self._models_cache: List[str] = []

    # ---- auth ------------------------------------------------------------------------------
    def _key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        v = os.environ.get(self._api_key_env, "").strip()
        if v:
            return v
        try:
            # Vault-backed fallback: service "<provider>" or env DESK_<PROVIDER>_API_KEY via the broker.
            from desk.auth.broker import get_credential_broker
            auth = get_credential_broker().get_auth_headers(self.name).get("Authorization", "")
            return auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else None
        except Exception:
            return None

    def _headers(self) -> Dict[str, str]:
        key = self._key()
        if not key:
            raise RuntimeError(f"No API key for provider '{self.name}': set {self._api_key_env}.")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                "Accept": "application/json"}

    # ---- health ----------------------------------------------------------------------------
    def check_health(self, timeout_sec: float = 8.0) -> ProviderHealth:
        t0 = time.time()
        if not self._key():
            return ProviderHealth(provider_name=self.name, available=False, cli_path=self.base_url,
                                  last_checked=t0,
                                  status_message=f"No API key: set {self._api_key_env} (value is never logged)")
        try:
            req = urllib.request.Request(self.base_url + "/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=timeout_sec) as r:
                data = json.loads(r.read().decode("utf-8"))
            ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
            self._models_cache = ids
            return ProviderHealth(provider_name=self.name, available=True, cli_path=self.base_url,
                                  supported_models=ids, last_checked=t0,
                                  status_message=f"Ready ({len(ids)} models listed)")
        except urllib.error.HTTPError as e:
            return ProviderHealth(provider_name=self.name, available=False, cli_path=self.base_url,
                                  last_checked=t0, status_message=f"HTTP {e.code} from /models")
        except Exception as e:
            return ProviderHealth(provider_name=self.name, available=False, cli_path=self.base_url,
                                  last_checked=t0, status_message=f"Health check failed: {str(e)[:160]}")

    # ---- execution -------------------------------------------------------------------------
    def build_body(self, task: TaskRequest) -> Dict[str, Any]:
        messages = []
        system = task.system_prompt or ""
        if task.output_schema:
            system = (system + "\n\n" if system else "") + (
                "Respond with a single JSON object and nothing else. It must conform to this JSON schema:\n"
                + json.dumps(task.output_schema))
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": task.prompt})

        body: Dict[str, Any] = {
            "model": task.preferred_model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": int(os.environ.get("DESK_HTTP_MAX_TOKENS", "2048")),
        }
        if task.output_schema:
            body["response_format"] = {"type": "json_object"}
        level = (task.thinking_level or "").lower()
        if level == "off":
            # Both forms verified on NVIDIA NIM for Nemotron 3.5 (2026-11-11); harmless elsewhere.
            body["chat_template_kwargs"] = {"enable_thinking": False}
            body["reasoning_effort"] = "none"
        elif level in ("low", "medium", "high"):
            body["reasoning_effort"] = level
        return body

    def execute(self, task: TaskRequest) -> TaskResult:
        t0 = time.perf_counter()
        model = task.preferred_model or "unset"
        timeout = task.timeout_sec or _FALLBACK_TIMEOUT

        def fail(msg: str) -> TaskResult:
            return TaskResult(task_id=task.task_id, success=False, provider=self.name, model=model,
                              output_text="", latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                              execution_level=task.execution_level, error=msg)

        if not task.preferred_model:
            return fail(f"No model configured for provider '{self.name}' at L{task.execution_level}; "
                        f"set DESK_L{task.execution_level}_MODEL_{self.name.upper()}.")
        try:
            body = self.build_body(task)
            req = urllib.request.Request(self.base_url + "/chat/completions",
                                         data=json.dumps(body).encode("utf-8"), headers=self._headers())
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:200]
            except Exception:
                pass
            return fail(f"HTTP {e.code}: {detail}")
        except Exception as e:
            if "timed out" in str(e).lower():
                return fail(f"Task timed out after {timeout} seconds.")
            return fail(f"{type(e).__name__}: {str(e)[:200]}")

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        try:
            choice = resp["choices"][0]
            msg = choice.get("message", {})
            content = (msg.get("content") or "").strip()
            finish = choice.get("finish_reason")
        except Exception:
            return fail("Malformed completion response.")

        usage = resp.get("usage") or {}
        parsed = _extract_json(content)
        if task.output_schema and not isinstance(parsed, dict):
            reason = "model returned no JSON object"
            if finish == "length":
                reason = "output truncated (finish_reason=length); the model likely spent the budget on reasoning"
            return TaskResult(task_id=task.task_id, success=False, provider=self.name, model=model,
                              output_text=content, latency_ms=latency_ms,
                              execution_level=task.execution_level,
                              error=f"Schema requested but {reason}.")

        return TaskResult(task_id=task.task_id, success=True, provider=self.name, model=model,
                          output_text=content, output_json=parsed if isinstance(parsed, dict) else None,
                          latency_ms=latency_ms, execution_level=task.execution_level,
                          error=None if content else "Empty content (finish_reason=%s)" % finish)
