"""Plain data export of simulation results for plotting: CSV per analysis and one JSON document.

No plotting dependency. Every file begins with SAFETY_NOTICE: a `# ` comment line in CSV, which numpy and
pandas skip with comment='#', and a "notice" field in JSON. AC vectors are complex and get four columns
each: <name>.re, <name>.im, <name>.mag and <name>.phase_deg.
"""
import cmath
import csv
import io
import json
import math
import os
from typing import List, Optional

from desk.simulation import base as B


def analysis_csv(ar: B.AnalysisResult) -> str:
    names = list(ar.vectors)
    if ar.scale in names:
        names.remove(ar.scale)
        names.insert(0, ar.scale)
    cplx = {n for n in names if ar.vectors[n] and isinstance(ar.vectors[n][0], complex)}
    header: List[str] = []
    for n in names:
        if n in cplx and n != ar.scale:
            header += [f"{n}.re", f"{n}.im", f"{n}.mag", f"{n}.phase_deg"]
        else:
            header.append(n)
    buf = io.StringIO()
    buf.write(f"# {B.SAFETY_NOTICE}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for i in range(ar.points):
        row: List[str] = []
        for n in names:
            v = ar.vectors[n][i]
            if isinstance(v, complex):
                if n == ar.scale:
                    row.append(repr(v.real))
                else:
                    row += [repr(v.real), repr(v.imag), repr(abs(v)), repr(math.degrees(cmath.phase(v)))]
            else:
                row.append(repr(v))
        w.writerow(row)
    return buf.getvalue()


def write_exports(result: B.SimulationResult, out_dir: str, extra: Optional[dict] = None) -> List[str]:
    """Write result.json and <analysis id>.csv files; returns the paths written."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    doc = result.to_dict()
    if extra:
        doc.update(extra)
    p = os.path.join(out_dir, "result.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    paths.append(p)
    for aid, ar in result.analyses.items():
        if ar.points:
            p = os.path.join(out_dir, f"{aid}.csv")
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(analysis_csv(ar))
            paths.append(p)
    return paths
