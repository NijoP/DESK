import os, sys, time, json, atexit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk.bridge import ex, guard, load_project, check  # noqa: E402,F401
from desk import spec as S  # noqa: E402,F401

# ---- DESK execution telemetry (local only, .desk_learn/runs.jsonl; disable with DESK_TELEMETRY=0)
# Records tool, subcommand, exit code, duration and output size -> evidence for the learning engine.
if os.environ.get("DESK_TELEMETRY", "1") != "0":
    _t0, _out, _err, _rc = time.time(), [0], [""], [None]

    class _Count:
        def __init__(self, s, store, keep=False): self.s, self.store, self.keep = s, store, keep
        def write(self, x):
            if self.keep: self.store[0] = (self.store[0] + x)[-400:]
            else: self.store[0] += len(x)
            return self.s.write(x)
        def __getattr__(self, n): return getattr(self.s, n)

    sys.stdout, sys.stderr = _Count(sys.stdout, _out), _Count(sys.stderr, _err, keep=True)
    _exit = sys.exit
    def _sys_exit(code=0):
        _rc[0] = code if isinstance(code, int) else 1
        _exit(code)
    sys.exit = _sys_exit

    def _log():
        rc = _rc[0] if _rc[0] is not None else (1 if _err[0].strip() else 0)
        argv = [a for a in sys.argv[1:3] if not a.startswith("--")]
        rec = {"ts": round(_t0), "tool": os.path.basename(sys.argv[0]), "args": argv, "rc": rc,
               "dur_s": round(time.time() - _t0, 2), "out_chars": _out[0], "err_tail": _err[0].strip()[-200:] if rc else ""}
        try:
            d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".desk_learn")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "runs.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(rec) + "\n")
        except OSError:
            pass
    atexit.register(_log)
