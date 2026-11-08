---
name: rework-mode
description: Existing PCB recovery, multi-domain engineering audit, controlled surgical repair, and manufacturing readiness verification for unfinished EasyEDA Pro projects.
triggers:
  - "rework"
  - "activate rework mode"
  - "continue unfinished project"
  - "repair existing pcb"
  - "take to manufacturing readiness"
  - "audit existing pcb"
  - "what remains on this board"
inputs:
  project_path: string
  policy: string (AUDIT_ONLY | GUIDED_REWORK | SUPERVISED_REWORK)
outputs:
  session_id: string
  baseline_revision: string
  issue_inventory: list
  repair_plan: list
  readiness_status: string
authoritative_pipeline: Rework
replay_safety: SAFE_IDEMPOTENT
---

# DESK Rework Mode Skill

## Purpose
Enables engineers to continue an unfinished or inherited electronics design without starting from scratch. Preserves original engineering decisions, detects gaps across 8 physical audit domains, proposes surgical repairs with approval tokens, and verifies manufacturing readiness.

## First Principle: Preserve Existing Engineering Intent
- **Never rebuild a PCB from scratch** when only surgical fixes are required.
- Distinguish between **Accepted/Protected**, **Incomplete**, **Incorrect**, **Unknown**, and **Intentional Design Exceptions** (no-connects, DNI parts).
- AI confidence must never replace physical engineering evidence.

## Procedural Execution Flow

### 1. Natural-Language Intake & Mode Activation
When the Captain states:
> *"Activate Rework Mode."*  
> *"I want to rework an existing PCB."*  
> *"Continue my unfinished EasyEDA project."*  
> *"Take this PCB to manufacturing readiness."*

Respond with:
```text
DESK REWORK MODE ACTIVATED, Captain.

I will help you continue your existing PCB project.
First, I need to establish a verified connection to your active EasyEDA Pro project.
I will begin with read-only inspection.
No modifications will be made during project identification or the initial engineering audit.
```

### 2. ECAD Connection & Project Identity Confirmation
1. Query active port and windows via `desk/rework/connection.py`.
2. Discover:
   - Application version & local endpoint.
   - Active Window ID.
   - Active Project name and UUID (`eda.dmt_Project.getCurrentProjectInfo()`).
   - Active Document PCB UUID & Schematic UUID (`eda.dmt_SelectControl.getCurrentDocumentInfo()`).
3. Require explicit Captain confirmation of project identity before proceeding.

### 3. Baseline Capture & Revision Identity
1. Extract existing components, footprints, tracks, vias, zones, stackup, and netlist.
2. Calculate composite revision fingerprint (`geometry_rev`, `connectivity_rev`, `stackup_rev`, `copper_rev`, `rules_rev`).
3. Save immutable baseline to `projects/<P>/state/rework/<SESSION_ID>/baseline.json`.

### 4. 8-Domain Engineering Audit
Execute deterministic physical audits across:
- **Domain A (Requirements & Intent):** Mechanical bounds, power tree, thermal limits.
- **Domain B (Schematic & Netlist):** Missing connections, ERC conflicts, feedback loops.
- **Domain C (Components & Footprints):** Package mismatch, pad count, pin-1 rotation.
- **Domain D (Mechanical Placement):** Edge clearances, connector access, keepouts.
- **Domain E (PCB Connectivity & Routing):** Open airwires, track widths, clearances.
- **Domain F (Power & Thermal):** IPC-2152 current ampacity, thermal dissipation.
- **Domain G (Copper & Ground):** Split planes, return-path continuity, repour state.
- **Domain H (DRC & Manufacturing):** Clearance violations, drill sizes, annular rings.

Output structured issue inventory with severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL`).

### 5. Surgical Repair Planning & Approval
1. Build an acyclic dependency graph of identified issues.
2. Formulate minimal-change "surgical" repairs (classify geometry as `PROTECTED`, `ACCEPTED`, `MODIFIABLE`).
3. Issue cryptographically secure approval tokens (`RW-APR-XXXX`) tied to session, project, and revision.
4. **Never execute a mutation without valid Captain approval.**

### 6. Controlled Mutation, Readback & Verification
1. Verify single-writer lock via `desk/ops.py`.
2. Save atomic checkpoint via `desk/runtime/checkpoints.py`.
3. Apply surgical change.
4. **Mandatory Readback:** Read actual modified primitives from EasyEDA Pro.
5. Re-evaluate physical verification criteria immediately.
6. Record transaction in `repair_history.jsonl`.

### 7. Manufacturing Readiness Assessment
Evaluate all 8 fail-closed hard quality gates on final revision:
- `READY_FOR_MANUFACTURING`: All 8 gates PASS.
- `CONDITIONALLY_READY`: Gates pass with approved exceptions.
- `NOT_READY`: At least 1 gate failed or unknown.
- `INCOMPLETE`: Outstanding repairs remain.
Emit final report to `final_report.md`.
