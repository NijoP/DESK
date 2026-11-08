# DESK Rework Mode: Testing & Verification Guide

**Document ID:** `docs/rework/15_TESTING_AND_VALIDATION.md`  

---

## 1. Automated Test Suite

Rework Mode is protected by 25 dedicated unit and end-to-end integration tests:

```bash
# Run all Rework Mode unit and integration tests
python -m unittest discover -s tests -p "test_rework_*.py"
```

### Test Coverage
- `test_rework_session.py`: Natural language intent recognition, state transitions, atomic persistence, multi-project isolation.
- `test_rework_connection.py`: Project binding, window identification, offline mock handling, mismatch detection.
- `test_rework_baseline.py`: Snapshot extraction, multi-domain fingerprints, external modification detection.
- `test_rework_audit.py`: 8-domain engineering audit, issue schema, severity categorization.
- `test_rework_planner.py`: Dependency graph analysis, surgical action sequencing, approval token binding.
- `test_rework_executor.py`: Single-writer lock, checkpointing, readback verification, transaction history.
- `test_rework_readiness.py`: 8 hard gates evaluation, fail-closed outcomes, report generation.
- `test_rework_e2e.py`: Scenarios A through H from Master Directive Section 22.7.

---

## 2. Full Regression Standard

```bash
# Run full suite (303 tests)
python -m unittest discover -s tests
```
Must pass with 0 failures and 0 errors under 100% Python standard library.
