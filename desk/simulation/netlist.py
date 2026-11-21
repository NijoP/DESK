"""SPICE netlist generation from a DESK block spec plus a simulation spec.

The block spec (projects/<P>/blocks/NN_ID.json) supplies parts, values and pin->net maps. The simulation
spec supplies what a schematic does not:

    {"ground": ["GND"],                                     # nets tied to SPICE node 0 (default ["GND"])
     "parts": {                                             # per-designator binding (or a "sim" key on the part)
        "R1": {"value": "1k"},                              # R/L/C: value override; pins in numeric order
        "D1": {"element": "D", "model": "DSCH", "terminals": {"A": "2", "K": "1"}},
        "Q1": {"element": "M", "model": "NSW", "terminals": {"D": "1", "G": "2", "S": "3"}},
        "J1": {"exclude": "wire pad, no electrical model"}},
     "models": {"DX": {"kind": "D", "card": ".model DX D(IS=1e-14)"}},   # inline cards: always UNVERIFIED
     "sources": [{"name": "VIN", "kind": "V", "pos": "VIN", "neg": "GND", "dc": 12, "ac": 1},
                 {"name": "VG", "kind": "V", "pos": "G", "neg": "SW", "pulse": [0, 10, 0, 1e-8, 1e-8, 4e-6, 1e-5]}],
     "analyses": [{"type": "op"}, {"type": "tran", "step": 1e-6, "stop": 1e-3, "uic": true},
                  {"type": "ac", "variation": "dec", "points": 20, "fstart": 1, "fstop": 1e6}],
     "measures": [{"name": "vout_avg", "analysis": "tran", "expr": "AVG v({VOUT}) FROM=0.8m TO=1m"}],
     "save": ["v({VOUT})"]}

`{NET}` placeholders in measure expressions and save lists are replaced by the SPICE node of that net.
Supported primitives: R, L, C, D (diode), Q (BJT), M (MOSFET) and X (subcircuit), each with a model card
where needed, plus independent V/I sources. Pin numbers are never guessed. Diodes, transistors and
subcircuits need an explicit terminal->pin map. A part DESK cannot model is reported in
`Circuit.unsupported`, never dropped. `require_complete()` refuses such a circuit until each of those parts
gets a binding or an explicit `exclude` reason.
"""
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from desk.calc import parse_value
from desk.errors import UsageError
from desk.simulation.models import ModelStore, UNVERIFIED

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_EXPR = re.compile(r"^[A-Za-z0-9_()=.+\-*/ ,#]+$")
_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")

TERMINALS = {"R": ("P", "N"), "L": ("P", "N"), "C": ("P", "N"), "D": ("A", "K"),
             "Q": ("C", "B", "E"), "M": ("D", "G", "S", "B")}
MODEL_KINDS = {"D": ("D",), "Q": ("NPN", "PNP"), "M": ("NMOS", "PMOS"), "X": ("SUBCKT",)}
ANALYSES = ("op", "tran", "ac")


class NetlistError(UsageError):
    """The block/sim spec cannot be turned into a valid netlist."""


@dataclass
class Circuit:
    title: str
    elements: List[str] = field(default_factory=list)
    model_cards: Dict[str, str] = field(default_factory=dict)
    models: List[Dict[str, Any]] = field(default_factory=list)      # provenance per model used
    analyses: List[Dict[str, Any]] = field(default_factory=list)
    measures: List[Dict[str, str]] = field(default_factory=list)
    save: List[str] = field(default_factory=list)
    options: Dict[str, float] = field(default_factory=dict)
    node_map: Dict[str, str] = field(default_factory=dict)
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    excluded: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def require_complete(self) -> None:
        if self.unsupported:
            lines = "; ".join(f"{u['ref']}: {u['reason']}" for u in self.unsupported)
            raise NetlistError(f"{len(self.unsupported)} part(s) cannot be simulated and were not excluded: {lines}")
        if not self.analyses:
            raise NetlistError("sim spec has no analyses (op, tran or ac)")

    def spice_body(self) -> str:
        """Engine-neutral SPICE: title, elements, options and model cards. No analysis or control statements."""
        out = [f"* DESK {self.title}"] + self.elements
        if self.options:
            out.append(".options " + " ".join(f"{k}={_num(v)}" for k, v in sorted(self.options.items())))
        out += list(self.model_cards.values())
        return "\n".join(out) + "\n"

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "elements": self.elements, "models": self.models, "analyses": self.analyses,
                "measures": self.measures, "save": self.save, "node_map": self.node_map,
                "unsupported": self.unsupported, "excluded": self.excluded, "warnings": self.warnings}


def _num(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise NetlistError(f"'{x}' is not a number")
    if not math.isfinite(v):
        raise NetlistError(f"'{x}' is not a finite number")
    return "%.12g" % v


def _value(raw: Any) -> Optional[float]:
    """Part value -> float: DESK notation via desk.calc ('4k7', '10uF', '2R2') or plain numbers ('1e-15')."""
    v = parse_value(raw)
    if v is None and raw is not None:
        try:
            v = float(str(raw).strip().split()[0])
        except (ValueError, IndexError):
            return None
    return v


def _pin_key(p: str):
    return (0, int(p), "") if str(p).isdigit() else (1, 0, str(p))


def _element_name(letter: str, ref: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", ref)
    return base if base[:1].upper() == letter else letter + base


class _Nodes:
    """Net name -> SPICE node. Ground nets become node 0; collisions under SPICE's case-folding are errors."""

    def __init__(self, ground: List[str]):
        self.ground = set(ground)
        self.map: Dict[str, str] = {}
        self._owner: Dict[str, str] = {}

    def __call__(self, net: Any) -> str:
        if not net or not isinstance(net, str):
            raise NetlistError(f"bad net name {net!r}")
        if net in self.map:
            return self.map[net]
        if net in self.ground:
            node = "0"
        else:
            node = re.sub(r"[^A-Za-z0-9_]", "_", net).lower()
            if node == "0":
                node = "n_0"
            other = self._owner.get(node)
            if other is not None and other != net:
                raise NetlistError(f"nets '{other}' and '{net}' both map to SPICE node '{node}' (SPICE is case-insensitive)")
            self._owner[node] = net
        self.map[net] = node
        return node

    def expand(self, text: str) -> str:
        def rep(m):
            net = m.group(1)
            if net not in self.map and net not in self.ground:
                raise NetlistError(f"placeholder {{{net}}} names a net that is not in the circuit")
            return self(net)
        return _PLACEHOLDER.sub(rep, text)


def _source_line(s: Dict[str, Any], nodes: _Nodes) -> str:
    kind = str(s.get("kind", "V")).upper()
    if kind not in ("V", "I"):
        raise NetlistError(f"source {s.get('name')}: kind must be V or I")
    name = str(s.get("name", ""))
    if not _NAME.match(name):
        raise NetlistError(f"source name '{name}' must be a letter followed by letters, digits or _")
    parts = [_element_name(kind, name), nodes(s.get("pos")), nodes(s.get("neg", "GND"))]
    if "dc" in s:
        parts += ["DC", _num(s["dc"])]
    if "ac" in s:
        parts += ["AC", _num(s["ac"])]
    shapes = [k for k in ("pulse", "sin", "pwl") if k in s]
    if len(shapes) > 1:
        raise NetlistError(f"source {name}: give at most one of pulse/sin/pwl")
    if shapes:
        k = shapes[0]
        vals = s[k]
        flat = [v for pt in vals for v in pt] if k == "pwl" else list(vals)
        want = {"pulse": (2, 7), "sin": (3, 6), "pwl": (2, 10000)}[k]
        if not (want[0] <= len(flat) <= want[1]):
            raise NetlistError(f"source {name}: {k} takes {want[0]}..{want[1]} numbers, got {len(flat)}")
        parts.append(f"{k.upper()}(" + " ".join(_num(v) for v in flat) + ")")
    if len(parts) == 3:
        raise NetlistError(f"source {name}: give dc, ac, pulse, sin or pwl")
    return " ".join(parts)


def _analysis(a: Dict[str, Any]) -> Dict[str, Any]:
    t = str(a.get("type", "")).lower()
    if t not in ANALYSES:
        raise NetlistError(f"analysis type '{a.get('type')}' not supported (supported: {', '.join(ANALYSES)})")
    out: Dict[str, Any] = {"type": t}
    try:
        if t == "tran":
            out["step"], out["stop"] = float(_num(a["step"])), float(_num(a["stop"]))
            if "start" in a:
                out["start"] = float(_num(a["start"]))
            if "maxstep" in a:
                out["maxstep"] = float(_num(a["maxstep"]))
            out["uic"] = bool(a.get("uic", False))
            out["linearize"] = bool(a.get("linearize", False))
            if out["step"] <= 0 or out["stop"] <= out["step"]:
                raise NetlistError("tran needs 0 < step < stop")
        elif t == "ac":
            var = str(a.get("variation", "dec")).lower()
            if var not in ("dec", "oct", "lin"):
                raise NetlistError("ac variation must be dec, oct or lin")
            out.update(variation=var, points=int(a.get("points", 20)),
                       fstart=float(_num(a["fstart"])), fstop=float(_num(a["fstop"])))
            if out["points"] < 1 or not (0 < out["fstart"] < out["fstop"]):
                raise NetlistError("ac needs points >= 1 and 0 < fstart < fstop")
    except KeyError as e:
        raise NetlistError(f"{t} analysis is missing '{e.args[0]}'")
    return out


def _bind_part(p: Dict[str, Any], b: Dict[str, Any], store: ModelStore, c: Circuit,
               used_models: Dict[str, Dict[str, Any]]):
    """Return (letter, pin order, model) for a part, or a reason string when it cannot be modelled."""
    ref = p.get("ref", "?")
    pins = {str(k): v for k, v in (p.get("pins") or {}).items()}
    prefix = re.match(r"^[A-Za-z]*", ref).group(0).upper()
    letter = str(b.get("element") or (prefix if prefix in ("R", "L", "C") else "")).upper()
    if letter not in ("R", "L", "C", "D", "Q", "M", "X"):
        return (f"no SPICE primitive for '{prefix or ref}' ({p.get('mpn', '')}); "
                "bind it with sim.element/model/terminals or exclude it with a reason")
    model = b.get("model")
    if letter in MODEL_KINDS:
        if not model:
            return f"element {letter} needs sim.model (a card in the model store)"
        rec = store.get(model)
        if rec is None:
            return f"model '{model}' not in the model store"
        if rec.get("kind") not in MODEL_KINDS[letter]:
            return f"model '{model}' is {rec.get('kind')}, element {letter} needs {'/'.join(MODEL_KINDS[letter])}"
    term = b.get("terminals")
    if letter == "X":
        if not isinstance(term, list) or not term:
            return "subcircuit needs sim.terminals as a list of pin numbers in port order"
        order = [str(t) for t in term]
    elif letter in ("R", "L", "C") and not term:
        if len(pins) != 2:
            return f"{letter} needs exactly 2 connected pins (has {len(pins)}) or explicit sim.terminals"
        order = sorted(pins, key=_pin_key)
    else:
        if not isinstance(term, dict):
            return (f"element {letter} needs sim.terminals {{{', '.join(TERMINALS[letter])}: pin}} "
                    "(pin numbers are never guessed)")
        t = {k.upper(): str(v) for k, v in term.items()}
        if letter == "M" and "B" not in t and "S" in t:
            t["B"] = t["S"]
        missing = [k for k in TERMINALS[letter] if k not in t]
        if missing:
            return f"sim.terminals missing {', '.join(missing)}"
        order = [t[k] for k in TERMINALS[letter]]
    absent = [n for n in order if n not in pins]
    if absent:
        return f"terminal pin(s) {', '.join(absent)} not connected in the block spec"
    if letter in MODEL_KINDS:
        used_models[model] = store.get(model)
    dangling = sorted({pins[n] for n in pins if n not in set(order)} - {pins[n] for n in order})
    if dangling:
        c.warnings.append(f"{ref}: pins on nets {', '.join(dangling)} are not part of the SPICE model")
    return letter, [pins[n] for n in order], model


def build_circuit(block: Optional[Dict[str, Any]], spec: Dict[str, Any],
                  store: Optional[ModelStore] = None) -> Circuit:
    block = block or {"parts": []}
    store = store or ModelStore()
    spec = spec or {}
    ground = list(spec.get("ground") or ["GND"])
    nodes = _Nodes(ground)
    c = Circuit(title=re.sub(r"\s+", " ", str(spec.get("title") or block.get("title") or block.get("id") or "circuit"))[:80])
    for name, e in (spec.get("models") or {}).items():
        store.add_inline(name, e.get("kind", "D"), e.get("card", ""), "sim spec inline card")
    bindings = spec.get("parts") or {}
    used_models: Dict[str, Dict[str, Any]] = {}
    names_seen: Dict[str, str] = {}

    for p in block.get("parts", []):
        ref = p.get("ref", "?")
        b = dict(p.get("sim") or {})
        b.update(bindings.get(ref) or {})
        if b.get("exclude"):
            c.excluded.append({"ref": ref, "reason": str(b["exclude"])})
            continue
        bound = _bind_part(p, b, store, c, used_models)
        if isinstance(bound, str):
            c.unsupported.append({"ref": ref, "reason": bound})
            continue
        letter, nets, model = bound
        if letter in ("R", "L", "C"):
            raw = b.get("value", p.get("value"))
            v = _value(raw)
            if v is None or not math.isfinite(v) or v <= 0:
                c.unsupported.append({"ref": ref, "reason": f"value {raw!r} is not a positive number; give sim.value"})
                continue
            tail = _num(v) + (f" IC={_num(b['ic'])}" if letter in ("L", "C") and "ic" in b else "")
        else:
            tail = model
        ename = _element_name(letter, ref)
        if ename.lower() in names_seen:
            raise NetlistError(f"element name {ename} used by {names_seen[ename.lower()]} and {ref}")
        names_seen[ename.lower()] = ref
        c.elements.append(f"{ename} {' '.join(nodes(n) for n in nets)} {tail}")

    for s in spec.get("sources") or []:
        line = _source_line(s, nodes)
        ename = line.split()[0]
        if ename.lower() in names_seen:
            raise NetlistError(f"source name {ename} collides with a part")
        names_seen[ename.lower()] = ename
        c.elements.append(line)

    if c.elements and "0" not in nodes.map.values():
        raise NetlistError(f"no ground reference: none of the nets {ground} is connected (SPICE needs node 0)")

    for k, v in (spec.get("options") or {}).items():
        if not re.match(r"^[a-z][a-z0-9]*$", str(k)):
            raise NetlistError(f"option '{k}' must be lower-case letters and digits")
        c.options[str(k)] = float(_num(v))

    counters: Dict[str, int] = {}
    for a in spec.get("analyses") or []:
        n = _analysis(a)
        counters[n["type"]] = counters.get(n["type"], 0) + 1
        n["id"] = str(a.get("id") or f"{n['type']}{counters[n['type']]}")
        if not _NAME.match(n["id"]) or any(x["id"] == n["id"] for x in c.analyses):
            raise NetlistError(f"analysis id '{n['id']}' must be unique: a letter followed by letters, digits or _")
        c.analyses.append(n)

    ids = {a["id"]: a for a in c.analyses}
    for m in spec.get("measures") or []:
        name = str(m.get("name", ""))
        if not _NAME.match(name):
            raise NetlistError(f"measure name '{name}' must be a letter followed by letters, digits or _")
        ref = str(m.get("analysis", ""))
        target = ids.get(ref)
        if target is None:
            same = [a for a in c.analyses if a["type"] == ref]
            if len(same) != 1:
                raise NetlistError(f"measure {name}: analysis '{ref}' matches {len(same)} analyses; use its id")
            target = same[0]
        if target["type"] == "op":
            raise NetlistError(f"measure {name}: OP values are read directly (verify 'op1:v(node)'), not measured")
        expr = nodes.expand(str(m.get("expr", "")))
        if not expr or not _EXPR.match(expr):
            raise NetlistError(f"measure {name}: expression has characters outside {_EXPR.pattern}")
        c.measures.append({"name": name, "analysis": target["id"], "type": target["type"], "expr": expr})

    for sv in spec.get("save") or []:
        e = nodes.expand(str(sv))
        if not _EXPR.match(e):
            raise NetlistError(f"save entry '{sv}' has characters outside {_EXPR.pattern}")
        c.save.append(e)

    for name, rec in used_models.items():
        c.model_cards[name] = rec["card"].strip()
        c.models.append({"name": name, "kind": rec.get("kind"), "mpn": rec.get("mpn", ""),
                         "status": rec.get("status", UNVERIFIED), "source": rec.get("source") or {}})
    c.node_map = dict(nodes.map)
    return c
