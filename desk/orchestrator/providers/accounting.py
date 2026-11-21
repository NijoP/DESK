"""Token and cost accounting for model calls.

Every attempt (success or failure) is one ledger row. Cost is computed only from prices the
catalog actually holds; a call whose price is unknown is counted as unpriced, never as free.
Token counts a provider did not report are estimated (4 chars/token) and flagged `estimated`.

Row (JSON lines when a path is given, timestamps ISO-8601 UTC):
    {"ts": "2026-11-21T10:00:00Z", "provider": "nvidia", "model": "...", "input_tokens": 120,
     "output_tokens": 30, "estimated": false, "cost_usd": null, "latency_ms": 850.0, "ok": true,
     "via": "native", "attempt": 1, "error": null}

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from desk.orchestrator.providers.base import ModelRoute, Usage
from desk.orchestrator.providers.catalog import ModelDescriptor, cost_usd


class UsageLedger:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.rows: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(self, route: ModelRoute, desc: Optional[ModelDescriptor], usage: Optional[Usage], latency_ms: float,
               ok: bool, via: str = "native", attempt: int = 1, error: Optional[str] = None) -> Dict[str, Any]:
        u = usage or Usage()
        cost = cost_usd(desc, u.input_tokens, u.output_tokens) if (desc is not None and ok) else None
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "provider": route.provider, "model": route.model,
               "input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "estimated": u.estimated,
               "cost_usd": cost, "latency_ms": round(latency_ms, 2), "ok": ok, "via": via, "attempt": attempt,
               "error": error}
        with self._lock:
            self.rows.append(row)
            if self.path:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                except OSError:
                    pass   # accounting must never break a model call; the row stays in memory
        return row

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            rows = list(self.rows)
        ok = [r for r in rows if r["ok"]]
        priced = [r for r in ok if r["cost_usd"] is not None]
        by_route: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            b = by_route.setdefault(f"{r['provider']}:{r['model']}",
                                    {"calls": 0, "failures": 0, "input_tokens": 0, "output_tokens": 0})
            b["calls"] += 1
            b["failures"] += 0 if r["ok"] else 1
            b["input_tokens"] += r["input_tokens"]
            b["output_tokens"] += r["output_tokens"]
        return {"calls": len(rows), "failures": len(rows) - len(ok),
                "input_tokens": sum(r["input_tokens"] for r in ok), "output_tokens": sum(r["output_tokens"] for r in ok),
                "estimated_calls": sum(1 for r in ok if r["estimated"]),
                "cost_usd_priced": round(sum(r["cost_usd"] for r in priced), 6), "unpriced_calls": len(ok) - len(priced),
                "by_route": by_route}
