"""Provider registry: registration, credentials, base-URL overrides and model discovery.

Credentials come from the environment or the user config (desk.config: env > ~/.desk/config.json),
then the DESK credential vault (desk.py auth configure <provider>). They are resolved lazily on
every request, never stored on disk by this module, never placed in a URL and never logged.
The repo file desk.config.json refuses secrets (desk.config validation).

Endpoints come from catalog.PRESETS; an operator can override a base URL with
DESK_<PROVIDER>_BASE_URL or declare extra OpenAI-compatible / Anthropic / Gemini endpoints in
the DESK_MODEL_CATALOG_FILE "providers" section:

    {"providers": [{"name": "lab-vllm", "kind": "openai_compat",
                    "base_url": "http://127.0.0.1:8000/v1", "key_setting": null}]}

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

from desk import config as deskcfg
from desk.orchestrator.providers.base import ModelProvider, ModelRoute, ProviderError, Transport
from desk.orchestrator.providers.catalog import PRESETS, ModelCatalog, ModelDescriptor, ProviderPreset, canonical_provider


def credential(provider: str, key_setting: Optional[str]) -> Callable[[], Optional[str]]:
    """A lazy key source: config/env value of `key_setting`, else the vault entry for `provider`."""

    def _get() -> Optional[str]:
        if not key_setting:
            return None
        v = (deskcfg.get(key_setting) or "").strip()
        if v:
            return v
        try:
            from desk.auth.broker import get_credential_broker
            auth = get_credential_broker().get_auth_headers(provider).get("Authorization", "")
            return auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else None
        except Exception:
            return None

    return _get


def base_url_for(preset: ProviderPreset) -> str:
    return (deskcfg.get(f"DESK_{preset.name.upper()}_BASE_URL") or "").strip() or preset.base_url


def build_provider(preset: ProviderPreset, transport: Optional[Transport] = None,
                   api_key: Any = None) -> ModelProvider:
    base_url = base_url_for(preset)
    key = api_key if api_key is not None else credential(preset.name, preset.key_setting)
    if preset.kind == "openai_compat":
        from desk.orchestrator.providers.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(preset.name, base_url, api_key=key, key_setting=preset.key_setting,
                                    transport=transport, thinking_style=preset.thinking_style, local=preset.local)
    if preset.kind == "anthropic":
        from desk.orchestrator.providers.anthropic import AnthropicProvider
        return AnthropicProvider(preset.name, base_url, api_key=key, key_setting=preset.key_setting, transport=transport)
    if preset.kind == "gemini":
        from desk.orchestrator.providers.gemini import GeminiProvider
        return GeminiProvider(preset.name, base_url, api_key=key, key_setting=preset.key_setting, transport=transport)
    raise ProviderError(f"unknown provider kind '{preset.kind}' for '{preset.name}'", kind="config")


def _operator_presets() -> List[ProviderPreset]:
    path = (deskcfg.get("DESK_MODEL_CATALOG_FILE") or "").strip()
    if not path or not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for p in (data.get("providers") or []) if isinstance(data, dict) else []:
        if isinstance(p, dict) and p.get("name") and p.get("kind") and p.get("base_url"):
            out.append(ProviderPreset(name=canonical_provider(p["name"]), kind=p["kind"], base_url=p["base_url"],
                                      key_setting=p.get("key_setting"), thinking_style=p.get("thinking_style"),
                                      local=bool(p.get("local", p.get("key_setting") is None)),
                                      defaults=dict(p.get("defaults") or {})))
    return out


class ModelProviderRegistry:
    """Named providers built on first use. Tests pass `transport` (recorded fixtures) or
    `register()` a fake provider; nothing here touches the network until a call is made."""

    def __init__(self, transport: Optional[Transport] = None, catalog: Optional[ModelCatalog] = None,
                 presets: Optional[Dict[str, ProviderPreset]] = None, load_operator_file: bool = True):
        self.transport = transport
        self.catalog = catalog if catalog is not None else ModelCatalog(load_operator_file=load_operator_file)
        self.presets: Dict[str, ProviderPreset] = dict(presets if presets is not None else PRESETS)
        if load_operator_file:
            for p in _operator_presets():
                self.presets[p.name] = p
        self._built: Dict[str, ModelProvider] = {}

    # ---- registration ------------------------------------------------------------------------
    def register(self, provider: ModelProvider) -> None:
        """Register a ready provider instance (a fake in tests, or a custom adapter)."""
        self._built[provider.name] = provider

    def register_preset(self, preset: ProviderPreset) -> None:
        self.presets[preset.name] = preset
        self._built.pop(preset.name, None)

    def names(self) -> List[str]:
        return sorted(set(self.presets) | set(self._built))

    def has(self, name: str) -> bool:
        n = canonical_provider(name)
        return n in self.presets or n in self._built

    def get(self, name: str) -> ModelProvider:
        n = canonical_provider(name)
        if n not in self._built:
            if n not in self.presets:
                raise ProviderError(f"provider '{name}' is not registered (known: {', '.join(self.names())})", kind="config")
            self._built[n] = build_provider(self.presets[n], self.transport)
        return self._built[n]

    # ---- routes and capabilities -------------------------------------------------------------
    def parse_route(self, spec: str, default_provider: Optional[str] = None) -> ModelRoute:
        """"provider:model" -> ModelRoute. The prefix counts as a provider only when registered, so
        a bare local id such as "qwen3:8b" stays a model name for `default_provider`."""
        s = (spec or "").strip()
        if ":" in s:
            head, tail = s.split(":", 1)
            if self.has(head) and tail:
                return ModelRoute(canonical_provider(head), tail)
        if not default_provider:
            raise ProviderError(f"route '{spec}' names no registered provider; write it as provider:model", kind="config")
        return ModelRoute(canonical_provider(default_provider), s)

    def descriptor(self, route: ModelRoute) -> ModelDescriptor:
        return self.catalog.get(route.provider, route.model)

    # ---- status and discovery ----------------------------------------------------------------
    def status(self) -> List[Dict[str, Any]]:
        """Configuration state per provider. No network."""
        rows = []
        for n in self.names():
            preset = self.presets.get(n)
            try:
                ok, why = self.get(n).configured()
            except ProviderError as e:
                ok, why = False, str(e)
            rows.append({"provider": n, "kind": preset.kind if preset else "custom",
                         "base_url": base_url_for(preset) if preset else "",
                         "local": bool(preset and preset.local), "configured": ok, "detail": why})
        return rows

    def discover(self, names: Optional[List[str]] = None, timeout: float = 5.0,
                 include_local: bool = False) -> Dict[str, Dict[str, Any]]:
        """Model discovery: ask each configured provider which models it serves. One request per
        provider, sequential, each bounded by `timeout`. Local servers are probed only when named
        or when `include_local` is set."""
        out: Dict[str, Dict[str, Any]] = {}
        for n in names or self.names():
            preset = self.presets.get(canonical_provider(n))
            if preset and preset.local and not include_local and not names:
                out[n] = {"ok": False, "skipped": "local server; pass --local to probe", "models": []}
                continue
            try:
                p = self.get(n)
                ok, why = p.configured()
                if not ok:
                    out[n] = {"ok": False, "skipped": why, "models": []}
                    continue
                out[n] = {"ok": True, "models": p.list_models(timeout=timeout)}
            except ProviderError as e:
                out[n] = {"ok": False, "error": str(e), "kind": e.kind, "models": []}
        return out


_DEFAULT: Optional[ModelProviderRegistry] = None


def get_provider_registry() -> ModelProviderRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = ModelProviderRegistry()
    return _DEFAULT
