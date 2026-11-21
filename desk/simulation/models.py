"""Component model store: SPICE model cards with their provenance.

Store file (JSON):
    {"version": 1,
     "models": {"DSCH": {"kind": "D", "mpn": "EXAMPLE-SCHOTTKY",
                         "card": ".model DSCH D(IS=1e-6 N=1.05 RS=0.02)",
                         "source": {"type": "datasheet", "reference": "<datasheet title> rev <x> p.<n>"}}}}

Provenance status:
    TRACEABLE   source.type is "datasheet" or "vendor_model" and source.reference names the document.
                The card's origin is recorded. DESK has NOT checked the card against the datasheet curves.
    UNVERIFIED  anything else: generic or hand-tuned cards, inline cards from a sim spec, or a missing reference.

Cards are checked for shape only. A card must be one `.model` line or one `.subckt ... .ends` block named
like its key. Control statements, includes and shell commands are refused, so a stored card cannot run
commands when the engine loads it.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

from desk.errors import UsageError

TRACEABLE, UNVERIFIED = "TRACEABLE", "UNVERIFIED"
TRACEABLE_SOURCES = ("datasheet", "vendor_model")
KINDS = ("D", "NPN", "PNP", "NMOS", "PMOS", "SW", "SUBCKT")

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_STORE = os.path.join(_REPO, "library", "sim_models.json")

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_FORBIDDEN = re.compile(r"^\s*(\.control|\.endc|\.include|\.inc|\.lib|\.exec|\.end\b|shell\b|source\b)", re.I | re.M)


class ModelError(UsageError):
    """A model card or store entry is malformed or unsafe."""


def validate_card(name: str, kind: str, card: str) -> None:
    if not _NAME.match(name or ""):
        raise ModelError(f"model name '{name}' must be a letter followed by letters, digits or _ (max 64)")
    if kind not in KINDS:
        raise ModelError(f"model {name}: kind '{kind}' not one of {', '.join(KINDS)}")
    text = (card or "").strip()
    if not text:
        raise ModelError(f"model {name}: empty card")
    if _FORBIDDEN.search(text):
        raise ModelError(f"model {name}: card contains a control/include/shell statement; only .model/.subckt allowed")
    first = text.splitlines()[0].split()
    if kind == "SUBCKT":
        if len(first) < 2 or first[0].lower() != ".subckt" or first[1].lower() != name.lower():
            raise ModelError(f"model {name}: SUBCKT card must start with '.subckt {name} ...'")
        if not re.search(r"^\s*\.ends\b", text, re.I | re.M):
            raise ModelError(f"model {name}: SUBCKT card has no .ends")
    else:
        if any(not ln.strip().startswith("+") for ln in text.splitlines()[1:] if ln.strip()):
            raise ModelError(f"model {name}: a .model card is one statement (continuation lines start with '+')")
        if len(first) < 2 or first[0].lower() != ".model" or first[1].lower() != name.lower():
            raise ModelError(f"model {name}: card must start with '.model {name} ...'")


def provenance(entry: Dict[str, Any]) -> str:
    src = entry.get("source") or {}
    if src.get("type") in TRACEABLE_SOURCES and str(src.get("reference") or "").strip():
        return TRACEABLE
    return UNVERIFIED


class ModelStore:
    def __init__(self, path: Optional[str] = None, models: Optional[Dict[str, Dict[str, Any]]] = None):
        self.path = path
        self.models: Dict[str, Dict[str, Any]] = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for name, e in (data.get("models") or {}).items():
                self.add(name, e)
        for name, e in (models or {}).items():
            self.add(name, e)

    def add(self, name: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        e = dict(entry)
        e.setdefault("kind", "D")
        validate_card(name, e["kind"], e.get("card", ""))
        e["status"] = provenance(e)
        self.models[name] = e
        return e

    def add_inline(self, name: str, kind: str, card: str, where: str) -> Dict[str, Any]:
        """A card written into a sim spec: always UNVERIFIED (no document behind it)."""
        return self.add(name, {"kind": kind, "card": card, "source": {"type": "inline", "reference": where}})

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        e = self.models.get(name)
        if e is None:  # SPICE names are case-insensitive
            e = next((v for k, v in self.models.items() if k.lower() == name.lower()), None)
        return e

    def save(self) -> None:
        if not self.path:
            raise ModelError("model store has no file path")
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        out = {"version": 1, "models": {k: {kk: vv for kk, vv in v.items() if kk != "status"}
                                        for k, v in sorted(self.models.items())}}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        os.replace(tmp, self.path)

    def rows(self) -> List[Dict[str, Any]]:
        return [{"name": k, "kind": v.get("kind"), "mpn": v.get("mpn", ""), "status": v["status"],
                 "source": (v.get("source") or {}).get("type", ""),
                 "reference": (v.get("source") or {}).get("reference", "")} for k, v in sorted(self.models.items())]
