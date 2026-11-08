# 00 — Backpass Adoption Audit for DESK

**Target Repository:** `https://github.com/NijoP/DESK`  
**Backpass Repository:** `https://github.com/kunchenguid/backpass` (`v0.1.44`)  
**Audit Date:** 2026-11-08  
**Auditor:** Principal Developer Productivity Architect & AI Agent Infrastructure Engineer  
**Host Platform:** Windows 11 (x64), PowerShell 5.1 / 7.x, Node.js `v24.21.0`, npm `11.19.0`, Git `2.55.0`

---

## Executive Summary

Backpass is a development-time gradient descent optimization engine for agent memory (`AGENTS.md`, `CLAUDE.md`, and specialized skills). It mines historical coding agent transcripts on disk, extracts recurring developer interventions and test failures, corroborates recurring gaps across distinct sessions ($\ge 2$), and generates evidence-backed, token-budgeted instruction edits that require human approval before application.

This audit evaluates the feasibility, environmental compatibility, multi-agent support, and adoption strategy for integrating Backpass into the DESK development lifecycle.

---

## 1. Backpass Capabilities

| Capability | Backpass Implementation | DESK Applicability |
|---|---|---|
| **Transcript Discovery** | Enumerate local disk stores & remote SSH hosts for 7 supported harnesses. | Discovers active Claude Code, OpenCode, Codex, and Pi sessions. |
| **Two-Tier LLM Evaluation** | Tier 1: Per-session cheap loss analysis via `acpx`.<br>Tier 2: Multi-session synthesis & proposal generation. | Utilizes pre-authenticated agent harnesses without separate API keys. |
| **Evidence Grounding** | Verbatim session quotes anchored to instruction IDs (`AG-xxx`). | Guarantees changes reflect real failure modes rather than synthetic hallucinations. |
| **Corroboration Floor** | Requires $\ge 2$ independent session observers for any memory change. | Prevents one-off debugging idiosyncrasies from polluting canonical memory. |
| **Token Budget Management** | Strict budget enforcement (default 5,000 tokens always-loaded). | Prevents instruction bloat in `AGENTS.md` by directing procedures to triggered skills. |
| **Human-in-the-Loop Gate** | `backpass apply` (via web UI or CLI `--no-ui`). | Non-destructive; never silently rewrites hardware engineering rules. |
| **Automatic Skill Extraction** | `extract` / `move` operations to `.agents/skills/<name>/SKILL.md`. | Modularizes deep domain workflows (routing, placement, DRC, EasyEDA). |

---

## 2. Supported Coding-Agent Harnesses

Backpass natively inspects the local storage of seven agent harnesses:

1. **Claude Code** (`claude`):
   - Path: `~/.claude/projects/<munged-cwd>/<session-uuid>.jsonl`
   - Classification: Extracts `cwd`, `gitBranch`, `sessionId`, `version`, `entrypoint`.
   - In DESK environment: Installed (`v2.1.316`).
2. **OpenCode** (`opencode`):
   - Path: `~/.local/share/opencode/opencode.db` (SQLite 1.x & 2.x formats)
   - Classification: Queries `session`, `project`, `message`, `session_v2`, `session_message`.
   - In DESK environment: Installed (`v1.18.16`). Database present at `C:\Users\HP\.local\share\opencode\opencode.db` (6.8 MB).
3. **OpenAI Codex CLI** (`codex`):
   - Path: `~/.codex/sessions/**/*.jsonl`
   - In DESK environment: Not currently installed / not on PATH.
4. **Pi** (`pi`):
   - Path: `~/.pi/sessions/`
   - In DESK environment: 145 historical sessions detected on system.
5. **Cursor CLI** (`cursor`):
   - Path: `~/.cursor/` CLI sessions.
6. **Cursor IDE** (`cursor-ide`):
   - Preview v1.1 store; requires `--include-cursor-ide`.
7. **Grok CLI** (`grok`):
   - Path: `~/.grok/`
8. **Hermes** (`hermes`):
   - Path: `~/.hermes/`

---

## 3. Available DESK Development Transcripts

Inspection of host transcript stores yielded the following empirical distribution:

- **Claude Code Store (`C:\Users\HP\.claude\projects`):**
  - Total project stores: 3 (`C--Users-HP`, `C--Users-HP-Downloads-hackathon`, `C--Users-HP-OneDrive-Documents-BEEBOX-V2-firstmate`).
  - Sessions matching DESK repo: 0 active sessions currently recorded in `.claude`.
- **OpenCode Store (`C:\Users\HP\.local\share\opencode\opencode.db`):**
  - Total recorded sessions: 8 sessions spanning 2026-10-03 to 2026-11-02.
  - Sessions matching DESK repo: 0 sessions matched the current DESK checkout path.
- **Historical DESK Learning Artifacts (`.desk_learn/`):**
  - Contains `corpus.jsonl` (12.3 MB), `gaps.json` (440 KB), `known.json` (33 historical Pi sessions from early prototype runs).
- **Audit Finding:**
  Because the current active git working copy (`C:\Users\HP\OneDrive\Documents\DESK`) has no recent sessions in the default 30-day window, `backpass scan` correctly reports **0 transcripts associated with this repo**. This is the expected initial state for a fresh Backpass adoption. New development sessions conducted via Claude Code or OpenCode in this directory will immediately be captured and indexed.

---

## 4. Existing Instruction Files

- **`AGENTS.md` (Root):**
  - Currently 81 lines / ~1,400 tokens.
  - Contains: Captain/First Mate operating protocol, Context Engine usage (`tools/ctx.py`), prohibited operations ("Never" rules 1–7), Gates R and B checklists, and block iteration workflow.
- **`CLAUDE.md` (Root):**
  - Currently 71 lines / ~1,100 tokens.
  - Redundant: Contains a subset of `AGENTS.md` rules without the newer Captain/First Mate hierarchy.
  - Resolution: Replaced with a canonical Backpass `@AGENTS.md` import pointer. Claude Code natively inlines `@AGENTS.md`, eliminating dual-file drift and enabling unified optimization.

---

## 5. Existing Skill Structure

DESK currently maintains 15 task-specific skills under `.agents/skills/`:
- `pcb-routing`, `placement-engineering`, `quality-gate-supervision`, `schematic-engineering`, `component-selection`, `copper-ground-engineering`, `differential-pair-engineering`, `high-current-design`, `manufacturing-verification`, `engineering-diagnostics`, `execution-recovery`, `benchmark-performance`, `scout-task-intake`, `ship-task-intake`, `skill-index`.

### Structural Assessment
- Descriptions average 25 tokens, consuming ~389 always-loaded tokens across 15 skills.
- The existing trigger fields align cleanly with Backpass's overflow model.
- Refinement needed: Standardize all skills to the 10-point engineering schema required by DESK (Purpose, Triggers/When to use, Required Inputs, Relevant DESK Modules, Engineering Constraints, Recommended Workflow, Validation Steps, Failure Conditions, Expected Output, Documentation References).

---

## 6. Configuration Requirements

A production Backpass configuration for DESK (`.backpassrc.json`) must define:
1. `memoryFiles`: `["AGENTS.md", "CLAUDE.md"]` (where `CLAUDE.md` is a pointer to `AGENTS.md`).
2. `budgetTokens`: `5000` (always-loaded ceiling).
3. `skillsDir`: `".agents/skills"` (overflow target).
4. `minGapEvidence`: `2` (corroboration requirement).
5. `maxTranscripts`: `100` (cap per run with recency-weighted sampling).
6. `discovery.harnesses`: Prioritize `["claude", "opencode", "codex", "pi"]`.
7. `discovery.since`: `"30d"` (configurable to `"all"` or `"90d"`).
8. `discovery.minUserTurns`: `2` (filters out single-turn noise).

---

## 7. Windows Compatibility Gaps

Native Windows execution on Node.js `v24.21.0` was tested and verified with the following findings:

| Component | Status on Windows | Technical Detail / Gap | Workaround / Mitigation |
|---|---|---|---|
| **Core CLI & Discovery** | **VERIFIED NATIVE** | Node.js built-ins (`node:fs`, `node:path`, `node:sqlite`) execute identically. Scans Claude and OpenCode stores in seconds. | Use native PowerShell. |
| **POSIX File Mode (0700)** | **GAP** | Windows NTFS does not support POSIX numeric chmod (`chmodSync(dir, 0o700)` is ignored by OS). | Backpass `src/state.js` includes explicit Windows exception handling falling back to inherited NTFS user ACLs. |
| **Windows Shim Safety** | **DESIGNED** | `windowsShimLaunch` in `src/subprocess.js` validates arguments to prevent `cmd.exe` injection vulnerabilities (`ERR_WINDOWS_SHIM_UNSAFE_ARG`). | Built-in argument validator active. |
| **ACPX Wrapper Scripts** | **GAP** | In `src/harness-invoke.js`, wrapper scripts cannot wrap `.cmd` or `.bat` executables for Pi/Grok model overrides on Windows. | Claude Code and OpenCode bypass this issue and execute directly via acpx. |
| **SSH Remote Hosts** | **RESTRICTION** | `src/discovery/hosts.js` explicitly refuses non-POSIX SSH remotes (`uname` check). | Windows hosts cannot be targets of remote SSH scraping; local scanning works seamlessly. |
| **Lavish UI (`backpass apply`)** | **OPTIONAL** | `lavish-axi` requires separate installation. | Use `backpass apply --no-ui` for deterministic terminal-based review. |
| **WSL2 Alternative** | **DOCUMENTED** | WSL2 is not currently installed on the host machine. | Documented as an optional cross-platform alternative for Linux-standard CI environments. |

---

## 8. Privacy and Redaction Risks

Agent transcripts frequently contain sensitive environmental data:
1. **Host paths & usernames:** Windows user profile paths (`C:\Users\HP\...`).
2. **EasyEDA Authentication Tokens:** Live bridge session cookies, project IDs, and API tokens.
3. **Client Schematics & Netlists:** Proprietary circuit topologies and component values.
4. **API Credentials:** Keys for component vendors, LCSC scrapers, or LLM providers.

### Backpass Safeguards
- `src/redact.js` runs high-entropy string and known token format redaction on all transcript excerpts before caching or synthesis.
- Backpass state is stored in `.backpass/` within the repository root.
- `.backpass/` is registered in `.git/info/exclude` and `.gitignore`, ensuring zero session quotes or private transcripts are committed to Git.

---

## 9. Installation Requirements

1. **Node.js:** `>= 22.5.0` (Host has `v24.21.0` - **PASS**).
2. **Package Manager:** `npm` (Host has `11.19.0` - **PASS**).
3. **ACPX:** Installed globally (`acpx@0.22.0` - **PASS**).
4. **Backpass:** Installed globally (`backpass@0.1.44` - **PASS**).
5. **Verified Agents:**
   - Claude Code (`2.1.316` - **PASS**).
   - OpenCode (`1.18.16` - **PASS**).

---

## 10. Recommended Adoption Strategy

1. **Establish Canonical Root Instructions:** Maintain `AGENTS.md` as the authoritative single source of truth for all agents.
2. **Configure Seamless Claude Pointer:** Set `CLAUDE.md` to `@AGENTS.md` so Claude Code automatically loads canonical instructions while Backpass focuses its token budget on `AGENTS.md`.
3. **Standardize Specialized Skills:** Implement the 10 canonical engineering skills under `.agents/skills/` adhering to the required 10-point schema.
4. **Local-Only Non-Destructive Operation:** Configure `.backpassrc.json` with strict local exclusions, 5,000-token budget, and 2-session corroboration floor.
5. **Human Gate Enforcement:** Adopt `backpass apply --no-ui` as the standard review step; never automate writes without human inspection.
6. **Preserve PCB Production Pipeline:** Ensure Backpass remains strictly a development utility; it must never be imported by `desk.*` Python modules or added to runtime requirements.
