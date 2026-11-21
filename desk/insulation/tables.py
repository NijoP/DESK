"""Versioned insulation-coordination datasets: load, validate and look up IEC 60664-1 table data with provenance.

The engine (desk/insulation/engine.py) holds no table values. Every number comes from a JSON dataset that names the
standard edition and carries a provenance record for each value:

    {"status": "PROVISIONAL" | "VERIFIED", "source": "<where the value came from>", "verified_by": "<who checked it>"}

A cell is either a bare number (it takes its column's `provenance`, else the table's `default_provenance`) or an
object {"value": <number>, "provenance": {...}}. A VERIFIED value must name `verified_by`.

Tables a dataset may hold (any may be absent; the engine then returns UNVERIFIED for what depends on it):

    creepage               columns {name: {pollution_degree, material_groups[], rows_v[], values_mm[]}}
                           rows are working voltage, V RMS
    clearance              columns {name: {pollution_degree, rows_v[], values_mm[]}}, plus altitude_basis_m (a cell)
                           rows are rated impulse voltage, V peak
    rated_impulse_voltage  rows_v[] (nominal mains voltage) and columns {"I".."IV": {values_v[]}}
    altitude_correction    rows_m[] and factors[]
    material_group_by_cti  bands [{group, cti_min, cti_max, provenance}]

Rules (any may be absent):

    creepage_reinforced_factor   {value, reference, provenance}
    clearance_reinforced         {method: "impulse_step" | "factor", value (factor only), reference, provenance}

The shipped dataset (data/iec60664-1_2020_a1_2025.provisional.json) holds only values the repository already had,
all PROVISIONAL. The owner supplies a dataset transcribed from the purchased standard with DESK_INSULATION_DATASET
(desk.config) or `load_dataset(path)`; no code change is needed.

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from desk.errors import InsulationDataInvalid

SCHEMA = "desk.insulation.dataset/1"
PROVISIONAL = "PROVISIONAL"
VERIFIED = "VERIFIED"
_PROVENANCE_STATES = (PROVISIONAL, VERIFIED)
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DEFAULT_DATASET_PATH = os.path.join(_DATA_DIR, "iec60664-1_2020_a1_2025.provisional.json")
CONFIG_KEY = "DESK_INSULATION_DATASET"
_TABLES = ("creepage", "clearance", "rated_impulse_voltage", "altitude_correction", "material_group_by_cti")
_RULES = ("creepage_reinforced_factor", "clearance_reinforced")
MATERIAL_GROUPS = ("I", "II", "IIIa", "IIIb")


@dataclass(frozen=True)
class Provenance:
    status: str
    source: str
    verified_by: Optional[str] = None

    @property
    def verified(self) -> bool:
        return self.status == VERIFIED and bool(self.verified_by)

    def to_dict(self) -> Dict[str, Any]:
        return {"status": self.status, "source": self.source, "verified_by": self.verified_by}


@dataclass(frozen=True)
class Cell:
    value: float
    provenance: Provenance


@dataclass(frozen=True)
class Column:
    name: str
    rows: Tuple[float, ...]
    cells: Tuple[Cell, ...]
    pollution_degree: Optional[int] = None
    material_groups: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Lookup:
    """A table lookup: the cell used, the row it sits on and how it was reached."""
    cell: Cell
    row: float
    exact: bool            # the query sat exactly on a row
    below_first: bool      # the query was below the first row, so the first row was used (over-states)


@dataclass(frozen=True)
class Table:
    name: str
    reference: str
    columns: Dict[str, Column]
    extra: Dict[str, Any]


@dataclass(frozen=True)
class Rule:
    name: str
    reference: str
    provenance: Provenance
    value: Optional[float] = None
    method: Optional[str] = None


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    standard_label: str
    edition: str
    amendments: Tuple[str, ...]
    path: str
    tables: Dict[str, Table]
    rules: Dict[str, Rule]

    def table(self, name: str) -> Optional[Table]:
        return self.tables.get(name)

    def rule(self, name: str) -> Optional[Rule]:
        return self.rules.get(name)


def _fail(path: str, where: str, why: str) -> InsulationDataInvalid:
    return InsulationDataInvalid(f"STOP: insulation dataset {path}: {where}: {why}", path=path, where=where,
                                 category="INSULATION_DATA_INVALID")


def _provenance(raw: Any, path: str, where: str) -> Provenance:
    if not isinstance(raw, dict):
        raise _fail(path, where, "provenance must be an object {status, source, verified_by}")
    status = str(raw.get("status", "")).upper()
    source = str(raw.get("source") or "").strip()
    verified_by = raw.get("verified_by")
    if status not in _PROVENANCE_STATES:
        raise _fail(path, where, f"provenance status must be one of {_PROVENANCE_STATES}, got {raw.get('status')!r}")
    if not source:
        raise _fail(path, where, "provenance needs a source")
    if status == VERIFIED and not (isinstance(verified_by, str) and verified_by.strip()):
        raise _fail(path, where, "a VERIFIED value must name verified_by")
    return Provenance(status=status, source=source, verified_by=verified_by if verified_by else None)


def _number(raw: Any, path: str, where: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise _fail(path, where, f"expected a number, got {raw!r}")
    v = float(raw)
    if v != v or v < 0:
        raise _fail(path, where, f"value must be >= 0, got {raw!r}")
    return v


def _cells(raw: Any, default: Optional[Provenance], path: str, where: str) -> Tuple[Cell, ...]:
    if not isinstance(raw, list) or not raw:
        raise _fail(path, where, "values must be a non-empty list")
    out = []
    for i, c in enumerate(raw):
        w = f"{where}[{i}]"
        if isinstance(c, dict):
            prov = _provenance(c.get("provenance"), path, w + ".provenance") if "provenance" in c else default
            value = _number(c.get("value"), path, w + ".value")
        else:
            prov, value = default, _number(c, path, w)
        if prov is None:
            raise _fail(path, w, "value has no provenance (set it on the cell, the column or default_provenance)")
        out.append(Cell(value=value, provenance=prov))
    return tuple(out)


def _ascending(rows: Sequence[float], path: str, where: str) -> None:
    for a, b in zip(rows, rows[1:]):
        if not b > a:
            raise _fail(path, where, "rows must be strictly ascending")


def _non_decreasing(cells: Sequence[Cell], path: str, where: str) -> None:
    for a, b in zip(cells, cells[1:]):
        if b.value < a.value:
            raise _fail(path, where, "values must never decrease as the row increases (a spacing can not shrink "
                                     "with voltage or altitude)")


def _column(name: str, raw: Any, default: Optional[Provenance], path: str, where: str, value_key: str,
            row_key: str = "rows_v", table_rows: Optional[Sequence[float]] = None) -> Column:
    if not isinstance(raw, dict):
        raise _fail(path, where, "column must be an object")
    col_default = _provenance(raw["provenance"], path, where + ".provenance") if "provenance" in raw else default
    if table_rows is None:
        rows = tuple(_number(r, path, f"{where}.{row_key}") for r in (raw.get(row_key) or []))
    else:
        rows = tuple(table_rows)
    if not rows:
        raise _fail(path, where, f"{row_key} must be a non-empty list")
    _ascending(rows, path, f"{where}.{row_key}")
    cells = _cells(raw.get(value_key), col_default, path, f"{where}.{value_key}")
    if len(cells) != len(rows):
        raise _fail(path, where, f"{len(rows)} rows but {len(cells)} values")
    _non_decreasing(cells, path, f"{where}.{value_key}")
    pd = raw.get("pollution_degree")
    if pd is not None and (isinstance(pd, bool) or not isinstance(pd, int) or pd not in (1, 2, 3, 4)):
        raise _fail(path, where, f"pollution_degree must be 1..4, got {pd!r}")
    groups = tuple(str(g) for g in (raw.get("material_groups") or ()))
    for g in groups:
        if g not in MATERIAL_GROUPS:
            raise _fail(path, where, f"material group {g!r} is not one of {MATERIAL_GROUPS}")
    return Column(name=name, rows=rows, cells=cells, pollution_degree=pd, material_groups=groups)


def _table(name: str, raw: Any, path: str) -> Table:
    where = f"tables.{name}"
    if not isinstance(raw, dict):
        raise _fail(path, where, "table must be an object")
    reference = str(raw.get("reference") or "").strip()
    if not reference:
        raise _fail(path, where, "table needs a reference (the table / clause it was transcribed from)")
    default = _provenance(raw["default_provenance"], path, where + ".default_provenance") \
        if "default_provenance" in raw else None
    columns: Dict[str, Column] = {}
    extra: Dict[str, Any] = {}
    if name in ("creepage", "clearance"):
        for cname, craw in (raw.get("columns") or {}).items():
            col = _column(cname, craw, default, path, f"{where}.columns.{cname}", "values_mm")
            if col.pollution_degree is None:
                raise _fail(path, f"{where}.columns.{cname}", "column needs pollution_degree")
            if name == "creepage" and not col.material_groups:
                raise _fail(path, f"{where}.columns.{cname}", "creepage column needs material_groups")
            columns[cname] = col
        if not columns:
            raise _fail(path, where, "table has no columns")
        if name == "clearance" and "altitude_basis_m" in raw:
            extra["altitude_basis_m"] = _cells([raw["altitude_basis_m"]], default, path, where + ".altitude_basis_m")[0]
    elif name == "rated_impulse_voltage":
        rows = tuple(_number(r, path, where + ".rows_v") for r in (raw.get("rows_v") or []))
        for cname, craw in (raw.get("columns") or {}).items():
            if cname not in ("I", "II", "III", "IV"):
                raise _fail(path, f"{where}.columns.{cname}", "overvoltage category must be I, II, III or IV")
            columns[cname] = _column(cname, craw, default, path, f"{where}.columns.{cname}", "values_v", table_rows=rows)
        if not columns:
            raise _fail(path, where, "table has no columns")
    elif name == "altitude_correction":
        columns["factor"] = _column("factor", {"rows_m": raw.get("rows_m"), "factors": raw.get("factors")}, default,
                                    path, where, "factors", row_key="rows_m")
    elif name == "material_group_by_cti":
        bands = []
        for i, b in enumerate(raw.get("bands") or []):
            w = f"{where}.bands[{i}]"
            if not isinstance(b, dict) or b.get("group") not in MATERIAL_GROUPS:
                raise _fail(path, w, f"band needs a group in {MATERIAL_GROUPS}")
            prov = _provenance(b["provenance"], path, w + ".provenance") if "provenance" in b else default
            if prov is None:
                raise _fail(path, w, "band has no provenance")
            lo = _number(b.get("cti_min"), path, w + ".cti_min")
            hi = None if b.get("cti_max") is None else _number(b.get("cti_max"), path, w + ".cti_max")
            bands.append((b["group"], lo, hi, prov))
        if not bands:
            raise _fail(path, where, "table has no bands")
        extra["bands"] = tuple(bands)
    return Table(name=name, reference=reference, columns=columns, extra=extra)


def _rule(name: str, raw: Any, path: str) -> Rule:
    where = f"rules.{name}"
    if not isinstance(raw, dict):
        raise _fail(path, where, "rule must be an object")
    reference = str(raw.get("reference") or "").strip()
    if not reference:
        raise _fail(path, where, "rule needs a reference")
    prov = _provenance(raw.get("provenance"), path, where + ".provenance")
    method = raw.get("method")
    value: Optional[float] = None
    if name == "creepage_reinforced_factor":
        value = _number(raw.get("value"), path, where + ".value")
        if value < 1.0:
            raise _fail(path, where, "a reinforced factor below 1 would make reinforced smaller than basic")
    elif name == "clearance_reinforced":
        if method not in ("impulse_step", "factor"):
            raise _fail(path, where, "method must be 'impulse_step' or 'factor'")
        if method == "factor":
            value = _number(raw.get("value"), path, where + ".value")
            if value < 1.0:
                raise _fail(path, where, "a reinforced factor below 1 would make reinforced smaller than basic")
    return Rule(name=name, reference=reference, provenance=prov, value=value, method=method)


def parse_dataset(data: Any, path: str = "<memory>") -> Dataset:
    """Validate a dataset object (as loaded from JSON). Raises InsulationDataInvalid naming the bad field."""
    if not isinstance(data, dict):
        raise _fail(path, "<root>", "dataset must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise _fail(path, "schema", f"expected {SCHEMA!r}, got {data.get('schema')!r}")
    did = str(data.get("dataset_id") or "").strip()
    if not did:
        raise _fail(path, "dataset_id", "dataset needs an id")
    std = data.get("standard") or {}
    label = str(std.get("label") or "").strip()
    if not label or not str(std.get("edition") or "").strip():
        raise _fail(path, "standard", "dataset must name the standard label and edition")
    tables: Dict[str, Table] = {}
    for name, raw in (data.get("tables") or {}).items():
        if name not in _TABLES:
            raise _fail(path, f"tables.{name}", f"unknown table; known tables are {_TABLES}")
        tables[name] = _table(name, raw, path)
    rules: Dict[str, Rule] = {}
    for name, raw in (data.get("rules") or {}).items():
        if name not in _RULES:
            raise _fail(path, f"rules.{name}", f"unknown rule; known rules are {_RULES}")
        rules[name] = _rule(name, raw, path)
    return Dataset(dataset_id=did, standard_label=label, edition=str(std["edition"]),
                   amendments=tuple(str(a) for a in (std.get("amendments") or ())), path=path,
                   tables=tables, rules=rules)


_CACHE: Dict[Tuple[str, float], Dataset] = {}


def load_dataset(path: Optional[str] = None) -> Dataset:
    """Load a dataset file. With no path: the file named by DESK_INSULATION_DATASET (desk.config), else the shipped
    provisional dataset. Results are cached per (path, mtime)."""
    if path is None:
        from desk import config
        path = config.get(CONFIG_KEY) or DEFAULT_DATASET_PATH
    path = os.path.abspath(path)
    try:
        key = (path, os.path.getmtime(path))
    except OSError as e:
        raise _fail(path, "<file>", f"cannot be read: {e}")
    if key not in _CACHE:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise _fail(path, "<file>", f"cannot be read as JSON: {e}")
        _CACHE[key] = parse_dataset(data, path)
    return _CACHE[key]


_DEFAULT: List[Dataset] = []


def default_dataset() -> Dataset:
    """The provisional dataset shipped with DESK, whatever DESK_INSULATION_DATASET says (loaded once: it is part of
    the installed package and the legacy router-rule path calls it per net pair)."""
    if not _DEFAULT:
        _DEFAULT.append(load_dataset(DEFAULT_DATASET_PATH))
    return _DEFAULT[0]


def lookup_up(column: Column, query: float) -> Optional[Lookup]:
    """The cell at the first row >= query (conservative: never interpolates down). None above the last row."""
    for row, cell in zip(column.rows, column.cells):
        if query <= row + 1e-9:
            return Lookup(cell=cell, row=row, exact=abs(query - row) <= 1e-9,
                          below_first=(row == column.rows[0] and query < row - 1e-9))
    return None


def normalise_material_group(raw: Any) -> Optional[str]:
    """'I', 'II', 'IIIa', 'IIIb' (case-insensitive). 'III' alone means IIIa or IIIb unknown: it becomes IIIb, the
    worse of the two. Anything else returns None."""
    if raw is None:
        return None
    s = str(raw).strip().upper()
    return {"I": "I", "II": "II", "IIIA": "IIIa", "IIIB": "IIIb", "III": "IIIb"}.get(s)


def columns_for(table: Table, pollution_degree: Optional[int] = None,
                material_group: Optional[str] = None) -> List[Column]:
    out = []
    for col in table.columns.values():
        if pollution_degree is not None and col.pollution_degree != pollution_degree:
            continue
        if material_group is not None and col.material_groups and material_group not in col.material_groups:
            continue
        out.append(col)
    return out
