# Agent Skill Architecture

## 1. Overview & Principles

The DESK Agent Skill Architecture is modeled directly after the **Firstmate** skill framework (`.agents/skills/`), tailored for mission-critical electronics hardware engineering.

In traditional AI tool architectures, complete system instructions are crammed into an enormous prompt, diluting attention, wasting context tokens, and causing hallucinated violations of physical design rules. DESK solves this through **conditional skill indexing and lazy loading**:

1. **Central Skill Index**: `.agents/skills/skill-index/SKILL.md` acts as a routing dictionary mapping keywords, regex patterns, and engineering domains to specific skills.
2. **Modular Skill Declarations**: Each skill is a standalone Markdown document (`SKILL.md`) located in `.agents/skills/<skill-name>/` with YAML frontmatter.
3. **One-Owner Contract Rule**:
   - `DesignProfile` owns physical constraints and net classifications.
   - `M1–M6` pipelines own authoritative engineering calculations.
   - `desk/operation_registry.py` owns mutation safety and schema validation.
   - Skills provide the procedural instructions for AI agents on how to invoke operations and interpret outcomes.

---

## 2. Skill Directory Layout

```
.agents/
└── skills/
    ├── skill-index/
    │   └── SKILL.md
    ├── schematic-engineering/
    │   └── SKILL.md
    ├── component-selection/
    │   └── SKILL.md
    ├── placement-engineering/
    │   └── SKILL.md
    ├── pcb-routing/
    │   └── SKILL.md
    ├── differential-pair-engineering/
    │   └── SKILL.md
    ├── high-current-design/
    │   └── SKILL.md
    ├── copper-ground-engineering/
    │   └── SKILL.md
    ├── engineering-diagnostics/
    │   └── SKILL.md
    ├── manufacturing-verification/
    │   └── SKILL.md
    ├── quality-gate-supervision/
    │   └── SKILL.md
    ├── ship-task-intake/
    │   └── SKILL.md
    ├── scout-task-intake/
    │   └── SKILL.md
    ├── execution-recovery/
    │   └── SKILL.md
    └── benchmark-performance/
        └── SKILL.md
```

---

## 3. Skill Specification Schema

Every `SKILL.md` file MUST conform to the structured YAML frontmatter standard:

```yaml
---
name: pcb-routing
description: Procedural workflow for single-ended, differential pair, and high-current PCB trace routing.
triggers:
  - "route"
  - "trace"
  - "routing"
  - "clearance"
  - "impedance"
inputs:
  net_names: list
  routing_layer: string
  profile: DesignProfile
outputs:
  routed_tracks: list
  unrouted_nets: list
  drc_passed: boolean
authoritative_pipeline: M3
replay_safety: SAFE_IDEMPOTENT
---
```

### Frontmatter Fields

- `name` (string, required): Unique identifier corresponding to directory name.
- `description` (string, required): Concise statement of skill utility and scope.
- `triggers` (list of strings/regex, required): Key phrases that activate this skill during intent classification.
- `inputs` (dictionary, required): Formal parameters required for skill execution.
- `outputs` (dictionary, required): Formal schema of outputs returned by the skill.
- `authoritative_pipeline` (string, required): The M1–M6 pipeline or DESK runtime engine governing this skill.
- `replay_safety` (enum, required): `SAFE_READ`, `SAFE_IDEMPOTENT`, `UNSAFE_MUTATION`, or `RECONCILE_BEFORE_RETRY`.

---

## 4. Conditional Lazy Loading Mechanism

The deterministic skill resolver (`desk/skills.py`) parses user prompts against the skill index:

1. **Token & Regex Matching**: Incoming instructions are sanitized and matched against `triggers`.
2. **Intent Classification**: Distinguishes Ship Tasks (actions requiring mutation or design synthesis) from Scout Tasks (audits, queries, investigations).
3. **Context Injection**: Only the top matching skill (or minimal requisite set) is loaded into the active agent context, keeping token consumption below 5% of traditional mega-prompts.
4. **Execution Protocol**: Agents execute the checklist defined inside the loaded `SKILL.md`, querying DESK's deterministic operations rather than guessing track geometries.
