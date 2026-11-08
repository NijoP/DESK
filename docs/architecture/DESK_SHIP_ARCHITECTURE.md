# DESK Ship Architecture

## 1. The Nautical Command Model

Adopted from the **Firstmate** philosophy, DESK models its engineering automation and agent coordination as a disciplined ship's crew operating under clear naval hierarchy. Electronics hardware design carries physical manufacturing risks, component costs, and thermal/RF hazards. Unclear agent authority leads to board destruction or manufacturing waste.

```
                    ┌───────────────────────────────┐
                    │            CAPTAIN            │
                    │   (Human Lead Hardware Eng)   │
                    └───────────────┬───────────────┘
                                    │ Commands, Intent, Approvals
                                    ▼
                    ┌───────────────────────────────┐
                    │          FIRST MATE           │
                    │   (Primary AI Coordinator)    │
                    │  Bridge, Intake, Orchestrator │
                    └───────┬───────────────┬───────┘
                            │               │
            Ship Tasks      │               │  Scout Tasks
            (Mutating)      │               │  (Read-Only Intelligence)
                            ▼               ▼
            ┌───────────────────┐       ┌───────────────────┐
            │       CREW        │       │      SCOUTS       │
            │ Ephemeral Workers │       │ Reconnaissance    │
            │ Schematic Crew    │       │ Topology Scout    │
            │ Placement Crew    │       │ DRC Audit Scout   │
            │ Routing Crew      │       │ Thermal Scout     │
            │ Copper Crew       │       │ Stackup Scout     │
            │ Verification Crew │       └───────────────────┘
            └───────────────────┘
```

---

## 2. Roles and Operating Boundaries

### 2.1 The Captain (Human Engineer)
- **Role**: Ultimate design authority and commander of the vessel.
- **Authority**:
  - Sets project requirements, operating budgets, and manufacturing specifications.
  - Approves or rejects DRC waivers, schematic edits, and copper zone mutations.
  - Grants permission before any live EDA canvas modification.
- **Guarantees**: No AI worker may unilaterally bypass quality gates, override high-voltage clearances, or issue manufacturing orders without explicit Captain approval.

### 2.2 The First Mate (Primary AI Coordinator)
- **Role**: Second-in-command, bridge operator, and primary conversational interface.
- **Responsibilities**:
  - Greet the Captain respectfully and concisely.
  - Manage task intake, distinguishing between **Ship Tasks** and **Scout Tasks**.
  - Match requests against the Skill Trigger Index and load appropriate domain skills.
  - Supervise Crew and Scout agents, ensuring deterministic engineering pipelines (M1–M6) are invoked correctly.
  - Hold the Bridge during execution, reporting progress through structured events.
  - Present crisp, evidence-backed options when engineering decisions are required.

### 2.3 The Crew (Specialized Ephemeral Workers)
- **Role**: Focused execution agents spawned for specific Ship Tasks.
- **Characteristics**:
  - Short-lived: created to perform a discrete task (e.g., "Place Decoupling Caps for U1") and dismissed upon completion.
  - Scoped permissions: a Routing worker cannot modify schematic nets; a Placement worker cannot alter copper pour parameters.
  - Bound to authoritative M1–M6 calculations: the Crew does not calculate track geometries via generative text; it calls `desk.router` and `desk.placement`.

### 2.4 Scouts (Reconnaissance Workers)
- **Role**: Pure read-only investigative agents.
- **Characteristics**:
  - Absolute zero mutation rights: cannot write to EDA bridge, cannot modify design profiles, cannot alter component placement.
  - Output: Durable, structured Markdown intelligence reports stored in `docs/` or task ledgers.
  - Used for: DRC audits, thermal topology reconnaissance, differential pair skew inspections, and component stock queries.

---

## 3. Bridge Rules & The Single Serialized Writer

1. **One Writer at Sea**: Only the active Ship Task or authorized Crew member possessing the atomic writer lock (`desk/ops.py`) may execute mutations against the EDA canvas or project database.
2. **Scouts Never Touch the Helm**: Scouts execute with read-only database connections and mock adapters.
3. **Emergency Stop (All Stop)**: The Captain can abort any running task via the Bridge, triggering instant process suspension and state rollback to the last verified checkpoint.
