"""Insulation coordination engine: clearance and creepage as separate, sourced, status-carrying results.

Standard reference: IEC 60664-1:2020 (Edition 3.0) including Amendment 1:2025, where applicable. DESK does not hold the
licensed text, so this module contains no table values; it reads them from a versioned dataset (desk/insulation/
tables.py) in which every value carries provenance.

Two quantities, two code paths, two result types. They are never mixed:

    evaluate_clearance(inputs) -> ClearanceResult   shortest distance through air. Driven by the rated impulse voltage
                                                    (declared, or from the overvoltage category and the mains voltage),
                                                    the pollution degree, the insulation type and the altitude. Altitude
                                                    correction applies here and only here.
    evaluate_creepage(inputs)  -> CreepageResult    shortest distance along the insulating surface. Driven by the
                                                    working voltage (RMS), the pollution degree, the material group
                                                    (or CTI), the insulation type and the surface coating.

Each result carries:

    value_mm        the value derived from the dataset when every required input is declared (else None)
    guidance_mm     a conservative provisional spacing for preliminary layout guidance: the value itself, or the
                    worst case over the undeclared inputs when the dataset covers every case; None when no number
                    can be shown not to under-state the requirement
    status          VERIFIED-AGAINST-TABLE  every value used is a VERIFIED dataset cell hit exactly (no rounding)
                    PROVISIONAL             derived from the dataset, but a value used is PROVISIONAL, the lookup
                                            rounded up, or it rests on a DESK assumption
                    UNVERIFIED              a required input, table or rule is missing
    references, standard edition, dataset id, assumptions, missing inputs and the provenance of every value used.

No status is a compliance statement. VERIFIED-AGAINST-TABLE means "equals a verified table cell", nothing more. Only
`InsulationAssessment.compliance_statement` with a matching engineering sign-off record (desk/insulation/signoff.py)
may say so, and only when both results are VERIFIED-AGAINST-TABLE.

Missing inputs are never defaulted: an undeclared input makes the result UNVERIFIED and is listed in missing_inputs.

Zero external dependencies.
"""
from __future__ import annotations

import enum
import hashlib
import json
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Optional, Tuple

from desk.insulation import tables as T

NOT_A_COMPLIANCE_CLAIM = ("NOT A COMPLIANCE CLAIM: software result for preliminary layout guidance; engineering review "
                          "is required before safety compliance sign-off.")


class Status(str, enum.Enum):
    VERIFIED_AGAINST_TABLE = "VERIFIED-AGAINST-TABLE"
    PROVISIONAL = "PROVISIONAL"
    UNVERIFIED = "UNVERIFIED"


_RANK = {Status.VERIFIED_AGAINST_TABLE: 0, Status.PROVISIONAL: 1, Status.UNVERIFIED: 2}


def _worse(a: Status, b: Status) -> Status:
    return a if _RANK[a] >= _RANK[b] else b


class InsulationType(str, enum.Enum):
    FUNCTIONAL = "functional"
    BASIC = "basic"
    REINFORCED = "reinforced"


OVERVOLTAGE_CATEGORIES = ("I", "II", "III", "IV")
UNCOATED = "none"


@dataclass(frozen=True)
class InsulationInputs:
    """Explicit design inputs. None means "not declared"; the engine never substitutes a default."""
    insulation_type: Optional[InsulationType] = None
    working_voltage_v: Optional[float] = None         # V RMS across the insulation (creepage)
    rated_impulse_voltage_v: Optional[float] = None   # V peak (clearance)
    overvoltage_category: Optional[str] = None        # I..IV (with mains_voltage_v: rated impulse from the dataset)
    mains_voltage_v: Optional[float] = None           # nominal mains voltage the equipment is supplied from
    pollution_degree: Optional[int] = None            # 1..4
    material_group: Optional[str] = None              # I, II, IIIa, IIIb ('III' = IIIa/IIIb unknown -> IIIb)
    cti: Optional[float] = None                       # comparative tracking index (needs a CTI table to give a group)
    altitude_m: Optional[float] = None                # operating altitude above sea level
    coating: Optional[str] = None                     # "none" (uncoated) or the coating declared; never credited
    environment: Optional[str] = None                 # free-text operating environment, recorded as an assumption

    def __post_init__(self):
        it = self.insulation_type
        if it is not None and not isinstance(it, InsulationType):
            try:
                object.__setattr__(self, "insulation_type", InsulationType(str(it).strip().lower()))
            except ValueError:
                raise ValueError(f"insulation_type must be functional, basic or reinforced, got {it!r}")
        for name in ("working_voltage_v", "rated_impulse_voltage_v", "mains_voltage_v", "cti", "altitude_m"):
            v = getattr(self, name)
            if v is None:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{name} must be a number, got {v!r}")
            if name not in ("altitude_m", "working_voltage_v") and v < 0:
                raise ValueError(f"{name} must be >= 0, got {v!r}")
            object.__setattr__(self, name, abs(float(v)) if name == "working_voltage_v" else float(v))
        if self.overvoltage_category is not None:
            ovc = str(self.overvoltage_category).strip().upper()
            if ovc not in OVERVOLTAGE_CATEGORIES:
                raise ValueError(f"overvoltage_category must be one of {OVERVOLTAGE_CATEGORIES}, got {ovc!r}")
            object.__setattr__(self, "overvoltage_category", ovc)
        pd = self.pollution_degree
        if pd is not None and (isinstance(pd, bool) or pd not in (1, 2, 3, 4)):
            raise ValueError(f"pollution_degree must be 1, 2, 3 or 4, got {pd!r}")
        if self.material_group is not None and T.normalise_material_group(self.material_group) is None:
            raise ValueError(f"material_group must be I, II, IIIa or IIIb, got {self.material_group!r}")
        if self.coating is not None:
            object.__setattr__(self, "coating", str(self.coating).strip().lower() or UNCOATED)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InsulationInputs":
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - known)
        if unknown:
            raise ValueError(f"unknown insulation input(s) {unknown}; known inputs are {sorted(known)}")
        return cls(**d)

    def to_dict(self) -> Dict[str, Any]:
        out = {f.name: getattr(self, f.name) for f in fields(self)}
        if self.insulation_type is not None:
            out["insulation_type"] = self.insulation_type.value
        return out


@dataclass(frozen=True)
class _Result:
    value_mm: Optional[float]
    guidance_mm: Optional[float]
    guidance_basis: str
    status: Status
    standard: str
    dataset_id: str
    insulation_type: Optional[str]
    pollution_degree: Optional[int]
    references: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    missing_inputs: Tuple[str, ...] = ()
    provenance: Tuple[Dict[str, Any], ...] = ()

    QUANTITY = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"quantity": self.QUANTITY}
        for f in fields(self):
            v = getattr(self, f.name)
            d[f.name] = list(v) if isinstance(v, tuple) else v
        d["status"] = self.status.value
        d["value_mm"] = None if self.value_mm is None else round(self.value_mm, 4)
        d["guidance_mm"] = None if self.guidance_mm is None else round(self.guidance_mm, 4)
        d["note"] = NOT_A_COMPLIANCE_CLAIM
        return d


@dataclass(frozen=True)
class ClearanceResult(_Result):
    """Clearance (through air). Never built from creepage data."""
    rated_impulse_voltage_v: Optional[float] = None
    altitude_m: Optional[float] = None
    altitude_factor: Optional[float] = None

    QUANTITY = "clearance"


@dataclass(frozen=True)
class CreepageResult(_Result):
    """Creepage (along the surface). Never built from clearance data; no altitude correction."""
    working_voltage_v: Optional[float] = None
    material_group: Optional[str] = None

    QUANTITY = "creepage"


# ------------------------------------------------------------------------------------------------------------ shared
def _prov(source: str, p: T.Provenance) -> Dict[str, Any]:
    d = p.to_dict()
    d["value_of"] = source
    return d


def _cell_status(lk: T.Lookup) -> Status:
    return Status.VERIFIED_AGAINST_TABLE if (lk.cell.provenance.verified and lk.exact) else Status.PROVISIONAL


def _rule_status(rule: T.Rule) -> Status:
    return Status.VERIFIED_AGAINST_TABLE if rule.provenance.verified else Status.PROVISIONAL


def _round_note(what: str, query: float, lk: T.Lookup, unit: str) -> Optional[str]:
    if lk.below_first:
        return (f"{what} {query:g} {unit} is below the first {what} row ({lk.row:g} {unit}); the first row is used "
                f"(over-states, never under-states)")
    if not lk.exact:
        return f"{what} {query:g} {unit} rounded up to the {lk.row:g} {unit} row (no interpolation)"
    return None


def _environment_notes(inputs: InsulationInputs, quantity: str) -> List[str]:
    out = []
    if inputs.coating is not None and inputs.coating != UNCOATED:
        out.append(f"coating '{inputs.coating}' declared; no coating credit (IEC 60664-3) is taken, the uncoated "
                   f"{quantity} is used (conservative)")
    if inputs.environment:
        out.append(f"environment declared as '{inputs.environment}'; no environmental condition beyond the "
                   f"pollution degree is modelled")
    return out


# ---------------------------------------------------------------------------------------------------------- creepage
def _material_group(inputs: InsulationInputs, ds: T.Dataset) -> Tuple[Optional[str], List[str], List[Dict[str, Any]], bool]:
    """(group, notes, provenance, conflict). A CTI gives a group only through the dataset's CTI table."""
    notes: List[str] = []
    provs: List[Dict[str, Any]] = []
    declared = T.normalise_material_group(inputs.material_group)
    if declared and str(inputs.material_group).strip().upper() == "III":
        notes.append("material group 'III' declared without a or b: IIIb (the worse) is used")
    from_cti: Optional[str] = None
    if inputs.cti is not None:
        table = ds.table("material_group_by_cti")
        if table is None:
            notes.append(f"CTI {inputs.cti:g} declared but the dataset has no CTI-to-material-group table; the CTI "
                         f"is not converted")
        else:
            for group, lo, hi, prov in table.extra["bands"]:
                if inputs.cti >= lo and (hi is None or inputs.cti < hi):
                    from_cti = group
                    provs.append(_prov(f"material group from CTI {inputs.cti:g}", prov))
                    break
            if from_cti is None:
                notes.append(f"CTI {inputs.cti:g} falls in no band of the dataset's CTI table")
    if declared and from_cti and declared != from_cti:
        notes.append(f"declared material group {declared} disagrees with group {from_cti} from CTI {inputs.cti:g}")
        return None, notes, provs, True
    return declared or from_cti, notes, provs, False


def _creepage_value(table: T.Table, ds: T.Dataset, v: float, pd: int, mg: str, it: InsulationType):
    """(value, status, notes, provenance, refs, reason). value None with a reason when the dataset cannot give it."""
    cols = T.columns_for(table, pd, mg)
    if not cols:
        return None, Status.UNVERIFIED, [], [], [], f"dataset has no creepage column for PD{pd}, material group {mg}"
    best = None
    for col in cols:
        lk = T.lookup_up(col, v)
        if lk is None:
            return (None, Status.UNVERIFIED, [], [], [],
                    f"working voltage {v:g} V is above the last creepage row ({col.rows[-1]:g} V) of column {col.name}")
        if best is None or lk.cell.value > best[1].cell.value:
            best = (col, lk)
    col, lk = best
    status = _cell_status(lk)
    notes = [n for n in [_round_note("working voltage", v, lk, "V")] if n]
    provs = [_prov(f"creepage {col.name} @ {lk.row:g} V", lk.cell.provenance)]
    refs: List[str] = []
    value = lk.cell.value
    if it == InsulationType.REINFORCED:
        rule = ds.rule("creepage_reinforced_factor")
        if rule is None:
            return None, Status.UNVERIFIED, notes, provs, refs, "dataset has no rule for reinforced creepage"
        value *= float(rule.value)
        status = _worse(status, _rule_status(rule))
        refs.append(rule.reference)
        provs.append(_prov(f"reinforced creepage factor {rule.value:g}", rule.provenance))
    elif it == InsulationType.FUNCTIONAL:
        notes.append("functional insulation uses the same creepage column as basic insulation (per the table "
                     "reference of the dataset)")
    return value, status, notes, provs, refs, None


def evaluate_creepage(inputs: InsulationInputs, dataset: Optional[T.Dataset] = None) -> CreepageResult:
    """Creepage distance. Reads only the creepage table, the CTI table and the reinforced-creepage rule; never the
    clearance, rated-impulse or altitude data."""
    ds = dataset or T.load_dataset()
    missing: List[str] = []
    it = inputs.insulation_type
    v = inputs.working_voltage_v
    pd = inputs.pollution_degree
    if it is None:
        missing.append("insulation_type")
    if v is None:
        missing.append("working_voltage_v")
    if pd is None:
        missing.append("pollution_degree")
    mg, notes, provs, conflict = _material_group(inputs, ds)
    if mg is None:
        missing.append("material_group (conflicting with cti)" if conflict else "material_group (or cti with a CTI table)")
    if inputs.coating is None:
        missing.append("coating")
    notes += _environment_notes(inputs, "creepage")
    refs: List[str] = []
    table = ds.table("creepage")
    base = dict(standard=ds.standard_label, dataset_id=ds.dataset_id, insulation_type=it.value if it else None,
                pollution_degree=pd, working_voltage_v=v, material_group=mg)
    if table is None:
        return CreepageResult(value_mm=None, guidance_mm=None, status=Status.UNVERIFIED,
                              guidance_basis="no creepage table in the dataset; no provisional value can be given",
                              assumptions=tuple(notes), missing_inputs=tuple(missing + ["table: creepage"]),
                              provenance=tuple(provs), **base)
    refs.append(table.reference)
    value: Optional[float] = None
    status = Status.UNVERIFIED
    if not missing:
        value, status, n2, p2, r2, reason = _creepage_value(table, ds, v, pd, mg, it)
        notes += n2
        provs += p2
        refs += r2
        if reason:
            notes.append(reason)
    if value is not None:
        guidance, basis = value, "the derived creepage value"
    else:
        guidance, basis = _creepage_worst_case(table, ds, v, pd, mg, it)
        if inputs.coating is None and guidance is not None:
            basis += "; coating undeclared: uncoated surface assumed (no coating is ever credited)"
    return CreepageResult(value_mm=value, guidance_mm=guidance, guidance_basis=basis, status=status,
                          references=tuple(dict.fromkeys(refs)), assumptions=tuple(notes),
                          missing_inputs=tuple(missing), provenance=tuple(provs), **base)


def _creepage_worst_case(table: T.Table, ds: T.Dataset, v: Optional[float], pd: Optional[int], mg: Optional[str],
                         it: Optional[InsulationType]) -> Tuple[Optional[float], str]:
    if v is None:
        return None, "working voltage undeclared: no provisional creepage can be given"
    pds = [pd] if pd is not None else [1, 2, 3, 4]
    mgs = [mg] if mg is not None else list(T.MATERIAL_GROUPS)
    its = [it] if it is not None else [InsulationType.REINFORCED]
    worst: Optional[float] = None
    for p in pds:
        for g in mgs:
            for i in its:
                val, _, _, _, _, reason = _creepage_value(table, ds, v, p, g, i)
                if val is None:
                    return None, (f"no conservative provisional creepage: the dataset cannot cover every undeclared "
                                  f"case ({reason})")
                worst = val if worst is None else max(worst, val)
    over = [n for n, x in (("pollution degree", pd), ("material group", mg), ("insulation type", it)) if x is None]
    return worst, ("PROVISIONAL LAYOUT GUIDANCE: worst case over undeclared " + ", ".join(over) if over
                   else "PROVISIONAL LAYOUT GUIDANCE")


# --------------------------------------------------------------------------------------------------------- clearance
def _rated_impulse(inputs: InsulationInputs, ds: T.Dataset):
    """(uimp, status, notes, provenance, refs, missing)."""
    notes: List[str] = []
    provs: List[Dict[str, Any]] = []
    refs: List[str] = []
    declared = inputs.rated_impulse_voltage_v
    from_table: Optional[float] = None
    status = Status.PROVISIONAL
    if inputs.overvoltage_category and inputs.mains_voltage_v is not None:
        table = ds.table("rated_impulse_voltage")
        if table is None:
            notes.append("overvoltage category and mains voltage declared but the dataset has no rated-impulse-voltage "
                         "table")
        elif inputs.overvoltage_category not in table.columns:
            notes.append(f"dataset has no rated-impulse column for overvoltage category {inputs.overvoltage_category}")
        else:
            lk = T.lookup_up(table.columns[inputs.overvoltage_category], inputs.mains_voltage_v)
            if lk is None:
                notes.append(f"mains voltage {inputs.mains_voltage_v:g} V is above the rated-impulse table")
            else:
                from_table = lk.cell.value
                status = _cell_status(lk)
                refs.append(table.reference)
                provs.append(_prov(f"rated impulse OVC {inputs.overvoltage_category} @ {lk.row:g} V mains",
                                   lk.cell.provenance))
                rn = _round_note("mains voltage", inputs.mains_voltage_v, lk, "V")
                if rn:
                    notes.append(rn)
    if declared is not None and from_table is not None:
        if declared + 1e-9 < from_table:
            notes.append(f"declared rated impulse voltage {declared:g} V is below {from_table:g} V from the "
                         f"overvoltage category and mains voltage; the declaration must be reviewed")
            return max(declared, from_table), Status.UNVERIFIED, notes, provs, refs, ["rated_impulse_voltage_v (conflict)"]
        notes.append(f"declared rated impulse voltage {declared:g} V used (table gives {from_table:g} V)")
        return declared, status, notes, provs, refs, []
    if declared is not None:
        # A declared design input is not a table value: it does not lower the status (engineering review checks it).
        notes.append(f"rated impulse voltage {declared:g} V as declared (not derived from an overvoltage category)")
        return declared, Status.VERIFIED_AGAINST_TABLE, notes, provs, refs, []
    if from_table is not None:
        return from_table, status, notes, provs, refs, []
    return None, Status.UNVERIFIED, notes, provs, refs, [
        "rated_impulse_voltage_v (or overvoltage_category + mains_voltage_v with a rated-impulse table)"]


def _clearance_value(table: T.Table, ds: T.Dataset, uimp: float, pd: int, it: InsulationType):
    """Clearance before altitude correction: (value, status, notes, provenance, refs, reason)."""
    cols = T.columns_for(table, pd)
    if not cols:
        return None, Status.UNVERIFIED, [], [], [], f"dataset has no clearance column for PD{pd}"
    col = cols[0]
    lk = T.lookup_up(col, uimp)
    if lk is None:
        return (None, Status.UNVERIFIED, [], [], [],
                f"rated impulse voltage {uimp:g} V is above the last clearance row ({col.rows[-1]:g} V)")
    notes = [n for n in [_round_note("rated impulse voltage", uimp, lk, "V")] if n]
    refs: List[str] = []
    status = _cell_status(lk)
    if it == InsulationType.REINFORCED:
        rule = ds.rule("clearance_reinforced")
        if rule is None:
            return None, Status.UNVERIFIED, notes, [], refs, "dataset has no rule for reinforced clearance"
        refs.append(rule.reference)
        status = _worse(status, _rule_status(rule))
        rule_prov = _prov(f"reinforced clearance rule ({rule.method})", rule.provenance)
        if rule.method == "impulse_step":
            idx = col.rows.index(lk.row)
            if idx + 1 >= len(col.rows):
                return (None, Status.UNVERIFIED, notes, [rule_prov], refs,
                        f"no clearance row above {lk.row:g} V for the reinforced step")
            lk = T.Lookup(cell=col.cells[idx + 1], row=col.rows[idx + 1], exact=lk.exact, below_first=lk.below_first)
            status = _worse(status, _cell_status(lk))
            notes.append(f"reinforced: clearance of the next rated-impulse row ({lk.row:g} V)")
            value = lk.cell.value
        else:
            value = lk.cell.value * float(rule.value)
            notes.append(f"reinforced: basic clearance x {rule.value:g}")
        return value, status, notes, [_prov(f"clearance {col.name} @ {lk.row:g} V", lk.cell.provenance), rule_prov], refs, None
    if it == InsulationType.FUNCTIONAL:
        notes.append("functional insulation dimensioned with the basic-insulation clearance lookup (DESK conservative "
                     "assumption; confirm the functional-insulation clause)")
        status = _worse(status, Status.PROVISIONAL)
    return lk.cell.value, status, notes, [_prov(f"clearance {col.name} @ {lk.row:g} V", lk.cell.provenance)], refs, None


def _altitude_factor(table: T.Table, ds: T.Dataset, altitude_m: float):
    """(factor, status, notes, provenance, refs, reason). Clearance only."""
    basis: Optional[T.Cell] = table.extra.get("altitude_basis_m")
    if basis is None:
        return None, Status.UNVERIFIED, [], [], [], "dataset does not state the altitude its clearance table is valid to"
    provs = [_prov("clearance altitude basis", basis.provenance)]
    status = Status.VERIFIED_AGAINST_TABLE if basis.provenance.verified else Status.PROVISIONAL
    if altitude_m <= basis.value + 1e-9:
        return 1.0, status, [f"altitude {altitude_m:g} m within the {basis.value:g} m basis of the clearance table: "
                             f"no correction"], provs, [], None
    alt = ds.table("altitude_correction")
    if alt is None:
        return (None, Status.UNVERIFIED, [], provs, [],
                f"altitude {altitude_m:g} m exceeds the {basis.value:g} m basis and the dataset has no altitude "
                f"correction table")
    lk = T.lookup_up(alt.columns["factor"], altitude_m)
    if lk is None:
        return None, Status.UNVERIFIED, [], provs, [alt.reference], f"altitude {altitude_m:g} m is above the correction table"
    provs.append(_prov(f"altitude factor @ {lk.row:g} m", lk.cell.provenance))
    notes = [f"altitude {altitude_m:g} m: clearance multiplied by {lk.cell.value:g}"]
    rn = _round_note("altitude", altitude_m, lk, "m")
    if rn:
        notes.append(rn)
    return lk.cell.value, _worse(status, _cell_status(lk)), notes, provs, [alt.reference], None


def evaluate_clearance(inputs: InsulationInputs, dataset: Optional[T.Dataset] = None) -> ClearanceResult:
    """Clearance distance. Reads only the clearance, rated-impulse and altitude tables and the reinforced-clearance
    rule; never the creepage table, the working voltage RMS, the material group or the CTI."""
    ds = dataset or T.load_dataset()
    missing: List[str] = []
    it = inputs.insulation_type
    pd = inputs.pollution_degree
    alt = inputs.altitude_m
    if it is None:
        missing.append("insulation_type")
    if pd is None:
        missing.append("pollution_degree")
    if alt is None:
        missing.append("altitude_m")
    uimp, ustatus, notes, provs, refs, umissing = _rated_impulse(inputs, ds)
    missing += umissing
    notes += _environment_notes(inputs, "clearance")
    table = ds.table("clearance")
    base = dict(standard=ds.standard_label, dataset_id=ds.dataset_id, insulation_type=it.value if it else None,
                pollution_degree=pd, rated_impulse_voltage_v=uimp, altitude_m=alt)
    if table is None:
        return ClearanceResult(value_mm=None, guidance_mm=None, status=Status.UNVERIFIED, altitude_factor=None,
                               guidance_basis="no clearance table in the dataset; no provisional value can be given",
                               references=tuple(dict.fromkeys(refs)), assumptions=tuple(notes),
                               missing_inputs=tuple(missing + ["table: clearance"]), provenance=tuple(provs), **base)
    refs.append(table.reference)
    value: Optional[float] = None
    factor: Optional[float] = None
    status = Status.UNVERIFIED
    if not missing:
        v0, status, n2, p2, r2, reason = _clearance_value(table, ds, uimp, pd, it)
        notes += n2
        provs += p2
        refs += r2
        if reason:
            notes.append(reason)
        if v0 is not None:
            factor, fstatus, n3, p3, r3, reason = _altitude_factor(table, ds, alt)
            notes += n3
            provs += p3
            refs += r3
            if factor is None:
                notes.append(reason)
                status = Status.UNVERIFIED
            else:
                value = v0 * factor
                status = _worse(_worse(status, fstatus), ustatus)
        else:
            status = Status.UNVERIFIED
    if value is not None:
        guidance, basis = value, "the derived clearance value"
    else:
        guidance, basis = _clearance_worst_case(table, ds, uimp, pd, it, alt)
    return ClearanceResult(value_mm=value, guidance_mm=guidance, guidance_basis=basis, status=status,
                           altitude_factor=factor, references=tuple(dict.fromkeys(refs)), assumptions=tuple(notes),
                           missing_inputs=tuple(missing), provenance=tuple(provs), **base)


def _clearance_worst_case(table: T.Table, ds: T.Dataset, uimp: Optional[float], pd: Optional[int],
                          it: Optional[InsulationType], alt: Optional[float]) -> Tuple[Optional[float], str]:
    if uimp is None:
        return None, "rated impulse voltage unknown: no provisional clearance can be given"
    if alt is None:
        return None, "altitude undeclared: no provisional clearance can be given (the correction is unbounded)"
    pds = [pd] if pd is not None else [1, 2, 3, 4]
    its = [it] if it is not None else [InsulationType.REINFORCED]
    worst: Optional[float] = None
    for p in pds:
        for i in its:
            val, _, _, _, _, reason = _clearance_value(table, ds, uimp, p, i)
            if val is None:
                return None, f"no conservative provisional clearance: the dataset cannot cover every undeclared case ({reason})"
            worst = val if worst is None else max(worst, val)
    factor, _, _, _, _, reason = _altitude_factor(table, ds, alt)
    if factor is None:
        return None, f"no conservative provisional clearance: {reason}"
    over = [n for n, x in (("pollution degree", pd), ("insulation type", it)) if x is None]
    return worst * factor, ("PROVISIONAL LAYOUT GUIDANCE: worst case over undeclared " + ", ".join(over) if over
                            else "PROVISIONAL LAYOUT GUIDANCE")


# -------------------------------------------------------------------------------------------------------- assessment
@dataclass(frozen=True)
class InsulationAssessment:
    """One insulation (e.g. across a declared barrier): its inputs and the two separate results."""
    inputs: InsulationInputs
    clearance: ClearanceResult
    creepage: CreepageResult
    standard: str
    dataset_id: str
    label: str = ""

    def __post_init__(self):
        if type(self.clearance) is not ClearanceResult:
            raise TypeError("clearance must be a ClearanceResult (creepage and clearance are never interchangeable)")
        if type(self.creepage) is not CreepageResult:
            raise TypeError("creepage must be a CreepageResult (creepage and clearance are never interchangeable)")

    @property
    def status(self) -> Status:
        return _worse(self.clearance.status, self.creepage.status)

    def digest(self) -> str:
        """Content hash an engineering sign-off must quote: inputs, both results and the dataset id."""
        payload = {"inputs": self.inputs.to_dict(), "clearance": self.clearance.to_dict(),
                   "creepage": self.creepage.to_dict(), "dataset_id": self.dataset_id, "standard": self.standard}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def compliance_statement(self, signoff: Any = None) -> str:
        from desk.insulation import signoff as S
        return S.evaluate_signoff(self, signoff)[1]

    def to_dict(self, signoff: Any = None) -> Dict[str, Any]:
        from desk.insulation import signoff as S
        ok, statement = S.evaluate_signoff(self, signoff)
        return {"label": self.label, "standard": self.standard, "dataset_id": self.dataset_id,
                "inputs": self.inputs.to_dict(), "clearance": self.clearance.to_dict(),
                "creepage": self.creepage.to_dict(), "status": self.status.value, "digest": self.digest(),
                "engineering_review_required": not ok, "compliance_statement": statement}

    def summary(self) -> str:
        def one(r: _Result) -> str:
            g = "none" if r.guidance_mm is None else f"{r.guidance_mm:.3g} mm"
            miss = f"; missing {', '.join(r.missing_inputs)}" if r.missing_inputs else ""
            return f"{r.QUANTITY} {r.status.value} (guidance {g}{miss})"
        head = f"INSULATION {self.label}: " if self.label else "INSULATION: "
        return (head + "; ".join([one(self.clearance), one(self.creepage)])
                + f" [{self.standard}, dataset {self.dataset_id}; engineering review required]")


def assess(inputs: InsulationInputs, dataset: Optional[T.Dataset] = None, label: str = "") -> InsulationAssessment:
    ds = dataset or T.load_dataset()
    return InsulationAssessment(inputs=inputs, clearance=evaluate_clearance(inputs, ds),
                                creepage=evaluate_creepage(inputs, ds), standard=ds.standard_label,
                                dataset_id=ds.dataset_id, label=label)


def creepage_value_mm(working_voltage_v: float, pollution_degree: int, material_group: str,
                      insulation_type: str = "basic", dataset: Optional[T.Dataset] = None) -> Optional[float]:
    """The dataset creepage value for fully explicit inputs, or None when the dataset cannot give one. Used by the
    legacy router-rule path (desk/ipc.py, desk/spacing.py), which supplies its own explicit defaults; it reads the
    shipped dataset unless one is passed, so a DESK_INSULATION_DATASET override never moves an existing router rule."""
    ds = dataset or T.default_dataset()
    key = (id(ds), abs(float(working_voltage_v)), int(pollution_degree), str(material_group), str(insulation_type))
    if key in _VALUE_MEMO and _VALUE_MEMO[key][0] is ds:
        return _VALUE_MEMO[key][1]
    table = ds.table("creepage")
    mg = T.normalise_material_group(material_group)
    value: Optional[float] = None
    if table is not None and mg is not None:
        value, *_ = _creepage_value(table, ds, key[1], key[2], mg, InsulationType(key[4].lower()))
    if len(_VALUE_MEMO) > 4096:
        _VALUE_MEMO.clear()
    _VALUE_MEMO[key] = (ds, value)
    return value


_VALUE_MEMO: Dict[Tuple[Any, ...], Tuple[T.Dataset, Optional[float]]] = {}
