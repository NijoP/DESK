"""Verification of simulation results against expected ranges from the calculation layer.

An expectation names a quantity and an accepted range, with the source of that range:

    {"quantity": "vout_avg", "min": 4.5, "max": 5.2, "unit": "V", "source": "Vout = D*Vin, BLOCK qa 'Vout'"}
    {"quantity": "op1:v({VOUT})", "min": 2.4, "max": 2.6, "unit": "V", "source": "divider R2/(R1+R2)*VIN"}

`quantity` is either a measurement name or `<op analysis id>:<vector>`. `{NET}` is expanded through the
circuit's node map. A block's qa entries become expectations when they carry a "sim" key
(`expectations_from_qa`). The calculated value from desk.calc is then carried along. With
`sim_tolerance` (a relative fraction) the simulated value must also agree with the calculation.

Fail-closed: a missing or failed measurement is a FAIL, a run that did not complete is NOT_RUN, and only
PASS means every check passed, every model is TRACEABLE and the run had no warnings. Every report carries
SAFETY_NOTICE. A PASS here is one piece of evidence, not proof that the board is safe.
"""
import re
from typing import Any, Dict, List, Optional

from desk.errors import UsageError
from desk.simulation import base as B
from desk.simulation.models import TRACEABLE

PASS, FAIL, NOT_RUN, NO_EXPECTATIONS, PASS_WITH_CAVEATS = (
    "PASS", "FAIL", "NOT_RUN", "NO_EXPECTATIONS", "PASS_WITH_CAVEATS")


def normalise(exp: Dict[str, Any]) -> Dict[str, Any]:
    q = str(exp.get("quantity") or "").strip()
    if not q:
        raise UsageError(f"expectation without 'quantity': {exp}")
    if exp.get("min") is None and exp.get("max") is None:
        raise UsageError(f"expectation {q}: give min and/or max")
    if not str(exp.get("source") or "").strip():
        raise UsageError(f"expectation {q}: 'source' (the calculation or datasheet behind the range) is required")
    out = {"quantity": q, "min": exp.get("min"), "max": exp.get("max"), "unit": exp.get("unit", ""),
           "source": str(exp["source"])}
    for k in ("calc_value", "tolerance"):
        if exp.get(k) is not None:
            out[k] = float(exp[k])
    return out


def expectations_from_qa(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    """qa entries with a "sim" key (the quantity to compare) -> expectations, calc value attached when computable."""
    from desk.calc import check_qa
    computed = {item: v for item, v, _ok, _msg in check_qa(block)}
    out = []
    for q in block.get("qa", []):
        if not q.get("sim"):
            continue
        src = str(q.get("source") or "")
        if q.get("expr"):
            src = f"{src}; calc: {q['expr']}" if src else f"calc: {q['expr']}"
        e = {"quantity": q["sim"], "min": q.get("min"), "max": q.get("max"), "unit": q.get("unit", ""),
             "source": src or f"block qa '{q.get('item')}'", "calc_value": computed.get(q.get("item")),
             "tolerance": q.get("sim_tolerance")}
        out.append(normalise(e))
    return out


def _value(result: B.SimulationResult, quantity: str, node_map: Dict[str, str]):
    """(value or None, why-missing)."""
    q = re.sub(r"\{([^{}]+)\}", lambda m: node_map.get(m.group(1), m.group(0)), quantity)
    if ":" in q:
        aid, vec = q.split(":", 1)
        ar = result.analyses.get(aid)
        if ar is None:
            return None, f"no analysis '{aid}'"
        if ar.type != "op":
            return None, f"'{aid}' is a {ar.type} analysis: compare a measure, not a raw vector"
        if ar.status != B.COMPLETED:
            return None, f"analysis {aid} did not complete"
        v = ar.vectors.get(vec.lower(), ar.vectors.get(vec))
        if not v:
            return None, f"vector {vec} not in {aid} (has {', '.join(sorted(ar.vectors))[:120]})"
        return float(v[0].real if isinstance(v[0], complex) else v[0]), ""
    m = result.measurements.get(q)
    if m is None:
        return None, f"no measurement '{q}'"
    if not m.ok or m.value is None:
        return None, f"measurement failed: {m.detail}"
    return m.value, ""


def verify(result: B.SimulationResult, expectations: List[Dict[str, Any]],
           node_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    exps = [normalise(e) for e in expectations]
    checks: List[Dict[str, Any]] = []
    for e in exps:
        v, why = _value(result, e["quantity"], node_map or {})
        c = dict(e, value=v)
        if v is None:
            c.update(status=FAIL, detail=f"MISSING: {why}")
        else:
            lo, hi = e["min"], e["max"]
            ok = (lo is None or v >= lo) and (hi is None or v <= hi)
            detail = f"{v:.6g}{e['unit']} in [{'-inf' if lo is None else lo}, {'inf' if hi is None else hi}]"
            if "calc_value" in e:
                cv = e["calc_value"]
                dev = (v - cv) / abs(cv) if cv else None
                c["deviation_from_calc"] = dev
                detail += f"; calc {cv:.6g}" + (f" (sim deviates {dev * 100:+.1f}%)" if dev is not None else "")
                if "tolerance" in e and dev is not None and abs(dev) > e["tolerance"]:
                    ok = False
                    detail += f", exceeds tolerance {e['tolerance'] * 100:.1f}%"
            c.update(status=PASS if ok else FAIL, detail=("" if ok else "OUT OF RANGE: ") + detail)
        checks.append(c)
    caveats = [f"model {m['name']} is {m.get('status')} (source: {(m.get('source') or {}).get('type', 'none')})"
               for m in result.models if m.get("status") != TRACEABLE]
    caveats += [f"{d.category}: {d.message}" for d in result.diagnostics if d.severity == B.WARNING]
    caveats += [f"part {x['ref']} excluded: {x['reason']}" for x in result.excluded]
    # A failed measurement is a verification failure; any other error means the simulation itself did not run.
    if any(d.category != B.MEASURE_FAILED for d in result.errors):
        verdict = NOT_RUN
    elif result.errors or any(c["status"] != PASS for c in checks):
        verdict = FAIL
    elif not checks:
        verdict = NO_EXPECTATIONS
    elif caveats:
        verdict = PASS_WITH_CAVEATS
    else:
        verdict = PASS
    return {"verdict": verdict, "checks": checks, "caveats": caveats,
            "errors": [d.to_dict() for d in result.errors], "notice": B.SAFETY_NOTICE}


def render(report: Dict[str, Any]) -> str:
    lines = [f"SIMULATION VERIFICATION: {report['verdict']}"]
    for c in report["checks"]:
        lines.append(f"  [{c['status']:4}] {c['quantity']:<28} {c['detail']}  <- {c['source']}")
    for e in report["errors"]:
        lines.append(f"  [ERR ] {e['category']}: {e['message']}")
    for cv in report["caveats"]:
        lines.append(f"  caveat: {cv}")
    lines.append("NOTE: " + report["notice"])
    return "\n".join(lines)
