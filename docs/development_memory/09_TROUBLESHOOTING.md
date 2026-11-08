# 09 — Backpass Operational Troubleshooting Guide

This guide provides diagnostics and remediation steps for common operational issues encountered when running Backpass in the DESK development environment.

---

## 1. Discovery Issues

### Symptom: `backpass scan` reports `0 transcript(s) associated with this repo`
- **Cause 1 (Recency Cutoff):** By default, Backpass only inspects sessions newer than 30 days (`--since 30d`).
  - **Fix:** Run with `--since all`:
    ```powershell
    backpass scan --since all
    ```
- **Cause 2 (Different Working Directory):** The agent was launched from a parent directory (e.g. `C:\Users\HP` or `Documents`) instead of the repository root.
  - **Fix:** Launch coding agents directly from `C:\Users\HP\OneDrive\Documents\DESK`.
- **Cause 3 (Harness Filtered Out):** The harness used is not in the active discovery list.
  - **Fix:** Run with explicit harness flag:
    ```powershell
    backpass scan --harness claude,opencode,pi,cursor
    ```

---

## 2. Model & ACPX Boundary Issues

### Symptom: `acpx: command not found` or `ERR_WINDOWS_SHIM_UNSAFE_ARG`
- **Cause:** `acpx` is missing from system PATH or an argument contained characters unsafe for the Windows command interpreter.
  - **Fix:** Reinstall `acpx` globally and verify:
    ```powershell
    npm install -g acpx
    acpx --version
    ```

### Symptom: `Cold start timeout` or `ACP agent did not advertise that model`
- **Cause:** Backpass attempts to auto-probe installed agents for supported models (`gpt-5.6-luna`, `claude-sonnet-5`).
  - **Fix:** Pin the specific agent harness and model directly:
    ```powershell
    backpass --analysis-agent claude --synthesis-agent claude
    ```

---

## 3. Human Approval & Review Issues

### Symptom: `backpass apply` fails to open browser or errors on Lavish UI
- **Cause:** The optional Lavish web UI (`lavish-axi`) is not installed globally on the Windows host.
  - **Fix:** Use the built-in interactive terminal review flow:
    ```powershell
    backpass apply --no-ui
    ```
  - Alternatively, inspect unified diffs in dry-run mode:
    ```powershell
    backpass apply --dry-run
    ```

---

## 4. Token Budget & Instruction Issues

### Symptom: `CLAUDE.md separate - not optimized` warning
- **Cause:** `CLAUDE.md` contains separate prose rather than resolving as an import pointer to `AGENTS.md`.
  - **Fix:** Restore the pointer header in `CLAUDE.md`:
    ```markdown
    # DESK Instructions for Claude Code

    <!-- Canonical instructions maintained in AGENTS.md and optimized via Backpass -->
    @AGENTS.md
    ```

### Symptom: Always-loaded budget bar exceeds 5,000 tokens
- **Cause:** `AGENTS.md` or skill descriptions have expanded beyond the configured budget ceiling.
  - **Fix:** Backpass automatically enters a "shrink plan" during synthesis. You can also manually extract detailed procedural workflows into `.agents/skills/<name>/SKILL.md`.

---

## 5. Corroboration & Proposal Issues

### Symptom: Known mistake in one session did not generate a proposal
- **Cause:** Backpass enforces a non-negotiable **Corroboration Floor** (`minGapEvidence: 2`). A mistake must be witnessed across at least two independent development sessions before an instruction change is drafted.
  - **Behavior:** This is intentional designed behavior. A single developer prompt misunderstanding must not destabilize the canonical engineering rules. The observation is stored in `.backpass/gap-ledger.json` and will corroborate once a second session exhibits the same pattern.
