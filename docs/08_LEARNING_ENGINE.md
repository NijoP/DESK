# 08 — Learning Engine

DESK learns from **what actually happened**: agent sessions (Claude Code, Codex, OpenCode, Pi, Cursor, Grok, Hermes)
plus DESK's own execution evidence (tool telemetry, op journal, ledger). It finds recurring mistakes, token waste,
unnecessary calls, slow or failing workflows, and proposes improvements — which a human accepts or rejects.

```
python tools/learn.py setup      # once: clone Backpass at the pinned commit (library/tools/BACKPASS_PIN)
python tools/learn.py run        # collect -> detect -> corroborate -> propose -> report   (read-only, ~2 s)
python tools/learn.py show P8527be
python tools/learn.py accept P8527be --reviewer "your name"      # or: reject ... --reason "..."
python tools/learn.py bench      # replay measured waste against the current DESK tools
```

## Relationship to Backpass (MIT, © Kun Chen)
| Backpass capability | DESK use |
|---|---|
| 8 harness adapters (transcript discovery + parsing, incl. SQLite stores) | **reused as-is** through `desk/learn/collect.mjs`; DESK has no transcript parser of its own |
| secret redaction (`redact.js`) | **reused** on every text/input/result before it is stored |
| evidence-only claims, ≥ 2 distinct sessions, persistent gap ledger, remembered rejections, token budget, human gate, one writer | **same principles, re-implemented** for DESK targets (small, deterministic) |
| model-driven distill / synthesis via `acpx` | **not used**: DESK detection is deterministic, no model calls, so transcripts never leave the machine and results are reproducible |
Backpass is cloned (not vendored) to `library/tools/backpass` at a pinned commit; its MIT license travels with it.
Backpass officially supports macOS/Linux; on this Windows machine all 8 adapters ran without error (verified).

## Pipeline
1. **Collect** — adapters enumerate every harness store; a session is kept if its cwd is under a configured root
   (default: the DESK repo) or any tool call uses DESK tools / the EasyEDA bridge. Incremental: `known.json` stores
   mtime+size per session; unchanged sessions are skipped. Results keep head+tail (errors are at the tail); sizes are
   measured before truncation.
2. **Detect** (deterministic, `desk/learn/engine.py: detect`) — per tool call:
   `large_output` (≥ 4000 tokens), `reference_read` (whole API reference/skill docs), `repeated_call` (identical call,
   identical result), `failure` (error status, or error text at the tail of *command* output — file contents never count),
   `retry_loop` (≥ 3 failures of the same command), `eda_api_failure`, `context_bypass` (whole DESK docs/specs read),
   `rule_violation` (own drawing JS — only in sessions after DESK's first commit: earlier sessions could not know the rule).
   DESK evidence: `tool_failure_rate`, oversized tool output (`runs.jsonl`), dirty write failures (`ops.jsonl`).
3. **Corroborate** — `gaps.json` accumulates per signature across runs; one session counts once (idempotent per event);
   every entry keeps verbatim redacted quotes with session key, model and event index.
4. **Propose** — a gap becomes a proposal only with ≥ 2 distinct sessions (floor enforced in code; config cannot lower it),
   or DESK log evidence for tool-level signals. Ranked by measured tokens and severity. A rejected proposal is not shown
   again until it gains new sessions (then flagged `reproposed_after_reject`).
5. **Human gate / apply** — `accept` requires `--reviewer`. Only two surfaces can be edited, each inside a marked section:
   `AGENTS.md` (+ mirrored `CLAUDE.md`) “Learned rules (human-approved)” and `docs/06` “Learned gotchas”. One line per
   accept, with `<!-- learn:<id> sessions=N -->` provenance; AGENTS.md budget enforced; the full test suite runs and the
   edit is **reverted** if it fails. Everything else (tool interfaces, context, workflows, routing) becomes a task file
   in `.desk_learn/tasks/`. **Protected** engineering surfaces (`desk/spec.py`, `erc.py`, `calc.py`, `netcheck.py`,
   `release.py`, `draw.py`, `tools/verify.py`, `tools/release.py`, `docs/02`) are never edited by this engine; accepting
   such a proposal needs `--engineering-review NAME` and still only creates a task.
6. **Report / bench** — `.desk_learn/report.md` (proposals, measured waste, model-routing evidence table — report only).
   `bench` replays measured waste against current tools (both sides measured).

## Benchmark on real sessions (this machine, first run)
- Corpus: **33 DESK-relevant sessions**, 5,929 tool calls, 2.9 M tool-output tokens, models incl. Claude Opus, GPT‑5.6,
  Nemotron, Qwen2.5‑Coder‑7B, Mistral. Full cycle **1.3–1.9 s**; incremental re-run reads only changed sessions.
- Top corroborated finding: agents read the EasyEDA API reference whole — **SKILL.md 203k tokens in 27 sessions**, class
  docs another ~107k. Response implemented: `python tools/ctx.py api <method|module>` (signature + exists-in-live-client
  + live-verified status). **Replay: 106,638 → 33,324 tokens (−69 %)** on replayable class-doc reads (conservative:
  the pack lists the whole module). The 203k SKILL.md reads are not credited; they need the instruction proposal
  (`P8527be`) — awaiting human review.
- False positives found and fixed during benchmarking: error words inside *read file contents* counted as failures;
  rule violations attributed to pre-DESK sessions.

## Privacy
Local only. Corpus, gaps, decisions and telemetry live in `.desk_learn/` (git-ignored). No model calls, no upload.
Backpass redaction is applied before anything is stored; quotes are ≤ 240 chars. Disable DESK telemetry with `DESK_TELEMETRY=0`.

## Tests
`tests/test_learn.py`: detectors (incl. false-positive guards), era provenance, corroboration floor, idempotent
re-analysis, rejection memory, accept-in-section + mirror, budget refusal, regression **revert**, protected refusal,
and a real Backpass Pi-adapter integration test (parse, filter, redact).
