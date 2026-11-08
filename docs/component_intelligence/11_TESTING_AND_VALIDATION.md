# Testing Strategy & Validation Framework

## 1. Test Architecture

The component intelligence test suite is organized into modular unit and integration tests under `tests/`:

1. `tests/test_ci_identity.py`: Manufacturer normalization, MPN standardization, canonical DESK ID hashing, and conflict detection.
2. `tests/test_ci_suppliers.py`: Supplier capabilities, base contract, price break tiers, provider registration, duplicate rejection, and fault isolation.
3. `tests/test_ci_lcsc.py`: LCSC provider, API client, offline fixture search, product detail lookup, and package filters.
4. `tests/test_ci_eda.py`: EDA asset models, local provider offline indexing of `library/devices.json` and `library/pins/`, and EDA registry.
5. `tests/test_ci_storage.py`: SQLite migrations, foreign keys, transactions, component upsert, search, and supplier offer CRUD.
6. `tests/test_ci_verification.py`: V1–V4 verification engine, unit normalization, capacitor 1.5x voltage derating, and stale quote detection.
7. `tests/test_ci_procurement.py`: Multi-supplier BOM procurement, volume pricing, stock shortage, CSV export, and alternatives evaluation.

---

## 2. Validation Metrics & Test Results

```powershell
python -m unittest discover -s tests -p "test_ci_*"
Ran 26 tests in 0.229s - OK
```

- Total Component Intelligence Tests: 26 passing.
- Total Full Repository Tests: 195 passing (0 regressions).
- Execution Time: $<0.25\,\text{s}$.
- Zero external Python dependencies.
