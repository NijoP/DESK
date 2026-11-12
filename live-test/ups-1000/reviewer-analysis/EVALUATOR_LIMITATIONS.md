# Evaluator limitations
- No live EasyEDA access: board state (123 components, 0 copper) taken from records and state/*.json, not independently read back.
- Monitoring was interim plus final only, not every 10 min. Timing relies on builder-written timing.json and execution.jsonl, which I could only check for internal consistency.
- Same underlying vendor family as the builder; shared blind spots are possible.
- Did not re-measure pad geometry after the F-008 re-placement; hot-loop and gate-loop improvement is builder-reported.
- Did not rerun routing, DRC, lint or ERC (forbidden); only the offline test suite (721 OK, skipped=9).
- The 349 vs 1 DRC count discrepancy could not be resolved without live access.
- No fresh datasheet re-verification of ratings; relied on DATASHEET_FACTS.md.
- Hash check covered all 71 manifest entries; the 3 mismatches (files larger than recorded) are attributed to logs appended after manifest generation, not proven.
- Stale text in REQUIREMENTS (M2/M4) not re-audited.
