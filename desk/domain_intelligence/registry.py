"""Indexed, lazily loaded, mtime-invalidated access to library/pcb_domains. Zero external dependencies.

Only the taxonomy index is read at start; archetype files load on first access and stay cached until their
file changes. Rule sets, families, overlays and references load once each on demand.
"""
from __future__ import annotations
import json
import os
import threading
from typing import Any, Dict, Iterable, List, Optional, Tuple

from desk.domain_intelligence.models import Archetype, Overlay, ComponentFamily, Rule

_DEFAULT_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "library", "pcb_domains")


class DomainLibrary:
    def __init__(self, root: Optional[str] = None):
        self.root = os.path.abspath(root or os.environ.get("DESK_DOMAIN_LIBRARY") or _DEFAULT_ROOT)
        self._lock = threading.RLock()
        self._cache: Dict[str, Tuple[float, Any]] = {}     # path -> (mtime, parsed)
        self._rules_cache: Optional[Tuple[Tuple[Tuple[str, float], ...], Dict[str, Rule]]] = None

    # ---- raw files ---------------------------------------------------------------------------
    def _path(self, *parts: str) -> str:
        return os.path.join(self.root, *parts)

    def _load(self, path: str) -> Any:
        """Parse a JSON file, re-reading only when its mtime changed."""
        with self._lock:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                raise FileNotFoundError(path)
            hit = self._cache.get(path)
            if hit and hit[0] == mtime:
                return hit[1]
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._cache[path] = (mtime, data)
            return data

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()
            self._rules_cache = None

    # ---- taxonomy ----------------------------------------------------------------------------
    def taxonomy(self) -> Dict[str, Any]:
        return self._load(self._path("taxonomy.json"))

    @property
    def version(self) -> str:
        t = self.taxonomy()
        return f"{t.get('schema_version', '?')}@{t.get('generated', '?')}"

    def domains(self) -> List[Dict[str, Any]]:
        return list(self.taxonomy().get("domains", []))

    def domain(self, domain_id: str) -> Optional[Dict[str, Any]]:
        for d in self.domains():
            if d["domain_id"] == domain_id:
                return d
        return None

    def archetype_ids(self) -> List[str]:
        return list(self.taxonomy().get("archetype_index", {}).keys())

    def archetype_index(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.taxonomy().get("archetype_index", {}))

    def archetype(self, archetype_id: str) -> Archetype:
        idx = self.archetype_index().get(archetype_id)
        if not idx:
            raise KeyError(f"unknown archetype '{archetype_id}'")
        data = self._load(self._path(*idx["file"].split("/")))
        return Archetype(archetype_id=data["archetype_id"], name=data["name"], domain=data["domain"], data=data)

    def archetypes(self, domain: Optional[str] = None) -> Iterable[Archetype]:
        for aid, meta in self.archetype_index().items():
            if domain and meta.get("domain") != domain:
                continue
            yield self.archetype(aid)

    # ---- overlays, families, references ------------------------------------------------------
    def overlay_ids(self) -> List[str]:
        return list(self.taxonomy().get("overlay_ids", []))

    def overlay(self, overlay_id: str) -> Overlay:
        data = self._load(self._path("overlays", overlay_id + ".json"))
        return Overlay(overlay_id=data["overlay_id"], name=data["name"], data=data)

    def overlays(self) -> List[Overlay]:
        return [self.overlay(o) for o in self.overlay_ids()]

    def families(self) -> Dict[str, ComponentFamily]:
        data = self._load(self._path("component_families", "families.json"))
        return {f["family_id"]: ComponentFamily(family_id=f["family_id"], group=f["group"], name=f["name"], data=f) for f in data.get("families", [])}

    def family_groups(self) -> Dict[str, str]:
        return dict(self._load(self._path("component_families", "families.json")).get("groups", {}))

    def family(self, family_id: str) -> Optional[ComponentFamily]:
        return self.families().get(family_id)

    def references(self) -> Dict[str, Dict[str, Any]]:
        data = self._load(self._path("references", "references.json"))
        return {r["id"]: r for r in data.get("references", [])}

    def schema(self, name: str) -> Dict[str, Any]:
        return self._load(self._path("schemas", name + ".schema.json"))

    # ---- rules -------------------------------------------------------------------------------
    def rule_set_ids(self) -> List[str]:
        return list(self.taxonomy().get("rule_set_ids", []))

    def rules(self) -> Dict[str, Rule]:
        """All rules keyed by id; cached until any rule-set file changes."""
        with self._lock:
            paths = [self._path("rule_sets", rs + ".json") for rs in self.rule_set_ids()]
            stamp = tuple((p, os.path.getmtime(p)) for p in paths if os.path.exists(p))
            if self._rules_cache and self._rules_cache[0] == stamp:
                return self._rules_cache[1]
            out: Dict[str, Rule] = {}
            for p in paths:
                if not os.path.exists(p):
                    continue
                for d in self._load(p).get("rules", []):
                    r = Rule.from_dict(d)
                    if r.rule_id in out:
                        raise ValueError(f"duplicate rule id {r.rule_id} in {p}")
                    out[r.rule_id] = r
            self._rules_cache = (stamp, out)
            return out

    def rule(self, rule_id: str) -> Optional[Rule]:
        return self.rules().get(rule_id)

    # ---- search ------------------------------------------------------------------------------
    def search(self, text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Keyword search over archetype names, descriptions and classification keywords (deterministic order)."""
        q = [t for t in text.lower().replace("/", " ").split() if t]
        hits = []
        for a in self.archetypes():
            hay = (a.name + " " + a.data.get("description", "") + " " + " ".join(a.classification.get("keywords", {}).keys())).lower()
            score = sum(1 for t in q if t in hay) + sum(w for k, w in a.classification.get("keywords", {}).items() if k in text.lower())
            if score > 0:
                hits.append({"archetype_id": a.archetype_id, "name": a.name, "domain": a.domain, "score": score})
        hits.sort(key=lambda h: (-h["score"], h["archetype_id"]))
        return hits[:limit]


_LIB: Optional[DomainLibrary] = None
_LIB_LOCK = threading.Lock()


def get_library(root: Optional[str] = None) -> DomainLibrary:
    global _LIB
    with _LIB_LOCK:
        if root:
            return DomainLibrary(root)
        if _LIB is None:
            _LIB = DomainLibrary()
        return _LIB
