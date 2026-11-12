"""DESK configuration: one schema, one precedence order, one place to read it.

Before this module existed, 24 environment variables configured routing, models, timeouts,
Java and HTTP, each read by the module that needed it, with no file, no schema and no way
to print the effective configuration. Now:

    precedence (highest first)
        1. environment variable            (unchanged behaviour: every old `export X=...` still wins)
        2. user file   ~/.desk/config.json  (or the file named by DESK_CONFIG_FILE)
        3. repo file   <repo>/desk.config.json
        4. built-in default from SCHEMA

    python desk.py config show            effective values, their source, secrets masked
    python desk.py config schema          every key with type, default and description
    python desk.py doctor                 validates the configuration as one of its checks

Files hold a flat JSON object keyed by the variable name, e.g. {"DESK_L1_TIMEOUT": 20}.
Secrets (API keys) are refused in the repo file: validation reports them as errors.
Environment variables are read live on every call, so a test or a shell that sets one
after import is honoured, exactly as before.

Zero external dependencies.
"""
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Pattern

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_FILE = os.path.join(_REPO_ROOT, "desk.config.json")
USER_FILE_DEFAULT = os.path.join(os.path.expanduser("~"), ".desk", "config.json")

STR, INT, FLOAT, BOOL, PATH, SECRET, ENUM = "str", "int", "float", "bool", "path", "secret", "enum"


@dataclass(frozen=True)
class Setting:
    key: str                      # exact variable name, or a regex when `pattern` is True
    type: str
    default: Optional[str]
    group: str
    description: str
    pattern: bool = False
    choices: Optional[tuple] = None

    def regex(self) -> Pattern[str]:
        return re.compile("^" + self.key + "$")


SCHEMA: List[Setting] = [
    # -- project / ECAD bridge ------------------------------------------------------------
    Setting("DESK_PROJECT", PATH, None, "project", "Project directory used when a CLI gets no explicit path."),
    Setting("EDA_PORT", INT, None, "bridge", "EasyEDA Pro API-gateway port; unset = probe 49620-49629."),
    Setting("EDA_WINDOW_ID", STR, None, "bridge", "EasyEDA window to target when project.json has none."),
    Setting("EASYEDA_API_REF", PATH, None, "bridge", "Alternative EasyEDA API reference file for tools/ctx.py api."),
    Setting("DESK_TELEMETRY", BOOL, "1", "project", "Append tool runs to .desk_learn/runs.jsonl (0 disables)."),
    Setting("DESK_MUTATION_POLICY", ENUM, "record", "safety",
            "record: journal whether a human approval accompanied each live mutation; "
            "require: refuse non-idempotent mutations without one.", choices=("record", "require")),
    # -- credentials ------------------------------------------------------------------------
    Setting("DESK_CREDENTIAL_STORE", ENUM, None, "credentials",
            "Force a vault backend instead of the platform default.", choices=("windows", "keychain", "file")),
    Setting("NVIDIA_API_KEY", SECRET, None, "credentials", "NVIDIA NIM key (or store it with desk.py auth configure)."),
    Setting("LCSC_CLIENT_ID", STR, None, "credentials", "LCSC API client id (live supplier calls)."),
    Setting("LCSC_CLIENT_SECRET", SECRET, None, "credentials", "LCSC API client secret."),
    Setting("DESK_MOCK_SUPPLIERS", BOOL, "0", "credentials", "1 = supplier providers answer from offline fixtures."),
    Setting("DESK_MOCK_MANUFACTURING", BOOL, "0", "credentials", "1 = JLCPCB client answers from offline fixtures."),
    # -- knowledge ---------------------------------------------------------------------------
    Setting("DESK_DOMAIN_LIBRARY", PATH, None, "knowledge", "Alternative library/pcb_domains root."),
    # -- routing engine ------------------------------------------------------------------------
    Setting("DESK_JAVA", PATH, None, "routing", "Java executable for Freerouting (else library/tools/jdk*/bin, else PATH)."),
    Setting("FREEROUTING_JAR", PATH, None, "routing", "Explicit Freerouting JAR."),
    Setting("FREEROUTING_BIN", PATH, None, "routing", "Explicit native Freerouting executable."),
    Setting("DESK_FR_STAGNATION_FLAG", BOOL, "0", "routing",
            "1 = pass --router.autorouter.stagnation_pass_limit (rejected by Freerouting 2.5.0)."),
    Setting("DESK_DOCTOR_CACHE_TTL_S", INT, "86400", "routing", "Seconds the doctor caches Java/Freerouting/Node probes."),
    # -- models -----------------------------------------------------------------------------
    Setting("DESK_AGENT_MODEL", STR, "nvidia/nemotron-3-ultra-550b-a55b", "models", "Model for desk.py agent."),
    Setting("DESK_HTTP_BASE_URL", STR, "https://integrate.api.nvidia.com/v1", "models", "OpenAI-compatible endpoint."),
    Setting("DESK_HTTP_API_KEY_ENV", STR, "NVIDIA_API_KEY", "models", "Name of the variable holding the endpoint key."),
    Setting("DESK_HTTP_MAX_TOKENS", INT, "2048", "models", "max_tokens per HTTP completion."),
    Setting("DESK_PI_PATH", PATH, None, "models", "Pi CLI executable (else PATH)."),
    Setting("DESK_PI_EXTENSIONS", BOOL, "0", "models", "1 = let Pi load its extensions (slower, more tokens)."),
    Setting("DESK_AGY_PATH", PATH, None, "models", "Gemini CLI executable (else PATH)."),
    Setting("DESK_PROVIDER_ORDER", STR, "agy,pi", "models", "Provider preference for L1/L2, comma separated."),
    Setting("DESK_L3_PROVIDERS", STR, "agy,pi", "models", "The two providers used for L3 dual review."),
    Setting("DESK_FRONTIER_PROVIDER", STR, None, "models", "Provider for L4 (default: first of DESK_PROVIDER_ORDER)."),
    Setting("DESK_FRONTIER_MODEL", STR, None, "models", "Model id for L4 on that provider."),
    Setting(r"DESK_L[1-4]_MODEL_(AGY|PI|NVIDIA)", STR, None, "models", "Model per tier and provider.", pattern=True),
    Setting(r"DESK_L[1-4]_TIMEOUT", FLOAT, None, "models", "Per-tier timeout in seconds (defaults 30/90/180/300).", pattern=True),
    Setting(r"DESK_L[1-4]_THINKING", ENUM, None, "models", "Per-tier thinking level.", pattern=True,
            choices=("off", "low", "medium", "high")),
    Setting("DESK_CONFIG_FILE", PATH, None, "project", "User config file (default ~/.desk/config.json)."),
]

_EXACT: Dict[str, Setting] = {s.key: s for s in SCHEMA if not s.pattern}
_PATTERNS: List[Setting] = [s for s in SCHEMA if s.pattern]


def setting_for(key: str) -> Optional[Setting]:
    s = _EXACT.get(key)
    if s:
        return s
    for p in _PATTERNS:
        if p.regex().match(key):
            return p
    return None


def _coerce(setting: Setting, raw: str) -> Any:
    t = setting.type
    if t == INT:
        return int(str(raw).strip())
    if t == FLOAT:
        return float(str(raw).strip())
    if t == BOOL:
        v = str(raw).strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off", ""):
            return False
        raise ValueError(f"not a boolean: {raw!r}")
    if t == ENUM and setting.choices and str(raw).strip().lower() not in setting.choices:
        raise ValueError(f"must be one of {', '.join(setting.choices)}")
    return str(raw)


class Config:
    def __init__(self, repo_file: Optional[str] = None, user_file: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None):
        self.repo_file = repo_file or REPO_FILE
        self._user_file = user_file
        self._env = env
        self._files: Dict[str, Dict[str, Any]] = {}
        self._mtimes: Dict[str, float] = {}

    # ---- sources ---------------------------------------------------------------------------
    @property
    def environ(self) -> Dict[str, str]:
        return self._env if self._env is not None else os.environ  # type: ignore[return-value]

    @property
    def user_file(self) -> str:
        return self._user_file or self.environ.get("DESK_CONFIG_FILE") or USER_FILE_DEFAULT

    def _file(self, path: str) -> Dict[str, Any]:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            self._files.pop(path, None)
            return {}
        if self._mtimes.get(path) != mtime:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._files[path] = data if isinstance(data, dict) else {"__error__": "top level must be an object"}
            except (OSError, ValueError) as e:
                self._files[path] = {"__error__": str(e)[:120]}
            self._mtimes[path] = mtime
        return self._files.get(path, {})

    def lookup(self, key: str):
        """Return (raw_value_as_str_or_None, source). Empty env strings count as unset (old behaviour)."""
        v = self.environ.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip(), "env"
        for src, path in (("user", self.user_file), ("repo", self.repo_file)):
            data = self._file(path)
            if key in data and data[key] is not None and str(data[key]).strip() != "":
                return str(data[key]).strip(), src
        s = setting_for(key)
        if s and s.default is not None:
            return s.default, "default"
        return None, "unset"

    # ---- typed getters ---------------------------------------------------------------------
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        v, _ = self.lookup(key)
        return v if v is not None else default

    def get_int(self, key: str, default: Optional[int] = None) -> Optional[int]:
        v = self.get(key)
        try:
            return int(v) if v is not None else default
        except ValueError:
            return default

    def get_float(self, key: str, default: Optional[float] = None) -> Optional[float]:
        v = self.get(key)
        try:
            return float(v) if v is not None else default
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key)
        if v is None:
            return default
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    def source(self, key: str) -> str:
        return self.lookup(key)[1]

    # ---- validation and display -------------------------------------------------------
    def validate(self) -> List[str]:
        problems: List[str] = []
        for src, path in (("user", self.user_file), ("repo", self.repo_file)):
            data = self._file(path)
            if "__error__" in data:
                problems.append(f"{src} file {path}: {data['__error__']}")
                continue
            for k, v in data.items():
                s = setting_for(k)
                if s is None:
                    problems.append(f"{src} file: unknown key {k}")
                    continue
                if s.type == SECRET and src == "repo":
                    problems.append(f"repo file: {k} is a secret; keep it in the environment or the vault")
                try:
                    _coerce(s, v)
                except (ValueError, TypeError) as e:
                    problems.append(f"{src} file: {k}={v!r} invalid ({e})")
        for k, v in self.environ.items():
            s = setting_for(k)
            if s is None or s.type in (STR, PATH, SECRET):
                continue
            try:
                _coerce(s, v)
            except (ValueError, TypeError) as e:
                problems.append(f"env: {k}={v!r} invalid ({e})")
        return problems

    def keys_in_effect(self) -> List[str]:
        keys = set(_EXACT)
        for data in (self._file(self.user_file), self._file(self.repo_file), dict(self.environ)):
            for k in data:
                if setting_for(k):
                    keys.add(k)
        return sorted(keys)

    def as_rows(self, mask_secrets: bool = True) -> List[Dict[str, Any]]:
        rows = []
        for k in self.keys_in_effect():
            s = setting_for(k)
            v, src = self.lookup(k)
            shown = v
            if v is not None and mask_secrets and s and s.type == SECRET:
                shown = "***" + v[-4:] if len(v) > 8 else "***"
            rows.append({"key": k, "value": shown, "source": src, "type": s.type if s else "?",
                         "group": s.group if s else "?", "description": s.description if s else ""})
        return rows

    def render(self, mask_secrets: bool = True) -> str:
        lines = [f"DESK configuration  (env > {self.user_file} > {self.repo_file} > default)", "=" * 96]
        group = None
        for r in self.as_rows(mask_secrets):
            if r["group"] != group:
                group = r["group"]
                lines.append(f"[{group}]")
            val = "" if r["value"] is None else str(r["value"])
            lines.append(f"  {r['key']:<32} {val:<42} {r['source']}")
        probs = self.validate()
        lines.append("=" * 96)
        lines.append("valid" if not probs else "problems:\n  " + "\n  ".join(probs))
        return "\n".join(lines)

    @staticmethod
    def schema_rows() -> List[Dict[str, Any]]:
        return [{"key": s.key, "type": s.type, "default": s.default, "group": s.group,
                 "description": s.description, "pattern": s.pattern,
                 "choices": list(s.choices) if s.choices else None} for s in SCHEMA]


_CONFIG: Optional[Config] = None


def get_config() -> Config:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = Config()
    return _CONFIG


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """Module-level shortcut: `from desk import config; config.get("DESK_JAVA")`."""
    return get_config().get(key, default)


def get_int(key: str, default: Optional[int] = None) -> Optional[int]:
    return get_config().get_int(key, default)


def get_float(key: str, default: Optional[float] = None) -> Optional[float]:
    return get_config().get_float(key, default)


def get_bool(key: str, default: bool = False) -> bool:
    return get_config().get_bool(key, default)
