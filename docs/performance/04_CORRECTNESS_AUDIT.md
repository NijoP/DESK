# 04 — Correctness, Evidence Integrity, and Mutation Safety Audit

This audit evaluates the reliability, deterministic safety, and evidence models of DESK.

---

## 1. Quality-Gate Defaults & Evidence Model Audit

### A. Current Implementation Analysis (`desk/quality.py`)
- **Previous Vulnerability**: `HardAcceptanceGates` defaulted to `True` on all fields (`zero_shorts=True`, etc.). A caller omitting evidence would implicitly pass gates.
- **Sprint Remediation**: All 8 hard acceptance gates were converted to default `False`. Explicit validation checks set them to `True` only upon positive evidence.
- **Identified Gap**: Evidence is currently binary (`bool`) or list-based. There is no formal representation for intermediate verification lifecycles.
- **Mandatory Improvement**: Implement a formal 5-state lifecycle for every gate:
  - `PASS`: Explicit verified evidence confirms zero violations.
  - `FAIL`: Violation identified and confirmed.
  - `UNKNOWN`: Evidence is missing, corrupted, or inconclusive.
  - `NOT_RUN`: The verification stage has not been executed.
  - `STALE`: The verification evidence was computed against an outdated revision or superseded design profile.
- **Hard Rule**: `UNKNOWN`, `NOT_RUN`, and `STALE` must fail-closed and block manufacturing approval.

---

## 2. PCB Snapshot & Fingerprint Completeness Audit

### A. Fingerprint Scope (`desk/snapshot.py`)
- **Current State**: `_compute_fingerprint()` currently evaluates only:
  - Component designator (`ref`)
  - Centroid coordinates (`x`, `y`)
  - Rotation (`rot`)
  - Placement layer (`layer`)
  - Pad numbers and assigned net names
- **Missing State Elements**:
  - Track geometry (start, end, width, layer)
  - Via geometry (position, drill diameter, outer diameter, net)
  - Copper zones and poured regions (points, priority, connection rule)
  - Board outline and mechanical keepouts
  - Layer stackup and copper thickness
  - Net classes, differential pair definitions, and design rules
- **Risk**: An engineer modifying a track width, moving a via, or altering the layer stackup would NOT change the fingerprint under the current implementation. Caches could erroneously serve stale analysis.
- **Remediation**: Build a comprehensive composite snapshot fingerprint with domain-specific revision tracking.

---

## 3. Mutation Safety & Cross-Process Writer Integrity Audit

### A. Lock Management (`desk/ops.py`)
- **Current State**: `write_op()` checks if `projects/<P>/state/write.lock` exists. If not, it writes `json.dump(...)`.
- **Race Condition Vulnerability**: In concurrent Python processes or multi-agent runs, two processes checking `os.path.exists(lock)` simultaneously can both proceed to write, violating single-writer mutual exclusion.
- **Remediation**: Use atomic file creation (`os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`) to guarantee kernel-enforced mutual exclusion across processes.
- **Process Liveness**: Currently, locks only expire if `time.time() - ts > LOCK_TTL (1800s)`. If a process crashes after 10 seconds, the workspace remains locked for 30 minutes unless `--force-unlock` is used. A true PID liveness check (`os.kill(pid, 0)` on Unix, `OpenProcess` / `GetExitCodeProcess` on Windows) must automatically detect dead processes.

### B. Operation Lifecycle & Idempotence
- **Classifications Needed**:
  - `READ_ONLY`: Safe to execute concurrently.
  - `IDEMPOTENT_MUTATION`: Can be retried safely after verification.
  - `NON_IDEMPOTENT_MUTATION`: Requires explicit readback reconciliation before any retry.
  - `VALIDATION`: Mandatory gate check; must never be skipped or bypassed.

---

## 4. Engineering Profile & Electrical Trace-Width Audit

### A. IPC-2152 & Copper Weight Accuracy (`desk/profile.py`, `desk/router.py`)
- **Current State**:
  - `derive_trace_width_mil(net, is_inner, layer_idx)` checks `self.rf_lines` and `self.net_classes`.
  - Copper thickness is resolved from `self.stackup` using `layer_idx`.
- **Audit Finding**:
  - If a net class specifies a `min_width_mil` that is electrically insufficient for the net's maximum current limit, the net class previously took precedence.
  - **Correction**: The derived width must be $\max(\text{net\_class.min\_width}, \text{IPC\_2152\_width}, \text{mfg.min\_trace\_width})$. Sizing must never be compromised.
