"""Provider presets and model capability descriptors, as data.

Do not assume every model supports the same capabilities. Each model is described by a
`ModelDescriptor`; the router reads it to decide whether to send native tools, ask for JSON
mode, stream, or wrap the call in the prompt-based tool adapter, and whether a conversation
fits the context window.

Where a descriptor comes from (`source`):
  verified  probed by DESK against the live API (copied from desk/orchestrator/capabilities.py)
  operator  supplied by the operator in the catalog file (DESK_MODEL_CATALOG_FILE)
  assumed   no entry: a conservative default for the provider kind; never reported as verified

Prices are never invented: `input_per_mtok` / `output_per_mtok` are None (cost unknown) unless
the operator records them, and 0.0 only for local servers, which are free to call.

Operator catalog file (JSON):
    {"models": [{"provider": "ollama", "model": "example-model:8b", "context_window": 8192,
                 "native_tools": false, "input_per_mtok": 0.0, "output_per_mtok": 0.0}]}

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from desk import config as deskcfg


@dataclass
class ModelDescriptor:
    provider: str
    model: str
    context_window: int = 8192
    max_output_tokens: int = 2048
    native_tools: bool = False
    structured_output: bool = False          # provider JSON mode honoured
    streaming: bool = False
    vision: bool = False
    thinking_controllable: bool = False
    input_per_mtok: Optional[float] = None   # USD per million input tokens; None = unknown
    output_per_mtok: Optional[float] = None
    source: str = "assumed"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderPreset:
    """How to reach one provider. `key_setting` names the config/env key holding the secret;
    None means no credential (local servers)."""
    name: str
    kind: str                                   # openai_compat | anthropic | gemini
    base_url: str
    key_setting: Optional[str]
    thinking_style: Optional[str] = None        # openai_compat only: "nim" (chat_template_kwargs) or None
    local: bool = False
    defaults: Dict[str, Any] = field(default_factory=dict)  # descriptor defaults for unknown models

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Remote OpenAI-compatible endpoints assume native tools + JSON mode for unknown models; local
# servers assume neither (many local models do not emit tool calls), so the prompt-based tool
# adapter is used until the operator records otherwise in the catalog file.
_REMOTE_OAI = {"context_window": 32768, "native_tools": True, "structured_output": True, "streaming": True}
_LOCAL_OAI = {"context_window": 8192, "native_tools": False, "structured_output": False, "streaming": True,
              "input_per_mtok": 0.0, "output_per_mtok": 0.0}

PRESETS: Dict[str, ProviderPreset] = {p.name: p for p in [
    ProviderPreset("nvidia", "openai_compat", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY",
                   thinking_style="nim", defaults=dict(_REMOTE_OAI)),
    ProviderPreset("openai", "openai_compat", "https://api.openai.com/v1", "OPENAI_API_KEY", defaults=dict(_REMOTE_OAI)),
    ProviderPreset("xai", "openai_compat", "https://api.x.ai/v1", "XAI_API_KEY", defaults=dict(_REMOTE_OAI)),
    ProviderPreset("ollama", "openai_compat", "http://127.0.0.1:11434/v1", None, local=True, defaults=dict(_LOCAL_OAI)),
    ProviderPreset("llamacpp", "openai_compat", "http://127.0.0.1:8080/v1", None, local=True, defaults=dict(_LOCAL_OAI)),
    ProviderPreset("vllm", "openai_compat", "http://127.0.0.1:8000/v1", None, local=True, defaults=dict(_LOCAL_OAI)),
    ProviderPreset("anthropic", "anthropic", "https://api.anthropic.com/v1", "ANTHROPIC_API_KEY",
                   defaults={"context_window": 200000, "native_tools": True, "structured_output": False, "streaming": True}),
    ProviderPreset("gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta", "GEMINI_API_KEY",
                   defaults={"context_window": 1000000, "native_tools": True, "structured_output": True, "streaming": True}),
]}

# Aliases accepted in "provider:model" route strings.
ALIASES = {"grok": "xai", "nim": "nvidia", "google": "gemini", "claude": "anthropic", "llama.cpp": "llamacpp"}


def canonical_provider(name: str) -> str:
    n = (name or "").strip().lower()
    return ALIASES.get(n, n)


def _verified_nim() -> List[ModelDescriptor]:
    """NIM models DESK probed (capabilities.py, 2026-11-11/12). Free tier: price left unknown."""
    from desk.orchestrator.capabilities import CapabilityRegistry
    out = []
    for c in CapabilityRegistry().models_for("pi"):
        if not c.model_id.startswith("nvidia/") or not c.verified_on:
            continue
        out.append(ModelDescriptor(provider="nvidia", model=c.model_id, context_window=c.context_window,
                                   native_tools=c.tool_calling, structured_output=c.structured_output,
                                   streaming=True, vision=c.vision, thinking_controllable=c.thinking_controllable,
                                   source="verified", notes=f"probed {c.verified_on}"))
    return out


def _load_operator_file() -> List[Dict[str, Any]]:
    path = (deskcfg.get("DESK_MODEL_CATALOG_FILE") or "").strip()
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("models", []) if isinstance(data, dict) else data
    return [r for r in rows if isinstance(r, dict) and r.get("provider") and r.get("model")]


class ModelCatalog:
    """Descriptors keyed by (provider, model). Unknown models get the preset's assumed defaults."""

    def __init__(self, entries: Optional[List[ModelDescriptor]] = None, load_operator_file: bool = True):
        self._by_key: Dict[str, ModelDescriptor] = {}
        for e in (entries if entries is not None else _verified_nim()):
            self.add(e)
        if load_operator_file:
            known = set(ModelDescriptor.__dataclass_fields__)
            for row in _load_operator_file():
                d = {k: v for k, v in row.items() if k in known}
                d["provider"] = canonical_provider(d["provider"])
                d.setdefault("source", "operator")
                base = self.get(d["provider"], d["model"]).to_dict()
                base.update(d)
                self.add(ModelDescriptor(**base))

    @staticmethod
    def _key(provider: str, model: str) -> str:
        return f"{provider}::{model}"

    def add(self, d: ModelDescriptor) -> None:
        self._by_key[self._key(d.provider, d.model)] = d

    def known(self, provider: str, model: str) -> bool:
        return self._key(provider, model) in self._by_key

    def get(self, provider: str, model: str) -> ModelDescriptor:
        hit = self._by_key.get(self._key(provider, model))
        if hit:
            return hit
        preset = PRESETS.get(provider)
        defaults = dict(preset.defaults) if preset else {}
        return ModelDescriptor(provider=provider, model=model, source="assumed",
                               notes="no catalog entry; provider-kind default", **defaults)

    def entries(self) -> List[ModelDescriptor]:
        return list(self._by_key.values())


def cost_usd(desc: ModelDescriptor, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Cost of one call, or None when the price of either side is unknown."""
    if desc.input_per_mtok is None or desc.output_per_mtok is None:
        return None
    return round(input_tokens * desc.input_per_mtok / 1e6 + output_tokens * desc.output_per_mtok / 1e6, 6)
