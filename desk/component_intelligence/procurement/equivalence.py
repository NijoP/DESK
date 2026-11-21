"""Package/footprint and electrical/mechanical equivalence for sourcing alternatives (roadmap I-5).

Pure functions. Each check answers COMPATIBLE, INCOMPATIBLE or UNVERIFIED with its reasons, and only
COMPATIBLE lets an alternative replace the designed part: missing data is UNVERIFIED, never a pass.

Spec keys (the same names in BOM part ``specs``, evidence ``specs`` and offer ``specs``):

- mechanical (checked by ``check_footprint``): ``pin_count``, ``pitch_mm``, ``body_l_mm``,
  ``body_w_mm``, ``body_h_mm``;
- "at least" ratings: keys in ``AT_LEAST_KEYS`` or ending in ``_max`` (candidate >= requirement);
- "at most" limits: keys in ``AT_MOST_KEYS`` or ending in ``_min`` (candidate <= requirement);
- everything else must be equal (numbers to 1e-6 relative, text case-insensitively).
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class Equivalence(str, enum.Enum):
    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class EquivalenceResult:
    verdict: Equivalence
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict.value, "reasons": list(self.reasons)}


MECHANICAL_KEYS = ("pin_count", "pitch_mm", "body_l_mm", "body_w_mm", "body_h_mm")
BODY_TOLERANCE_MM = 0.15
PITCH_TOLERANCE_MM = 0.01

AT_LEAST_KEYS = frozenset({
    "voltage_v", "current_a", "power_w", "vds_v", "vce_v", "vrrm_v", "vr_v", "if_a", "id_a",
    "isat_a", "irms_a", "ripple_current_a", "vin_max_v", "iout_a", "breakdown_v",
})
AT_MOST_KEYS = frozenset({
    "tolerance_pct", "rds_on_ohm", "esr_ohm", "dcr_ohm", "vf_v", "iq_a", "leakage_a", "tempco_ppm",
})

# Conservative package aliases: the same land pattern under another name. Anything not listed must
# match exactly after normalisation (SOIC-8 vs SOP-8, 0402 vs 1005, ... are NOT treated as equal).
_PACKAGE_ALIASES = {
    "SOT-23-3": "SOT-23", "SOT23": "SOT-23", "SOT23-3": "SOT-23", "TO-236": "SOT-23",
    "SOT-223-3": "SOT-223", "SOT223": "SOT-223", "SOT-223-4": "SOT-223",
    "DPAK": "TO-252", "TO-252-2": "TO-252", "D2PAK": "TO-263", "TO-263-2": "TO-263",
    "SOT-23-5L": "SOT-23-5", "SOT23-5": "SOT-23-5", "SOT-23-6L": "SOT-23-6", "SOT23-6": "SOT-23-6",
    "DO-214AC": "SMA", "DO-214AA": "SMB", "DO-214AB": "SMC",
}


def normalize_package(pkg: str) -> str:
    """Upper-case, drop spaces and any EasyEDA footprint suffix (``SOT-23-3_L2.9-W1.3...``)."""
    p = (pkg or "").strip().upper().replace(" ", "")
    if not p:
        return ""
    p = p.split("_", 1)[0]
    m = re.fullmatch(r"(?:R|C|L|LED)-?(0201|0402|0603|0805|1206|1210|1812|2010|2512)", p)
    if m:  # chip-size passives written as R0402 / C0603 / LED0805
        p = m.group(1)
    return _PACKAGE_ALIASES.get(p, p)


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def check_footprint(
    design_package: str,
    candidate_package: str,
    design_specs: Optional[Dict[str, Any]] = None,
    candidate_specs: Optional[Dict[str, Any]] = None,
    design_footprint: str = "",
    candidate_footprint: str = "",
) -> EquivalenceResult:
    """Can the candidate sit on the design's land pattern?"""
    ds, cs = design_specs or {}, candidate_specs or {}
    reasons: List[str] = []
    bad = False
    dp, cp = normalize_package(design_package), normalize_package(candidate_package)
    unknown = not dp or not cp
    if unknown:
        reasons.append(f"package not known on both sides (design '{design_package}', candidate '{candidate_package}')")
    elif dp != cp:
        bad = True
        reasons.append(f"package mismatch: design {design_package} vs candidate {candidate_package}")
    else:
        reasons.append(f"same package {dp}")
    if design_footprint and candidate_footprint:
        if design_footprint.strip().upper() != candidate_footprint.strip().upper():
            bad = True
            reasons.append(f"footprint mismatch: {design_footprint} vs {candidate_footprint}")
        else:
            reasons.append(f"same footprint {design_footprint}")

    dpc, cpc = _num(ds.get("pin_count")), _num(cs.get("pin_count"))
    if dpc is not None and cpc is not None and dpc != cpc:
        bad = True
        reasons.append(f"pin count {ds.get('pin_count')} vs {cs.get('pin_count')}")
    dpi, cpi = _num(ds.get("pitch_mm")), _num(cs.get("pitch_mm"))
    if dpi is not None and cpi is not None and abs(dpi - cpi) > PITCH_TOLERANCE_MM:
        bad = True
        reasons.append(f"pitch {dpi} mm vs {cpi} mm")
    for k in ("body_l_mm", "body_w_mm"):
        a, b = _num(ds.get(k)), _num(cs.get(k))
        if a is not None and b is not None and abs(a - b) > BODY_TOLERANCE_MM:
            bad = True
            reasons.append(f"{k} {a} vs {b} (tolerance {BODY_TOLERANCE_MM} mm)")
    a, b = _num(ds.get("body_h_mm")), _num(cs.get("body_h_mm"))
    if a is not None and b is not None and b > a + BODY_TOLERANCE_MM:
        bad = True
        reasons.append(f"candidate is taller: {b} mm vs {a} mm")

    if bad:
        return EquivalenceResult(Equivalence.INCOMPATIBLE, reasons)
    if unknown:
        return EquivalenceResult(Equivalence.UNVERIFIED, reasons)
    return EquivalenceResult(Equivalence.COMPATIBLE, reasons)


def _norm_text(v: Any) -> str:
    t = re.sub(r"\s+", "", str(v).strip().upper()).replace("Ω", "")
    return re.sub(r"OHMS?$", "", t)


def check_electrical(requirement: Dict[str, Any], candidate_specs: Dict[str, Any]) -> EquivalenceResult:
    """Does the candidate meet every electrical requirement of the design part?"""
    req = {k: v for k, v in (requirement or {}).items() if k not in MECHANICAL_KEYS and v not in (None, "")}
    if not req:
        return EquivalenceResult(Equivalence.UNVERIFIED,
                                 ["no electrical requirement recorded for the design part to compare against"])
    reasons: List[str] = []
    bad = missing = False
    for k in sorted(req):
        want, have = req[k], (candidate_specs or {}).get(k)
        if have in (None, ""):
            missing = True
            reasons.append(f"{k}: candidate value not known (need {want})")
            continue
        wn, hn = _num(want), _num(have)
        at_least = k in AT_LEAST_KEYS or k.endswith("_max")
        at_most = k in AT_MOST_KEYS or k.endswith("_min")
        if at_least or at_most:
            if wn is None or hn is None:
                missing = True
                reasons.append(f"{k}: not numeric ({want!r} vs {have!r})")
            elif at_least and hn < wn:
                bad = True
                reasons.append(f"{k}: candidate {have} < required {want}")
            elif at_most and hn > wn:
                bad = True
                reasons.append(f"{k}: candidate {have} > allowed {want}")
            else:
                reasons.append(f"{k}: {have} {'>=' if at_least else '<='} {want}")
            continue
        if wn is not None and hn is not None:
            same = abs(wn - hn) <= 1e-6 * max(abs(wn), abs(hn), 1e-12)
        else:
            same = _norm_text(want) == _norm_text(have)
        if same:
            reasons.append(f"{k}: {have} matches")
        else:
            bad = True
            reasons.append(f"{k}: candidate {have} != required {want}")
    if bad:
        return EquivalenceResult(Equivalence.INCOMPATIBLE, reasons)
    if missing:
        return EquivalenceResult(Equivalence.UNVERIFIED, reasons)
    return EquivalenceResult(Equivalence.COMPATIBLE, reasons)


_DIELECTRICS = ("X5R", "X7R", "X7S", "X6S", "X8R", "C0G", "NP0", "Y5V", "Z5U")


def requirement_from_part(part: Dict[str, Any]) -> Dict[str, Any]:
    """Electrical requirement of a BOM/block-spec part: explicit ``specs`` win over parsed text.

    Parses ``value`` and the ``rating`` text DESK block specs use ("16V X5R", "1% 62.5mW",
    "Isat 2.6A", "50V 10%").
    """
    req: Dict[str, Any] = {}
    if part.get("value"):
        req["value"] = str(part["value"])
    rating = str(part.get("rating") or "")
    if rating:
        m = re.search(r"Isat\s*(\d+(?:\.\d+)?)\s*A\b", rating, re.I)
        if m:
            req["isat_a"] = float(m.group(1))
        else:
            m = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)\s*A\b", rating)
            if m:
                req["current_a"] = float(m.group(1))
        m = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)\s*V\b", rating)
        if m:
            req["voltage_v"] = float(m.group(1))
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", rating)
        if m:
            req["tolerance_pct"] = float(m.group(1))
        m = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(m?)W\b", rating)
        if m:
            req["power_w"] = float(m.group(1)) / (1000.0 if m.group(2) else 1.0)
        for d in _DIELECTRICS:
            if re.search(rf"\b{d}\b", rating, re.I):
                req["dielectric"] = "C0G" if d == "NP0" else d
                break
    req.update({k: v for k, v in (part.get("specs") or {}).items() if v not in (None, "")})
    return req
