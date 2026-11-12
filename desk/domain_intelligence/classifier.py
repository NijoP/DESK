"""Deterministic requirement extraction and archetype classification.

Input: free text (REQUIREMENTS.md, a client sentence) and/or a structured requirements dict. Output: normalised
features, ranked candidates with reasons, overlays, required component families, missing information, conflicts
and a status that is REVIEW_REQUIRED whenever safety-relevant ambiguity exists (mains, HV, motors) or the
margin between candidates is small. No model is consulted here; an LLM may pre-extract a dict, which then goes
through exactly the same scoring. Zero external dependencies.
"""
from __future__ import annotations
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from desk.domain_intelligence.models import Requirements, Candidate, ClassificationResult
from desk.domain_intelligence.registry import DomainLibrary, get_library

_NUM = r"(\d+(?:[.,]\d+)?)"
_PROTOCOLS = {
    "usb": [r"\busb\b", r"usb-c", r"type-c", r"usb c\b"], "can": [r"\bcan ?bus\b", r"\bcan-fd\b", r"\bcanh\b", r"\bcan\b(?! be| do| not| you| it| we| also| have| handle| support| drive| the| a| an)"],
    "rs485": [r"rs-?485", r"\bmodbus\b"], "ethernet": [r"\bethernet\b", r"rj45", r"\brmii\b", r"\brgmii\b"], "gigabit": [r"\bgigabit\b", r"1000base"],
    "wifi": [r"wi-?fi", r"802\.11"], "ble": [r"\bble\b", r"\bbluetooth\b"], "lora": [r"\blora(wan)?\b"], "lte": [r"\blte\b", r"nb-?iot", r"\bcat-?m\b", r"\bcellular\b", r"\b4g\b", r"\bmodem\b"],
    "gnss": [r"\bgnss\b", r"\bgps\b", r"\bglonass\b", r"\bgalileo\b"], "hdmi": [r"\bhdmi\b"], "mipi": [r"\bmipi\b", r"csi-?2"], "pcie": [r"pci-?e(xpress)?\b", r"\bnvme\b", r"\bm\.2\b"],
    "ddr": [r"\bddr[0-9]?\b", r"\blpddr", r"\bsdram\b"], "sata": [r"\bsata\b"], "i2c": [r"\bi2c\b", r"\bi²c\b"], "spi": [r"\bspi\b", r"\bqspi\b"], "uart": [r"\buart\b", r"\bserial\b"],
    "zigbee": [r"\bzigbee\b", r"\bthread\b", r"\bmatter\b"], "uwb": [r"\buwb\b", r"ultra-?wideband"], "subghz": [r"sub-?ghz", r"\b433 ?mhz\b", r"\b315 ?mhz\b"], "poe": [r"\bpoe\b", r"power over ethernet", r"802\.3(af|at|bt)"],
    "lin": [r"\blin bus\b", r"\blin\b(?=.*(vehicle|automotive|car))"], "i2s": [r"\bi2s\b", r"\bpdm\b"],
}
_POWER_SOURCE = {"battery": [r"\bbatter", r"li-?ion", r"li-?po", r"lifepo4", r"\bcell(s)?\b", r"coin cell", r"cr2032", r"\baa\b"], "usb": [r"\busb\b", r"usb-c", r"5 ?v usb", r"vbus"],
                 "mains": [r"\bmains\b", r"\bac input\b", r"\b(110|115|120|220|230|240) ?v(ac|\b)", r"\bac-?dc\b", r"\boffline\b", r"\bline voltage\b", r"\bwall (power|outlet)\b"],
                 "solar": [r"\bsolar\b", r"\bpv\b", r"photovoltaic", r"\bmppt\b"], "vehicle": [r"\bvehicle\b", r"\bautomotive\b", r"\bcar\b", r"\btruck\b", r"\bobd", r"\b12 ?v (battery|car|vehicle)", r"load dump"],
                 "poe": [r"\bpoe\b", r"power over ethernet"], "dc_input": [r"\bdc input\b", r"\bdc barrel\b", r"\b(12|24|48) ?v (dc|input|supply|rail)"]}
_MOTOR = {"bldc": [r"\bbldc\b", r"\bbrushless\b", r"\bpmsm\b", r"\bfoc\b", r"\besc\b", r"three-?phase motor", r"3-?phase motor"], "brushed": [r"\bbrushed\b", r"\bh-?bridge\b", r"\bdc motor\b"],
          "stepper": [r"\bstepper\b", r"\bstep/dir\b", r"microstep"], "servo": [r"\bservo\b"], "ac": [r"\bac motor\b", r"\binduction motor\b", r"\bvfd\b", r"\binverter\b(?!.*(solar|battery))"],
          "solenoid": [r"\bsolenoid\b", r"\bvalve\b"], "fan": [r"\bfan\b", r"\bpump\b"]}
_CONVERTER = {"buck": [r"\bbuck\b(?!-?boost)", r"step-?down"], "boost": [r"\bboost\b(?! pfc)", r"step-?up"], "buck_boost": [r"buck-?boost"], "sepic": [r"\bsepic\b"], "flyback": [r"\bflyback\b"],
              "forward": [r"\bforward converter\b", r"active clamp"], "push_pull": [r"push-?pull"], "half_bridge": [r"half-?bridge", r"\bllc\b"], "full_bridge": [r"full-?bridge", r"phase-?shift"],
              "dab": [r"dual[- ]active[- ]bridge", r"\bdab\b"], "pfc": [r"\bpfc\b", r"power factor"]}
_CHEM = {"li_ion": [r"li-?ion", r"18650", r"21700"], "li_po": [r"li-?po\b", r"lipo"], "lifepo4": [r"lifepo4", r"lfp\b"], "li_hv": [r"4\.35 ?v", r"4\.4 ?v"], "nimh": [r"nimh"], "lead_acid": [r"lead[- ]acid", r"\bsla\b"], "lto": [r"\blto\b"]}
_UNIT = {"v": 1.0, "kv": 1000.0, "mv": 0.001, "a": 1.0, "ma": 0.001, "ua": 1e-6, "w": 1.0, "kw": 1000.0, "mw": 0.001, "hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}
_CHECKLIST = [("input_voltage_v", "supply voltage or input range"), ("current_a|power_w", "load current or power level"), ("power_source", "power source (battery, USB, mains, DC input, vehicle, PoE)"),
              ("protocols", "communication interfaces"), ("max_ambient_c|environment", "operating environment and temperature"), ("enclosure", "mechanical outline / enclosure"),
              ("manufacturing", "quantity and assembler")]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _find_values(text: str, units: Iterable[str]) -> List[float]:
    vals: List[float] = []
    for u in units:
        for m in re.finditer(_NUM + r"\s*" + u + r"(?![a-z])", text):
            vals.append(_num(m.group(1)) * _UNIT[u])
        # A range written with one unit after it: "4.5-5.5 V", "3 to 5 A", "3–5 A", "3..5 A". The ".." is literal; an
        # unescaped one matched any two characters, so "24 V, 2 A" read as a 24..2 A range and reported 24 A.
        for m in re.finditer(_NUM + r"\s*(?:-|to|–|\.\.)\s*" + _NUM + r"\s*" + u + r"(?![a-z])", text):
            vals.append(_num(m.group(1)) * _UNIT[u]); vals.append(_num(m.group(2)) * _UNIT[u])
    return vals


def _any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def extract_requirements(source: Any) -> Requirements:
    """Normalise a dict and/or text into features. Structured fields win over text extraction."""
    provided: Dict[str, Any] = {}
    text = ""
    if isinstance(source, dict):
        provided = {k: v for k, v in source.items() if v not in (None, "", [], {})}
        text = " ".join(str(v) for k, v in source.items() if isinstance(v, str)) + " " + str(source.get("text", ""))
        src = "dict"
    else:
        text = str(source or "")
        src = "text"
    t = text.lower()
    f: Dict[str, Any] = {}
    kv = [v for v in _find_values(t, ["kv"]) if v >= 500]
    iso_ctx = re.search(r"isolat|barrier|hipot|withstand|dielectric", t) is not None
    if kv and iso_ctx:
        f["isolation_voltage_v"] = max(kv)
    volts = [v for v in _find_values(t, ["kv", "mv", "v"]) if 0 < v < 100000 and not (iso_ctx and v in kv)]
    if volts:
        f["voltages_v"] = sorted(set(volts)); f["input_voltage_v"] = max(volts)
    amps = [a for a in _find_values(t, ["ua", "ma", "a"]) if 0 < a < 10000]
    if amps:
        f["current_a"] = max(amps)
        if re.search(r"\bpeak\b", t):
            f["peak_current_a"] = max(amps)
        if re.search(r"\bcontinuous\b", t):
            f["continuous_current_a"] = min(amps) if len(amps) > 1 and re.search(r"\bpeak\b", t) else max(amps)
    watts = _find_values(t, ["kw", "mw", "w"])
    if watts:
        f["power_w"] = max(watts)
    freqs = _find_values(t, ["ghz", "mhz", "khz", "hz"])
    rf = [x for x in freqs if x >= 1e6 and re.search(r"(mhz|ghz)", t)]
    if rf:
        f["rf_frequency_hz"] = max(rf)
    sw = [x for x in freqs if 1e4 <= x < 5e6 and re.search(r"(switching|fsw|khz)", t)]
    if sw:
        f["switching_frequency_hz"] = max(sw)
    f["protocols"] = sorted(k for k, pats in _PROTOCOLS.items() if _any(t, pats))
    f["power_source"] = sorted(k for k, pats in _POWER_SOURCE.items() if _any(t, pats))
    motors = sorted(k for k, pats in _MOTOR.items() if _any(t, pats))
    if motors:
        f["motor"] = motors
    conv = sorted(k for k, pats in _CONVERTER.items() if _any(t, pats))
    if conv:
        f["converter"] = conv
    chem = [k for k, pats in _CHEM.items() if _any(t, pats)]
    if chem:
        f["chemistry"] = chem[0]
    if "mains" in f["power_source"] or (f.get("input_voltage_v", 0) >= 85 and re.search(r"\bac\b", t)):
        f["mains"] = True
    if _any(t, [r"\bisolat", r"\bgalvanic", r"\breinforced\b", r"\bselv\b"]):
        f["isolation"] = True
    if _any(t, [r"non-?isolated", r"transformerless", r"capacitive dropper"]):
        f["isolation"] = False
    m = re.search(r"\b(\d{1,2})\s*s\b(?!\w)", t) or re.search(r"\b(\d{1,2})[- ]cell", t)
    if m:
        f["cells"] = int(m.group(1))
    elif re.search(r"single[- ]cell|\b1s\b|one cell", t):
        f["cells"] = 1
    m = re.search(_NUM + r"\s*(?:°|deg)?\s*c\b", t)
    if m:
        temps = [_num(x) for x in re.findall(_NUM + r"\s*(?:°|deg)?\s*c\b", t)]
        f["max_ambient_c"] = max(temps)
    for env in ("outdoor", "industrial", "marine", "medical", "automotive"):
        if re.search(r"\b" + env, t):
            f["environment"] = env; break
    if re.search(r"conformal", t):
        f["conformal_coating"] = True
    if re.search(r"\b(sink|device)\b.*\busb", t) or re.search(r"usb.*\b(powered|sink)\b", t):
        f["usb_role"] = "sink"
    elif re.search(r"\b(source|host|charger)\b.*usb|usb.*\b(source|host)\b", t):
        f["usb_role"] = "source"
    if re.search(r"\bpd\b|power delivery|20 ?v", t) and "usb" in f["protocols"]:
        f["usb_pd"] = True
    m = re.search(r"\b(eu868|us915|in865|as923|au915)\b", t)
    if m:
        f["rf_region"] = m.group(1).upper()
    if re.search(r"\b(low[- ]power|sleep|battery life|years? on)", t):
        f["battery_life_target"] = True
    if re.search(r"\b(\d{2})[- ]bit\b", t):
        f["resolution_bits"] = int(re.search(r"\b(\d{2})[- ]bit\b", t).group(1))
    if _any(t, [r"\bsensor", r"\banalog", r"\bmeasure", r"\baudio\b"]):
        f["signal_type"] = "audio" if "audio" in t else "sensor" if "sensor" in t else "analog"
    if _any(t, [r"\benclosure\b", r"\boutline\b", r"\bmm x\b", r"\bdimensions?\b"]):
        f["enclosure"] = True
    if _any(t, [r"\bqty\b", r"\bquantity\b", r"\bunits?\b", r"\bjlc", r"\bassembl"]):
        f["manufacturing"] = True
    # structured fields override extracted ones
    for k, v in provided.items():
        if k != "text":
            f[k] = v
    f["protocols"] = sorted(set(f.get("protocols", [])))
    f["power_source"] = sorted(set(f.get("power_source", [])))
    return Requirements(text=text, features=f, provided_fields=sorted(provided.keys()), source=src)


_KW_CACHE: Dict[str, "re.Pattern[str]"] = {}
# Domains whose archetypes describe a feature of a larger board (an interface), not the board itself.
PERIPHERAL_DOMAINS = {"interfaces_comms"}
_CONTROLLER_HINT = re.compile(r"\b(mcu|microcontroller|controller board|stm32|esp32|rp2040|nrf5\d|pic\d|atmega|samd|controller)\b")


def _kw_match(text: str, kw: str) -> bool:
    """Whole-word match; a keyword ending in a digit (stm32, esp32, nrf52) may continue with a part suffix (stm32f4)."""
    pat = _KW_CACHE.get(kw)
    if pat is None:
        tail = r"" if kw[-1].isdigit() else r"(?![a-z0-9])"
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(kw) + tail)
        _KW_CACHE[kw] = pat
    return pat.search(text) is not None


def _score(a, feats: Dict[str, Any], text: str) -> Candidate:
    c = Candidate(archetype_id=a.archetype_id, domain=a.domain, score=0.0)
    cls = a.classification
    for kw, w in cls.get("keywords", {}).items():
        if _kw_match(text, kw.lower()):
            c.score += float(w); c.reasons.append(f"keyword '{kw}' (+{w})")
    spec = cls.get("features", {})
    v = feats.get("input_voltage_v")
    if "input_voltage_v" in spec and v is not None:
        lo, hi = spec["input_voltage_v"]
        if lo <= v <= hi:
            c.score += 3; c.reasons.append(f"input {v:g} V within {lo:g}-{hi:g} V (+3)")
        elif v > 2 * hi or v < lo / 2:
            c.score -= 2; c.penalties.append(f"input {v:g} V far outside {lo:g}-{hi:g} V (-2)")
    if "protocols_any" in spec:
        hits = sorted(set(spec["protocols_any"]) & set(feats.get("protocols", [])))
        if hits:
            pts = min(6, 3 * len(hits)); c.score += pts; c.reasons.append(f"protocols {hits} (+{pts})")
    if "power_source" in spec:
        hits = sorted(set(spec["power_source"]) & set(feats.get("power_source", [])))
        if hits:
            c.score += 3; c.reasons.append(f"power source {hits} (+3)")
    if "rf_frequency_hz" in spec and feats.get("rf_frequency_hz"):
        lo, hi = spec["rf_frequency_hz"]; fz = feats["rf_frequency_hz"]
        if lo <= fz <= hi:
            c.score += 4; c.reasons.append(f"RF {fz/1e6:g} MHz within band (+4)")
        else:
            c.score -= 3; c.penalties.append(f"RF {fz/1e6:g} MHz outside {lo/1e6:g}-{hi/1e6:g} MHz (-3)")
    if "motor" in spec:
        req_m = set(feats.get("motor", []))
        if req_m & set(spec["motor"]):
            c.score += 4; c.reasons.append(f"motor {sorted(req_m & set(spec['motor']))} (+4)")
        elif req_m:
            c.score -= 3; c.penalties.append(f"motor type {sorted(req_m)} not {spec['motor']} (-3)")
    if "converter" in spec and feats.get("converter"):
        hits = sorted(set(spec["converter"]) & set(feats["converter"]))
        if hits:
            c.score += 4; c.reasons.append(f"converter {hits} (+4)")
    if spec.get("mains") is True:
        if feats.get("mains"):
            c.score += 4; c.reasons.append("mains input (+4)")
        elif feats.get("power_source") and not set(feats["power_source"]) & {"mains"}:
            c.score -= 2; c.penalties.append("no mains source mentioned (-2)")
    if "isolation" in spec and "isolation" in feats:
        if bool(spec["isolation"]) == bool(feats["isolation"]):
            c.score += 2; c.reasons.append("isolation requirement matches (+2)")
        else:
            c.score -= 3; c.penalties.append("isolation requirement contradicts (-3)")
    if "cells" in spec and feats.get("cells"):
        lo, hi = spec["cells"]
        if lo <= feats["cells"] <= hi:
            c.score += 2; c.reasons.append(f"{feats['cells']} cells (+2)")
    if "power_w" in spec and feats.get("power_w"):
        lo, hi = spec["power_w"]
        if lo <= feats["power_w"] <= hi:
            c.score += 2; c.reasons.append(f"{feats['power_w']:g} W within range (+2)")
    return c


def _overlay_applies(overlay, feats: Dict[str, Any]) -> bool:
    from desk.domain_intelligence.rule_engine import applies
    return applies(overlay.applies_when, feats)


def classify(source: Any, lib: Optional[DomainLibrary] = None) -> ClassificationResult:
    lib = lib or get_library()
    req = extract_requirements(source)
    feats, text = req.features, req.text.lower()
    cands = sorted((_score(a, feats, text) for a in lib.archetypes()), key=lambda c: (-c.score, c.archetype_id))
    evidence: List[str] = []
    conflicts: List[str] = []
    # An interface archetype on top of a board that clearly has a controller is an overlay, not the board:
    # promote the best controller-class candidate when the text names an MCU/controller.
    demoted: Optional[str] = None
    if cands and cands[0].domain in PERIPHERAL_DOMAINS and _CONTROLLER_HINT.search(text):
        for i, c in enumerate(cands[1:], start=1):
            if c.domain not in PERIPHERAL_DOMAINS and c.score >= max(6.0, 0.4 * cands[0].score):
                evidence.append(f"{cands[0].archetype_id} is an interface feature; {c.archetype_id} describes the board (controller named)")
                demoted = cands[0].archetype_id
                cands.insert(0, cands.pop(i))
                break
    top = cands[0] if cands else None
    # the demoted interface is a secondary archetype, not a competitor for the primary slot
    second = max([c.score for c in cands[1:] if c.archetype_id != demoted] or [0.0])
    primary: Optional[str] = None
    status = "UNCLASSIFIED"
    confidence = 0.0
    if top and top.score >= 8 and top.score - second >= 3:
        status = "CLASSIFIED"; primary = top.archetype_id
        confidence = round(min(0.95, 0.5 + 0.04 * (top.score - second) + 0.01 * top.score), 2)
    elif top and top.score >= 4:
        status = "REVIEW_REQUIRED"; primary = top.archetype_id
        confidence = round(min(0.6, 0.2 + 0.03 * top.score), 2)
        if top.score - second < 3:
            conflicts.append(f"close candidates: {top.archetype_id} ({top.score:g}) vs {cands[1].archetype_id} ({second:g})")
    if top:
        evidence += [f"{top.archetype_id}: {r}" for r in top.reasons[:8]]
    secondary = [c.archetype_id for c in cands[1:4] if primary and c.score >= max(4.0, 0.4 * top.score) and c.archetype_id != primary]
    # Safety: mains / HV ambiguity is never resolved silently.
    mains_cands = [c for c in cands[:5] if c.domain == "ac_mains_hv" and c.score >= 4]
    overlays: List[str] = []
    if primary:
        overlays += lib.archetype(primary).overlays
    for o in lib.overlays():
        if _overlay_applies(o, feats) and o.overlay_id not in overlays:
            overlays.append(o.overlay_id); evidence.append(f"overlay {o.overlay_id} from features")
    if feats.get("mains") and "mains_safety_isolation" not in overlays:
        overlays.append("mains_safety_isolation"); evidence.append("overlay mains_safety_isolation added: mains detected")
    if (mains_cands or feats.get("mains")) and (not primary or lib.archetype(primary).domain != "ac_mains_hv"):
        conflicts.append("possible mains/high-voltage involvement; a mains archetype scored or mains was detected while the primary is not a mains archetype")
        if status == "CLASSIFIED":
            status = "REVIEW_REQUIRED"; confidence = min(confidence, 0.6)
    elif primary and lib.archetype(primary).domain == "ac_mains_hv" and (_CONTROLLER_HINT.search(text) or re.search(r"\bsensor|\bnode\b|\biot\b", text)):
        conflicts.append("mains archetype selected but the text also describes a controller/sensor product: confirm whether this is the mains supply section or a mains-powered device (both need the mains_safety_isolation overlay)")
        if status == "CLASSIFIED":
            status = "REVIEW_REQUIRED"; confidence = min(confidence, 0.6)
    if feats.get("motor") and primary and lib.archetype(primary).domain not in ("motor_control", "ac_mains_hv"):
        conflicts.append("motor mentioned but the primary archetype is not a motor-control archetype; motor_drive overlay applied")
        if "motor_drive" not in overlays:
            overlays.append("motor_drive")
    # Required component families: primary required roles + overlay additions (never invented parts, only roles).
    fam: List[str] = []
    if primary:
        fam += lib.archetype(primary).required_roles
    for oid in overlays:
        for fid in lib.overlay(oid).families:
            if fid not in fam:
                fam.append(fid)
    missing: List[str] = []
    for key, label in _CHECKLIST:
        if not any(k in feats and feats[k] not in ([], None, False) for k in key.split("|")):
            missing.append(label)
    if primary:
        a = lib.archetype(primary)
        missing += [f"confirm for {primary}: {x}" for x in a.data.get("typical_input_requirements", [])[:4]]
        if a.domain == "ac_mains_hv" or "mains_safety_isolation" in overlays:
            if "voltage_rails" not in feats:
                missing.append("voltage_rails: every mains/HV net with its working voltage (fail-closed)")
        if "battery_management" in overlays and not feats.get("chemistry"):
            missing.append("battery chemistry (charge voltage cannot be derived without it)")
    return ClassificationResult(primary_archetype=primary, secondary_archetypes=secondary, required_overlays=overlays,
                                required_component_families=fam, candidates=cands[:10], missing_information=missing,
                                conflicts=conflicts, confidence=confidence, classification_status=status, evidence=evidence,
                                features=feats)
