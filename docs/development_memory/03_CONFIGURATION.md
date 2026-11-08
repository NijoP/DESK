# 03 — Backpass Configuration Specification

This document details the configuration schema, state isolation, and harness settings for Backpass within the DESK repository.

---

## 1. Project Configuration File (`.backpassrc.json`)

The canonical project-level configuration resides at `.backpassrc.json` in the DESK root:

```json
{
  "memoryFiles": [
    "AGENTS.md",
    "CLAUDE.md"
  ],
  "budgetTokens": 5000,
  "skillsDir": ".agents/skills",
  "minGapEvidence": 2,
  "maxTranscripts": 100,
  "discovery": {
    "harnesses": [
      "claude",
      "opencode",
      "codex",
      "pi"
    ],
    "since": "30d",
    "worktreeGlobs": [],
    "minUserTurns": 2
  },
  "jobs": 4
}
```

---

## 2. Configuration Field Definitions

| Field | Type | Default | Description in DESK |
|---|---|---|---|
| `memoryFiles` | Array | `["AGENTS.md", "CLAUDE.md"]` | Memory surfaces to track. `AGENTS.md` is primary; `CLAUDE.md` is resolved as an import pointer. |
| `budgetTokens` | Number | `5000` | Maximum token ceiling for always-loaded instructions (`AGENTS.md` + skill descriptions). |
| `skillsDir` | String | `".agents/skills"` | Directory where extracted skills are created and updated. |
| `minGapEvidence` | Number | `2` | Corroboration floor: an issue must occur in $\ge 2$ distinct sessions before an instruction edit is proposed. |
| `maxTranscripts` | Number | `100` | Maximum transcripts analyzed per run. Uses recency-weighted sampling if session count exceeds this cap. |
| `discovery.harnesses` | Array | `["claude", "opencode", "codex", "pi"]` | Specific coding-agent harnesses to discover. Omits unneeded remote adapters. |
| `discovery.since` | String | `"30d"` | Time window for transcript collection. Accepts `12h`, `7d`, `30d`, or `all`. |
| `discovery.minUserTurns` | Number | `2` | Disregards trivial single-prompt sessions that lack iterative development evidence. |
| `jobs` | Number | `4` | Concurrency for Tier 1 parallel transcript loss analysis calls. |

---

## 3. Memory File Pointer Resolution

To prevent dual-file drift between `AGENTS.md` (read by general agents) and `CLAUDE.md` (read by Claude Code), DESK uses Backpass's native import pointer architecture:

### `CLAUDE.md` Pointer Syntax:
```markdown
# DESK Instructions for Claude Code

<!-- Canonical instructions maintained in AGENTS.md and optimized via Backpass -->
@AGENTS.md
```

### Operational Behavior:
- **Claude Code:** Automatically reads `CLAUDE.md`, parses `@AGENTS.md`, and inlines the full content of `AGENTS.md`.
- **Backpass Status / Analyze:** Recognizes `CLAUDE.md` as `pointer to AGENTS.md`, dedicating 100% of the optimization focus and token budget to `AGENTS.md`.
- **Codex & OpenCode:** Read `AGENTS.md` directly.

---

## 4. State Storage and Git Exclusion

Backpass generates local analysis caches, fingerprinted session indexes, and proposal diffs under `.backpass/`:

```
DESK/
  .backpass/
    gap-ledger.json     # Persisted gap observations and session corroboration counts
    status.json         # Fingerprint cache of scanned sessions
    synthesis/          # Staging workspace for proposed diffs
```

### Exclusion Mechanism:
- **Local Git Exclude (`.git/info/exclude`):**  
  Backpass automatically registers `.backpass/` upon running `backpass init`. This file is local to the checkout and never pushed.
- **Repository Gitignore (`.gitignore`):**  
  `.backpass/` is also explicitly declared in `.gitignore` for defense-in-depth, ensuring that no developer or CI pipeline inadvertently commits local transcript cache data.
