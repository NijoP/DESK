"""Incident learning for the reliability layer: failures become structured incidents in the EXISTING learning system.

* `IncidentWriter.write(record)` renders a FailureRecord as `learning/incidents/INC-YYYYMMDD-NNN.md` following
  learning/INCIDENT_TEMPLATE.md (what happened, expected, actual, root cause, evidence, confidence, recovery, whether it
  worked, regression test, prevention rule, related incidents) and appends one line to learning/index/INCIDENT_INDEX.md.
* `RecoveryOutcomes` keeps `learning/index/RECOVERY_OUTCOMES.jsonl`: which action worked or failed for which failure
  signature. A failed recovery is not proposed again for that signature without new evidence; a successful one is a
  reusable capability (the planner reads it through `successful_kinds`).
* `promote_known_failure(records)` promotes a pattern to a CONFIRMED known failure only when at least `min_sessions`
  independent sessions produced the same signature with a CONFIRMED or STRONGLY_SUPPORTED deterministic root cause. It
  appends to learning/index/KNOWN_FAILURES.md (append-only) and registers the signature at run time. Model-generated
  explanations are never promoted.

Zero external dependencies.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

from desk.reliability.models import Confidence as K, FailureRecord, redact
from desk.reliability import registry as KF


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class IncidentWriter:
    def __init__(self, root: Optional[str] = None, now: Any = time.time):
        self.root = root or _repo_root()
        self.inc_dir = os.path.join(self.root, "learning", "incidents")
        self.index = os.path.join(self.root, "learning", "index", "INCIDENT_INDEX.md")
        self.now = now

    def next_id(self) -> str:
        day = time.strftime("%Y%m%d", time.localtime(self.now()))
        os.makedirs(self.inc_dir, exist_ok=True)
        used = []
        for fn in os.listdir(self.inc_dir):
            m = re.match(rf"INC-{day}-(\d{{3}})\.md$", fn)
            if m:
                used.append(int(m.group(1)))
        return f"INC-{day}-{(max(used) + 1 if used else 1):03d}"

    def render(self, rec: FailureRecord, incident_id: str, regression_test: str = "", prevention: str = "") -> str:
        rc = rec.root_cause
        ev_lines = "\n".join(f"- `{e.id}` {e.kind} `{e.source}`: {e.summary}" for e in rec.evidence) or "- none collected"
        attempts = "\n".join(f"| {i + 1} | {o.action_id} | {o.result}{' (verified)' if o.verified else ''} {o.note} |"
                             for i, o in enumerate(rec.outcomes)) or "| 1 | none | - |"
        plan = rec.plan
        plan_lines = "\n".join(f"- {a.kind} [{a.risk.value}]: {a.description}" for a in (plan.actions if plan else [])) or "- none"
        verification = rec.verification.to_dict() if rec.verification else None
        related = ", ".join(rec.related_incidents) or "N/A"
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(rec.ts))
        return f"""# {incident_id}: {rec.category.value} in {rec.module}.{rec.operation}

## Metadata
- **Date/Time:** {when}
- **Project/Task:** {rec.project_id or '?'} ({rec.operation})
- **Subsystem:** {rec.module}
- **Severity:** {'HIGH' if rec.category.value.startswith(('ROUTER', 'API', 'UNKNOWN_MUTATION', 'PARTIAL')) else 'MEDIUM'}
- **Status:** {'VERIFIED' if rec.healed else rec.status}
- **Failure record:** `{rec.failure_id}` (signature `{rec.signature}`)
- **Identity:** project uuid `{rec.project_uuid or '?'}`, document `{rec.document_uuid or '?'}`, window `{rec.window_id or '?'}`, session `{rec.session_id or '?'}`

## Context
Operation `{rec.operation}` in `{rec.module}` (execution state {rec.execution_state.value}).
Engine/API version: {rec.engine_version or rec.api_version or 'n/a'}. Command: `{' '.join(rec.command)[:200] or 'n/a'}`.

## Expected Behaviour
The operation completes and an independent readback proves its postcondition.

## Actual Behaviour
{rec.message}

## Error Evidence
{ev_lines}

Before-state fingerprint `{rec.before_fingerprint or '-'}`, after-state `{rec.after_fingerprint or '-'}`.

## Root Cause Analysis
### Identified Cause
{(rc.statement if rc else 'UNKNOWN: no hypothesis survived')}

- **Category:** {(rc.category.value if rc else rec.category.value)}
- **Confidence:** {(rc.confidence.value if rc else 'UNVERIFIED')} (source: {(rc.source if rc else '-')})
- **Evidence cited:** {', '.join(rc.evidence_ids) if rc and rc.evidence_ids else 'none'}
- **Alternatives:** {'; '.join(rc.alternatives) if rc and rc.alternatives else 'none recorded'}
- **Missing evidence:** {'; '.join(rc.missing_evidence) if rc and rc.missing_evidence else 'none'}

### Classification
- [{'x' if rec.category.value in ('API_FALSE_SUCCESS', 'API_SCHEMA_MISMATCH') else ' '}] API incompatibility
- [{'x' if rec.category.value.startswith('ROUTER') or rec.category.value == 'EXTERNAL_TOOL_UNSUPPORTED' else ' '}] Implementation defect / tool limitation
- [{'x' if rec.category.value in ('DESIGN_PROFILE_INVALID', 'REQUIREMENT_CONFLICT') else ' '}] Engineering input
- [{'x' if rec.category.value in ('TRANSIENT_NETWORK', 'API_UNAVAILABLE', 'WINDOW_ID_ROTATED', 'WINDOW_DISCONNECTED') else ' '}] Environmental problem
- [{'x' if rec.category.value in ('RESOURCE_LIMIT', 'ROUTER_RESOURCE_EXHAUSTION') else ' '}] Resource/performance limitation
- [{'x' if not rc or rc.confidence in (K.UNVERIFIED,) else ' '}] Unknown cause (hypothesis recorded above)

## Recovery
### Plan
{plan_lines}

### Attempts Made
| Attempt | Action | Result |
|---------|--------|--------|
{attempts}

### Verification Evidence
{json.dumps(redact(verification), indent=1) if verification else 'No independent verification was performed; the failure is NOT healed.'}

### Recovery worked?
{'YES: independent verification passed after an executed recovery.' if rec.healed else 'NO or NOT YET: ' + rec.status}

## Prevention Strategy
### Regression test
{regression_test or 'none yet'}

### Preventive Rule/Procedure
{prevention or '(to be written when the pattern is confirmed across sessions)'}

## Cross-References
- **Related Incidents:** {related}
- **Known Failure Pattern:** {', '.join(k.id for k in KF.match(rec)) or 'N/A'}

## Changelog
- {time.strftime('%Y-%m-%d', time.localtime(self.now()))}: Incident created by desk.reliability (failure `{rec.failure_id}`)
"""

    def write(self, rec: FailureRecord, regression_test: str = "", prevention: str = "") -> str:
        incident_id = self.next_id()
        path = os.path.join(self.inc_dir, incident_id + ".md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render(rec, incident_id, regression_test, prevention))
        rec.related_incidents.append(incident_id)
        self._index(incident_id, rec)
        return path

    def _index(self, incident_id: str, rec: FailureRecord) -> None:
        os.makedirs(os.path.dirname(self.index), exist_ok=True)
        line = (f"- [{incident_id}](../incidents/{incident_id}.md) {rec.category.value} in {rec.module}.{rec.operation}: "
                f"{rec.message[:90].replace(chr(10), ' ')} ({'VERIFIED' if rec.healed else rec.status})\n")
        with open(self.index, "a", encoding="utf-8") as f:
            f.write(line)


class RecoveryOutcomes:
    """Append-only record of recovery results per failure signature."""

    def __init__(self, root: Optional[str] = None):
        self.root = root or _repo_root()
        self.path = os.path.join(self.root, "learning", "index", "RECOVERY_OUTCOMES.jsonl")

    def record(self, rec: FailureRecord) -> None:
        if not rec.outcomes:
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        kinds = {a.id: a.kind for a in (rec.plan.actions if rec.plan else [])}
        with open(self.path, "a", encoding="utf-8") as f:
            for o in rec.outcomes:
                if not o.executed:
                    continue
                f.write(json.dumps({"ts": time.time(), "signature": rec.signature, "category": rec.category.value, "kind": kinds.get(o.action_id, "?"),
                                    "result": o.result, "verified": o.verified, "failure_id": rec.failure_id, "session_id": rec.session_id}) + "\n")

    def _rows(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out

    def failed_kinds(self, signature: str) -> List[str]:
        return sorted({r["kind"] for r in self._rows() if r.get("signature") == signature and r.get("result") == "FAILED"})

    def successful_kinds(self, signature: str) -> List[str]:
        return sorted({r["kind"] for r in self._rows() if r.get("signature") == signature and r.get("verified")})


def promote_known_failure(records: Sequence[FailureRecord], root: Optional[str] = None, min_sessions: int = 2,
                          write_index: bool = True) -> Optional[KF.KnownFailure]:
    """Promote one signature to a CONFIRMED known failure when >= `min_sessions` distinct sessions reproduced it with a
    deterministic root cause at CONFIRMED or STRONGLY_SUPPORTED confidence. Returns the entry or None."""
    if not records:
        return None
    sig = records[0].signature
    same = [r for r in records if r.signature == sig]
    sessions = {r.session_id for r in same if r.session_id}
    strong = [r for r in same if r.root_cause and r.root_cause.source == "deterministic"
              and r.root_cause.confidence in (K.CONFIRMED, K.STRONGLY_SUPPORTED)]
    if len(sessions) < min_sessions or len(strong) < min_sessions:
        return None
    rc = strong[0].root_cause
    worked = sorted({(a.kind) for r in strong for o in r.outcomes if o.verified for a in (r.plan.actions if r.plan else []) if a.id == o.action_id})
    kf_id = "KF-" + time.strftime("%Y%m%d") + "-" + sig.split("|")[0][:12] + "-" + __import__("hashlib").sha1(sig.encode()).hexdigest()[:4]
    entry = KF.KnownFailure(kf_id, f"{rc.category.value}: {rc.statement[:80]}", (rc.category,),
                            re.escape(strong[0].message[:60]) or ".", rc.statement, tuple(worked), K.CONFIRMED,
                            tuple(sorted(r.failure_id for r in strong)) + tuple(sorted({i for r in strong for i in r.related_incidents})),
                            prevention="")
    KF.register(entry)
    if write_index:
        root = root or _repo_root()
        path = os.path.join(root, "learning", "index", "KNOWN_FAILURES.md")
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n### {kf_id}: {entry.title}\n- **Category:** {rc.category.value}\n- **Cause:** {rc.statement}\n"
                        f"- **Evidence:** {', '.join(entry.evidence)} ({len(sessions)} sessions)\n"
                        f"- **Recovery that worked:** {', '.join(worked) or 'none verified yet'}\n- **Confidence:** CONFIRMED (promoted by desk.reliability.learning)\n")
        except OSError:
            pass
    return entry
