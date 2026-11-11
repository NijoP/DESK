"""Model capability registry for DESK's L0-L4 router.

Routing by model *name* is fragile: a tier default may be a text-only model
while the task carries a board screenshot, or a reasoning model whose thinking
must be switched off for fast calls. This registry records what each model was
*verified* to support, so the router can choose by capability.

Entries marked VERIFIED were probed against the live provider API on the date
given, with the exact behaviour noted. UNVERIFIED entries are catalogue claims.

Zero external dependencies.
"""
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class ModelCapability:
    provider: str                 # DESK provider name: "pi" or "agy"
    model_id: str                 # exact id passed to the provider
    context_window: int = 128000
    vision: bool = False
    structured_output: bool = False   # JSON-object response mode honoured
    tool_calling: bool = False
    thinking_default_on: bool = False # emits reasoning unless explicitly disabled
    thinking_controllable: bool = False
    free_tier: bool = False
    verified_on: Optional[str] = None # ISO date of live probe; None = UNVERIFIED
    probe_latency_s: Optional[float] = None  # one-line JSON answer, thinking off
    notes: str = ""

    @property
    def status(self) -> str:
        return "VERIFIED" if self.verified_on else "UNVERIFIED"

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status
        return d


# Probed 2026-11-11 against https://integrate.api.nvidia.com/v1 (free NIM tier) and the
# local `pi` CLI with an `nvidia` provider in ~/.pi/agent/models.json.
_BUILTIN: List[ModelCapability] = [
    ModelCapability(
        provider="pi", model_id="nvidia/nemotron-3.5-lightning-30b-a3b", context_window=131072,
        vision=False, structured_output=True, tool_calling=True,
        thinking_default_on=True, thinking_controllable=True, free_tier=True,
        verified_on="2026-11-11", probe_latency_s=1.1,
        notes="With thinking on it spent the full 1500-token budget on reasoning (40-50 s, empty answer). "
              "With thinking off: ~1 s, valid JSON. Use for L1 only with thinking off.",
    ),
    ModelCapability(
        provider="pi", model_id="nvidia/nemotron-3.5-super-vl-120b-a12b", context_window=131072,
        vision=True, structured_output=True, tool_calling=True,
        thinking_default_on=True, thinking_controllable=True, free_tier=True,
        verified_on="2026-11-11", probe_latency_s=51.6,
        notes="Vision-language. Intermittent HTTP 503 'content safety screening is temporarily unavailable' "
              "on the free tier; 51.6 s for a one-line JSON answer with thinking off during the probe. "
              "Treat as L2 with a 90 s timeout and expect fallback to AGY.",
    ),
    ModelCapability(
        provider="pi", model_id="nvidia/nemotron-3-ultra-550b-a55b", context_window=131072,
        vision=False, structured_output=True, tool_calling=True,
        thinking_default_on=True, thinking_controllable=True, free_tier=True,
        verified_on="2026-11-11", probe_latency_s=0.7,
        notes="Fast with thinking off (0.7 s); 14.8 s with thinking on in JSON mode. Frontier tier.",
    ),
    ModelCapability(
        provider="agy", model_id="gemini-3.8-flash-low",
        vision=True, structured_output=True, tool_calling=True, free_tier=False,
        notes="Catalogue claim only; not probed by DESK.",
    ),
    ModelCapability(
        provider="agy", model_id="gemini-3.8-flash-high",
        vision=True, structured_output=True, tool_calling=True, free_tier=False,
        notes="Catalogue claim only; not probed by DESK.",
    ),
]


class CapabilityRegistry:
    def __init__(self, entries: Optional[List[ModelCapability]] = None):
        self._by_key: Dict[str, ModelCapability] = {}
        for e in entries if entries is not None else _BUILTIN:
            self.register(e)

    @staticmethod
    def _key(provider: str, model_id: str) -> str:
        return f"{provider}::{model_id}"

    def register(self, entry: ModelCapability) -> None:
        self._by_key[self._key(entry.provider, entry.model_id)] = entry

    def get(self, provider: str, model_id: Optional[str]) -> Optional[ModelCapability]:
        if not model_id:
            return None
        return self._by_key.get(self._key(provider, model_id))

    def models_for(self, provider: str) -> List[ModelCapability]:
        return [e for e in self._by_key.values() if e.provider == provider]

    def ensure_capability(self, provider: str, model_id: Optional[str], capability: str) -> Optional[str]:
        """Return `model_id` if it is known to have `capability`, else the first model of the
        same provider that does, else None (caller keeps its choice and the provider decides)."""
        entry = self.get(provider, model_id)
        if entry and getattr(entry, capability, False):
            return model_id
        for e in self.models_for(provider):
            if getattr(e, capability, False):
                return e.model_id
        return None

    def report(self) -> List[Dict]:
        return [e.to_dict() for e in self._by_key.values()]


_REGISTRY: Optional[CapabilityRegistry] = None


def get_registry() -> CapabilityRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CapabilityRegistry()
    return _REGISTRY
