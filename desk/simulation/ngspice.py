"""Optional ngspice adapter: runs ngspice as an isolated batch subprocess.

Isolation:
- every run gets its own working directory, a temporary one unless work_dir is given
- ngspice starts with -b (batch) and -n (no .spiceinit from the cwd or home) and stdin closed
- a wall-clock timeout (DESK_SIM_TIMEOUT_S, default 60 s) kills the process
- result files over DESK_SIM_MAX_OUTPUT_MB (default 64) are refused, not parsed, and log reads are capped

DESK generates the control block itself. Each analysis runs between `echo DESK_BEGIN <id>` and
`echo DESK_END <id>` markers and writes an ASCII raw file `<id>.raw`. The log is then classified per
analysis. ngspice exits 0 after an aborted transient and after ignoring a malformed element line. DESK
therefore judges a run by its log, not by the exit code.

`parse_run()` is pure. Tests feed it recorded logs and raw files, so CI needs no ngspice.
This module is imported only when the ngspice engine is requested (desk.simulation.base registry).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from desk import config as deskcfg
from desk.simulation import base as B

LOG_NAME, DECK_NAME = "desk.log", "desk.cir"
MAX_LOG_BYTES = 2 * 1024 * 1024
_PLOTNAMES = {"op": "operating point", "tran": "transient analysis", "ac": "ac analysis"}

_MODEL_ERR = re.compile(r"could not find a valid modelname|unable to find definition of model|unknown model type", re.I)
_NETLIST_ERR = re.compile(r"is not a valid .* instance line|^error on line|unknown subckt|syntax error"
                          r"|not enough nodes|too few parameters|unknown device type", re.I)
_CONV_ERR = re.compile(r"timestep too small|simulation\(s\) aborted|^doanalyses:|transient op failed"
                       r"|iteration limit reached|no convergence|dc solution failed", re.I)
_CONV_WARN = re.compile(r"singular matrix|gmin stepping failed|source stepping failed", re.I)
_MEAS_OK = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_MEAS_FAIL = re.compile(r"^\s*meas\s+\w+\s+([A-Za-z][A-Za-z0-9_]*)\b.*failed", re.I)


# ---- deck ------------------------------------------------------------------------------------
def _n(x: float) -> str:
    return "%.12g" % x


def render_deck(circuit) -> str:
    """SPICE body + the DESK-owned ngspice control block."""
    lines = [circuit.spice_body().rstrip("\n"), ".control", "set filetype=ascii"]
    save = " ".join(circuit.save)
    for a in circuit.analyses:
        aid, t = a["id"], a["type"]
        lines.append(f"echo DESK_BEGIN {aid}")
        if t == "op":
            lines.append("op")
        elif t == "tran":
            cmd = f"tran {_n(a['step'])} {_n(a['stop'])}"
            if "start" in a or "maxstep" in a:
                cmd += f" {_n(a.get('start', 0.0))}"
            if "maxstep" in a:
                cmd += f" {_n(a['maxstep'])}"
            if a.get("uic"):
                cmd += " uic"
            lines.append(cmd)
            if a.get("linearize"):
                lines.append("linearize" + (f" {save}" if save else ""))
        else:
            lines.append(f"ac {a['variation']} {a['points']} {_n(a['fstart'])} {_n(a['fstop'])}")
        lines.append(f"write {aid}.raw" + (f" {save}" if save else ""))
        for m in circuit.measures:
            if m["analysis"] == aid:
                lines.append(f"meas {t} {m['name']} {m['expr']}")
        lines.append(f"echo DESK_END {aid}")
    lines += ["echo DESK_DONE", "quit", ".endc", ".end"]
    return "\n".join(lines) + "\n"


# ---- raw file --------------------------------------------------------------------------------
def parse_raw(text: str) -> Dict[str, Any]:
    """Parse one ngspice ASCII raw plot -> {plotname, flags, variables:[(name,type)], vectors:{name:[...]}, points}."""
    text = text.replace("\r\n", "\n")
    head, sep, body = text.partition("\nValues:\n")
    if not sep:
        raise ValueError("not an ASCII raw file (no 'Values:' section)")
    meta: Dict[str, str] = {}
    variables: List[Tuple[str, str]] = []
    in_vars = False
    for ln in head.splitlines():
        if in_vars:
            parts = ln.split(None, 2)
            if len(parts) >= 3 and parts[0].isdigit():
                variables.append((parts[1], parts[2]))
            continue
        if ln.startswith("Variables:"):
            in_vars = True
            continue
        k, _, v = ln.partition(":")
        meta[k.strip().lower()] = v.strip()
    if not variables:
        raise ValueError("raw file lists no variables")
    complex_ = "complex" in meta.get("flags", "").lower()
    tokens = body.split()
    width = len(variables) + 1
    npts = len(tokens) // width
    vectors: Dict[str, List[Any]] = {name: [] for name, _ in variables}
    try:
        for i in range(npts):
            row = tokens[i * width:(i + 1) * width]
            for (name, _), tok in zip(variables, row[1:]):
                if complex_:
                    re_, _, im = tok.partition(",")
                    vectors[name].append(complex(float(re_), float(im or 0.0)))
                else:
                    vectors[name].append(float(tok))
    except ValueError as e:
        raise ValueError(f"bad value in raw file: {e}")
    for name, typ in variables:   # measurement scalars ngspice may attach to a plot ("notype dims=1")
        if "dims=" in typ:
            vectors.pop(name, None)
    return {"plotname": meta.get("plotname", ""), "flags": meta.get("flags", ""), "points": npts,
            "variables": [v for v in variables if "dims=" not in v[1]], "vectors": vectors}


# ---- log classification ---------------------------------------------------------------------
def _sections(log: str) -> Tuple[List[str], Dict[str, List[str]], bool]:
    pre: List[str] = []
    secs: Dict[str, List[str]] = {}
    cur: Optional[str] = None
    done = False
    for ln in log.splitlines():
        s = ln.strip()
        if s.startswith("DESK_BEGIN "):
            cur = s.split(None, 1)[1]
            secs[cur] = []
        elif s.startswith("DESK_END "):
            cur = None
        elif s == "DESK_DONE":
            done = True
        elif cur is None:
            pre.append(ln)
        else:
            secs[cur].append(ln)
    return pre, secs, done


def _classify_parse_phase(lines: List[str]) -> List[B.Diagnostic]:
    """Lines before the first analysis: the netlist parse. Ignored element lines are errors, never warnings."""
    out: List[B.Diagnostic] = []
    skip = set()
    for i, ln in enumerate(lines):
        if i in skip:
            continue
        s = ln.strip()
        if s.startswith("Circuit:"):      # the echoed title is user text, never a diagnostic
            continue
        if s.lower().startswith("error on line"):
            block = [x.strip() for x in lines[i:i + 3] if x.strip()]
            skip.update(range(i, i + 3))
            cat = B.MODEL_ERROR if any(_MODEL_ERR.search(x) for x in block) else B.NETLIST_ERROR
            out.append(B.Diagnostic(cat, B.ERROR, " | ".join(block)[:300]))
        elif _MODEL_ERR.search(s):
            out.append(B.Diagnostic(B.MODEL_ERROR, B.ERROR, s[:300]))
        elif _NETLIST_ERR.search(s):
            out.append(B.Diagnostic(B.NETLIST_ERROR, B.ERROR, s[:300]))
    if not out and any("simulation interrupted due to error" in x.lower() for x in lines):
        out.append(B.Diagnostic(B.NETLIST_ERROR, B.ERROR, "ngspice interrupted the run while reading the netlist"))
    return out


def _section_measures(res: B.SimulationResult, aid: str, lines: List[str], wanted: Dict[str, Dict[str, str]]) -> None:
    for i, ln in enumerate(lines):
        mf = _MEAS_FAIL.search(ln)
        if mf and mf.group(1).lower() in wanted:
            m = wanted[mf.group(1).lower()]
            why = lines[i - 1].strip() if i > 0 and lines[i - 1].strip().lower().startswith("error") else ln.strip()
            res.measurements[m["name"]] = B.Measurement(m["name"], None, aid, False, why[:200])
            res.diagnostics.append(B.Diagnostic(B.MEASURE_FAILED, B.ERROR, f"measure {m['name']}: {why}"[:300], aid))
            continue
        mo = _MEAS_OK.match(ln)
        if mo and mo.group(1).lower() in wanted and wanted[mo.group(1).lower()]["analysis"] == aid:
            m = wanted[mo.group(1).lower()]
            res.measurements[m["name"]] = B.Measurement(m["name"], float(mo.group(2)), aid, True, ln.strip()[:200])


def parse_run(circuit, log: str, raws: Dict[str, Optional[str]], returncode: Optional[int] = 0,
              engine_version: str = "", elapsed_s: float = 0.0) -> B.SimulationResult:
    """Turn an ngspice log plus per-analysis raw texts into a classified SimulationResult (pure function)."""
    res = B.SimulationResult(engine="ngspice", status=B.COMPLETED, engine_version=engine_version,
                             models=list(circuit.models), excluded=list(circuit.excluded), elapsed_s=elapsed_s)
    pre, secs, done = _sections(log)
    res.diagnostics.extend(_classify_parse_phase(pre))
    parse_failed = bool(res.errors)
    wanted = {m["name"].lower(): m for m in circuit.measures}
    for a in circuit.analyses:
        aid = a["id"]
        ar = B.AnalysisResult(id=aid, type=a["type"], status=B.FAILED)
        res.analyses[aid] = ar
        lines = secs.get(aid)
        if lines is None:
            if not parse_failed:
                res.diagnostics.append(B.Diagnostic(B.NO_OUTPUT, B.ERROR, "analysis never started", aid))
            continue
        stripped = [ln.strip() for ln in lines]
        conv_err = [s for s in stripped if _CONV_ERR.search(s)]
        conv_warn = [s for s in stripped if _CONV_WARN.search(s)]
        if conv_err:
            res.diagnostics.append(B.Diagnostic(B.CONVERGENCE, B.ERROR, "; ".join(dict.fromkeys(conv_err))[:300], aid))
        elif conv_warn:
            res.diagnostics.append(B.Diagnostic(B.CONVERGENCE_ASSISTED, B.WARNING, "converged only after fallbacks: "
                                                + "; ".join(dict.fromkeys(conv_warn))[:250], aid))
        for s in stripped:
            if _NETLIST_ERR.search(s):
                res.diagnostics.append(B.Diagnostic(B.NETLIST_ERROR, B.ERROR, s[:300], aid))
        _section_measures(res, aid, lines, wanted)
        raw = raws.get(aid)
        if raw is None:
            res.diagnostics.append(B.Diagnostic(B.NO_OUTPUT, B.ERROR, "no result file written", aid))
            continue
        try:
            plot = parse_raw(raw)
        except ValueError as e:
            res.diagnostics.append(B.Diagnostic(B.NO_OUTPUT, B.ERROR, f"unreadable result file: {e}", aid))
            continue
        if not plot["plotname"].lower().startswith(_PLOTNAMES[a["type"]]):
            res.diagnostics.append(B.Diagnostic(B.NO_OUTPUT, B.ERROR, f"result file holds '{plot['plotname']}', "
                                                f"not this {a['type']} analysis (it produced no data)", aid))
            continue
        ar.points = plot["points"]
        ar.scale = None if a["type"] == "op" else plot["variables"][0][0]
        ar.vectors = plot["vectors"]
        if ar.points == 0:
            res.diagnostics.append(B.Diagnostic(B.NO_OUTPUT, B.ERROR, "result file has no data points", aid))
        ar.status = B.FAILED if conv_err or ar.points == 0 else B.COMPLETED
    for m in wanted.values():
        if m["name"] not in res.measurements:
            res.measurements[m["name"]] = B.Measurement(m["name"], None, m["analysis"], False, "not reported by ngspice")
            if secs.get(m["analysis"]) is not None:
                res.diagnostics.append(B.Diagnostic(B.MEASURE_FAILED, B.ERROR, f"measure {m['name']} not reported",
                                                    m["analysis"]))
    if not done and not res.errors:
        res.diagnostics.append(B.Diagnostic(B.ENGINE_CRASH, B.ERROR, "ngspice stopped before the end of the control script"))
    if returncode not in (0, None) and not res.errors:
        res.diagnostics.append(B.Diagnostic(B.ENGINE_CRASH, B.ERROR, f"ngspice exited {returncode} without a logged reason"))
    res.status = B.FAILED if res.errors else B.COMPLETED
    res.log_tail = log[-4000:]
    return res


# ---- adapter ---------------------------------------------------------------------------------
def _read_capped(path: str, cap: int) -> Tuple[str, bool]:
    with open(path, "rb") as f:
        data = f.read(cap + 1)
    return data[:cap].decode("utf-8", "replace"), len(data) > cap


class NgspiceSimulator(B.Simulator):
    name = "ngspice"

    def __init__(self, executable: Optional[str] = None):
        self._explicit = executable

    def executable(self) -> Tuple[Optional[str], str]:
        """(path or None, how it was found / why not)."""
        exp = self._explicit or (deskcfg.get("DESK_NGSPICE") or "").strip()
        if exp:
            found = exp if os.path.isfile(exp) else shutil.which(exp)
            return (found, "DESK_NGSPICE") if found else (None, f"DESK_NGSPICE={exp} does not exist")
        names = ["ngspice_con", "ngspice"] if sys.platform == "win32" else ["ngspice"]
        for n in names:
            p = shutil.which(n)
            if p:
                return p, "PATH"
        return None, "ngspice not on PATH (optional; install it or set DESK_NGSPICE to its executable)"

    def probe(self) -> B.EngineInfo:
        exe, how = self.executable()
        if not exe:
            return B.EngineInfo(self.name, False, detail=how)
        try:
            p = subprocess.run([exe, "-v"], capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
            out = (p.stdout or "") + (p.stderr or "")
        except (OSError, subprocess.TimeoutExpired) as e:
            return B.EngineInfo(self.name, False, path=exe, detail=f"cannot run {exe}: {str(e)[:100]}")
        m = re.search(r"ngspice-(\S+)", out)
        if not m:
            return B.EngineInfo(self.name, False, path=exe, detail=f"{exe} -v did not report an ngspice version")
        return B.EngineInfo(self.name, True, version=m.group(1), path=exe, detail=how)

    def run(self, circuit, timeout_s: Optional[float] = None, work_dir: Optional[str] = None) -> B.SimulationResult:
        circuit.require_complete()
        info = self.probe()
        if not info.available:
            r = B.SimulationResult(engine=self.name, status=B.FAILED, models=list(circuit.models),
                                   excluded=list(circuit.excluded))
            r.diagnostics.append(B.Diagnostic(B.ENGINE_NOT_FOUND, B.ERROR, info.detail))
            return r
        timeout = timeout_s or deskcfg.get_float("DESK_SIM_TIMEOUT_S", 60.0) or 60.0
        max_raw = int((deskcfg.get_float("DESK_SIM_MAX_OUTPUT_MB", 64.0) or 64.0) * 1024 * 1024)
        if work_dir:
            os.makedirs(work_dir, exist_ok=True)
            return self._run_in(circuit, info, work_dir, timeout, max_raw)
        with tempfile.TemporaryDirectory(prefix="desk-sim-") as d:
            return self._run_in(circuit, info, d, timeout, max_raw)

    def _run_in(self, circuit, info: B.EngineInfo, d: str, timeout: float, max_raw: int) -> B.SimulationResult:
        with open(os.path.join(d, DECK_NAME), "w", encoding="utf-8", newline="\n") as f:
            f.write(render_deck(circuit))
        t0 = time.perf_counter()
        rc: Optional[int]
        with open(os.path.join(d, "stdout.txt"), "wb") as out:
            try:
                p = subprocess.run([info.path, "-b", "-n", "-o", LOG_NAME, DECK_NAME], cwd=d, stdout=out,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = None
        elapsed = round(time.perf_counter() - t0, 3)
        log_path = os.path.join(d, LOG_NAME)
        log, truncated = _read_capped(log_path, MAX_LOG_BYTES) if os.path.exists(log_path) else ("", False)
        if not log:
            log, _ = _read_capped(os.path.join(d, "stdout.txt"), MAX_LOG_BYTES)
        raws: Dict[str, Optional[str]] = {}
        oversize: List[str] = []
        for a in circuit.analyses:
            rp = os.path.join(d, f"{a['id']}.raw")
            if not os.path.exists(rp):
                raws[a["id"]] = None
            elif os.path.getsize(rp) > max_raw:
                raws[a["id"]] = None
                oversize.append(a["id"])
            else:
                raws[a["id"]] = _read_capped(rp, max_raw)[0]
        res = parse_run(circuit, log, raws, returncode=rc, engine_version=info.version, elapsed_s=elapsed)
        if rc is None:
            res.diagnostics.insert(0, B.Diagnostic(B.TIMEOUT, B.ERROR, f"ngspice killed after {timeout:g} s"))
            res.diagnostics = [x for x in res.diagnostics if x.category != B.ENGINE_CRASH]
        for aid in oversize:
            res.diagnostics = [x for x in res.diagnostics if not (x.analysis == aid and x.category == B.NO_OUTPUT)]
            res.diagnostics.append(B.Diagnostic(B.OUTPUT_TOO_LARGE, B.ERROR,
                                                f"result file exceeds DESK_SIM_MAX_OUTPUT_MB ({max_raw // 1048576} MB); "
                                                "shorten the analysis, coarsen the step or save fewer vectors", aid))
        if truncated:
            res.diagnostics.append(B.Diagnostic(B.OUTPUT_TOO_LARGE, B.WARNING, f"log truncated at {MAX_LOG_BYTES} bytes"))
        res.status = B.FAILED if res.errors else B.COMPLETED
        return res
