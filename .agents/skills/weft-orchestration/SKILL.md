---
name: weft-orchestration
description: Work on DESK's Weft orchestration layer - typed workflows over DESK nodes, node contracts, the node service and the Weft runtime adapter.
triggers:
  - "weft"
  - "workflow"
  - "orchestration"
  - "node contract"
  - "hardware_design.weft"
  - "human approval step"
---

# Weft Orchestration Skill

## Purpose
Weft orchestrates, DESK engineers. Workflows are Weft programs under `integrations/weft/`; each DESK node is a typed Weft group that calls the DESK node service, which runs one deterministic DESK engine. Read `docs/weft/04_STATUS.md` first: it says what has been executed and what has not.

## When to Use
- Adding or changing a workflow, a stage group or a DESK node.
- Diagnosing a Weft run, a compile error in a `.weft` file, or a node that fails closed.
- Any question about Weft installation, the pin or the licence.

## Procedure (model-independent)
1. `python tools/desk.py weft status` and `python tools/desk.py weft nodes`. Do not assume Weft is installed or that a node is backed by an engine.
2. To change a node: edit its contract in `desk/weft/contracts.py` and its handler in `desk/weft/nodes.py`, then `python tools/desk.py weft gen`. Never edit `integrations/weft/nodes/desk/*.weft` by hand; they are generated.
3. To change a workflow: edit `integrations/weft/workflows/<name>/src/main.weft` or a stage group in `integrations/weft/nodes/desk_stages/`. Gate every stage on the `passed` of the one before it.
4. After every edit to a `.weft` file or a contract: `python tools/desk.py weft validate`. Fix every error and every warning before going on.
5. Build one stage at a time against real output, not a longer plan: run the node, read what came back, then add the next stage.
6. Run `python -m unittest discover -s tests -p "test_weft_*.py"`, then the full suite.

## Hard Rules
- A handler is a thin adapter. Engineering logic belongs in a DESK engine, never in a node, a `.weft` file or a prompt.
- A valid graph approves nothing. Only a DESK engine sets `passed`, and only DESK records hold approvals and evidence.
- A model never supplies an electrical value that reaches an engine. Model output is validated and stored as advisory.
- No `ExecPython`, no `RunCommand`, no credential in a `.weft` file.
- No node mutates a live design until its authorization path (write lock, approval record, Captain sign-off) is designed and approved.
- If Weft is unavailable, say so. Never run the stages by another route and call it a Weft run.
- Never install Tangle at the DESK repository root: its installer replaces `AGENTS.md`, `CLAUDE.md` and the skill folders.
- Never report a Weft behaviour as verified unless it was executed; `docs/weft/04_STATUS.md` lists what is still unproven.

## References
`docs/weft/01_ARCHITECTURE.md`, `docs/weft/02_INSTALL.md`, `docs/weft/03_LICENCE.md`, `docs/weft/04_STATUS.md`, `integrations/weft/WEFT_PIN.json`.
