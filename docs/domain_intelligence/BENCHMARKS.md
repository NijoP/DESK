# DDIS benchmarks (measured 2026-11-12, Windows 11, Python 3.11.9, warm disk)

Script: a scratch benchmark calling the public API (`desk.domain_intelligence.api`, `registry`, `rule_composer`, `rule_engine`); numbers are medians of 10 to 20 runs unless stated. Nothing here is a target; these are the values obtained on this machine.

| Measure | Value |
|---|---|
| `import desk.domain_intelligence` (first import, incl. desk.profile) | 51 ms |
| taxonomy index load | 1.4 ms |
| cold load of all 100 archetype files | 33.6 ms |
| warm iteration over 100 archetypes (mtime checks only) | 9.8 ms |
| rules (66) + families (206) + overlays (17) + references (46) load | 15.6 ms |
| full library validation (`domains check`) | 48 ms |
| classification, warm median / first call | 19.6 ms / 277 ms |
| rule composition (31 rules for the BLDC controller) | 3.0 ms |
| rule evaluation (31 rules) | 0.14 ms |
| `validate_requirements` end to end (classify + compose + compile + evaluate) | 28.8 ms |
| composition with a 6x larger library (396 rules) | 11.4 ms |
| peak memory of the whole library in process | 5.1 MB |
| agent context for one archetype | 2,496 chars, about 620 tokens |
| whole library serialised (what an agent would load without the context API) | 450 k chars, about 112 k tokens |

Test suite after DDIS: 549 tests in 27.9 s, 0 failures, 3 live-only skips (74 new tests in nine files).

Interpretation: the agent context API is roughly 180x smaller than loading the library; classification is dominated by regex compilation on the first call and by the 100 per-archetype scorers afterwards. Memory is file-backed and bounded; the mtime cache re-reads only changed files.
