"""Deterministic engineering calculations for block QA. The model writes the formula; DESK computes and judges it.

qa entry with an expression:
  {"item":"Vout","expr":"0.6*(1+R1/R2)","unit":"V","min":3.0,"max":3.6,"source":"TPS61023 ds p.9 eq.1"}
- Part designators in `expr` evaluate to the part's `value` ("562k" -> 562000, "4.7uF" -> 4.7e-6, "2R2" -> 2.2).
- Extra named inputs: "vars": {"VIN_MAX": 5.5}
- Allowed: + - * / ** ( ), min max abs sqrt log log10 exp pi.
- Result is judged against min/max; a hand-written `pass` that disagrees is an ERROR (lint)."""
import ast, math, re, operator

SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1, "r": 1}
_NUM = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([pnuµmkKMGRr]?)([0-9]*)\s*([A-Za-zΩ]*)\s*$")


def parse_value(text):
    """'4.7uF' -> 4.7e-6, '2R2' -> 2.2, '562k' -> 562000, '1M' -> 1e6, '0R' -> 0, '10' -> 10. None if not numeric."""
    if text is None: return None
    if isinstance(text, (int, float)): return float(text)
    t = str(text).strip().split()[0] if str(text).strip() else ""
    m = _NUM.match(t)
    if not m: return None
    num, pre, frac, _unit = m.groups()
    if pre and frac:                          # 2R2, 4k7
        num = f"{num}.{frac}"
    elif frac:
        return None
    return float(num) * SI.get(pre, 1) if pre else float(num)


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUN = {"min": min, "max": max, "abs": abs, "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp}


def evaluate(expr, names):
    def ev(n):
        if isinstance(n, ast.Expression): return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)): return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS: return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS: return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name):
            if n.id == "pi": return math.pi
            if n.id not in names: raise ValueError(f"unknown name '{n.id}'")
            if names[n.id] is None: raise ValueError(f"'{n.id}' has no numeric value")
            return names[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUN and not n.keywords:
            return _FUN[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"unsupported expression element: {ast.dump(n)[:60]}")
    return ev(ast.parse(expr, mode="eval"))


def check_qa(block):
    """Return list of (qa_item, computed_or_None, ok_bool_or_None, message)."""
    names = {p["ref"]: parse_value(p.get("value")) for p in block.get("parts", [])}
    out = []
    for q in block.get("qa", []):
        if "expr" not in q:
            continue
        local = dict(names); local.update({k: float(v) for k, v in q.get("vars", {}).items()})
        try:
            v = evaluate(q["expr"], local)
        except (ValueError, ZeroDivisionError, SyntaxError, TypeError) as e:
            out.append((q.get("item"), None, False, f"cannot evaluate '{q['expr']}': {e}")); continue
        lo, hi = q.get("min"), q.get("max")
        ok = (lo is None or v >= lo) and (hi is None or v <= hi)
        unit = q.get("unit", "")
        msg = f"{q.get('item')} = {v:.4g}{unit} (limits {lo if lo is not None else '-inf'}..{hi if hi is not None else 'inf'})"
        if lo is None and hi is None: ok, msg = False, msg + " has no min/max limit"
        out.append((q.get("item"), v, ok, msg))
    return out
