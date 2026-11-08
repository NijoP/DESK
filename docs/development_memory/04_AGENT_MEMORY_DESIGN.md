# 04 — DESK Agent Memory Architecture and Design

This document describes the canonical memory design, token budget allocation, instruction unit addressing, and quality control protocols for DESK.

---

## 1. Information Architecture Hierarchy

To maximize agent comprehension while strictly containing context costs, DESK establishes a four-tier knowledge hierarchy:

```
+-------------------------------------------------------------------------+
| Level 1: Canonical Always-Loaded Rules (AGENTS.md)                      |
| ~1,500 - 2,000 tokens. Read on every turn by every agent.               |
| Contains: Partnership protocol, gates R & B, core invariant checklist. |
+-------------------------------------------------------------------------+
                                     │ (overflows when procedure > 200 tok)
                                     ▼
+-------------------------------------------------------------------------+
| Level 2: Specialized Triggered Skills (.agents/skills/*/SKILL.md)       |
| Descriptions always-loaded (~25 tok each). Bodies loaded on trigger.    |
| Contains: Procedural workflows (routing, placement, DRC, EasyEDA).      |
+-------------------------------------------------------------------------+
                                     │ (references deep background)
                                     ▼
+-------------------------------------------------------------------------+
| Level 3: Architecture & Engineering Documentation (docs/*.md)           |
| Read on-demand via Context Engine (tools/ctx.py doc <name>).            |
| Contains: Mental models M1-M6, context engine, API reference.           |
+-------------------------------------------------------------------------+
                                     │ (records historical decisions)
                                     ▼
+-------------------------------------------------------------------------+
| Level 4: Project Decision Ledgers (projects/<P>/LEDGER.md)              |
| Per-board durable audit trail.                                          |
| Contains: Confirmed part specs, client confirmations, formula derivations|
+-------------------------------------------------------------------------+
```

---

## 2. Token Budget Dynamics

Backpass enforces a **5,000 token always-loaded budget** across the repository:

$$\text{Always-Loaded Tokens} = \text{Tokens}(\text{AGENTS.md}) + \sum_{s \in \text{Skills}} \text{Tokens}(s.\text{description})$$

### Budget Status in DESK (Verified):
- `AGENTS.md`: ~1,792 tokens (including core checklist and constraints).
- `CLAUDE.md`: 0 tokens (resolved as pointer).
- 15 Skill Descriptions: ~389 tokens (~25 tokens/skill).
- **Total Surface:** **~2,181 / 5,000 tokens** ($43.6\%$ utilized).
- **Headroom:** ~2,819 tokens available for evidence-backed additions.

---

## 3. Instruction Unit Addressing (`AG-xxx`)

Backpass parses memory files into addressable, hash-indexed instruction units:
- Every heading, list item, or thematic paragraph receives an identifier: `AG-001`, `AG-002`, ...
- Each unit is assigned a 12-character content hash (`sha256(normalized_text).slice(0, 12)`).
- This structure enables:
  1. **Attribution Persistence:** Evidence gathered in past runs re-anchors to the correct instruction even if surrounding text is reformatted.
  2. **Fine-Grained Loss Tracking:** Tracks exactly which rules prevent errors and which are repeatedly violated or ignored.
  3. **Targeted Pruning:** Pinpoints obsolete rules that have zero relevance across dozens of sessions.

---

## 4. Relevance-Based Overflow and Skill Extraction

When Backpass analyzes session history, it calculates the **relevance** of each instruction:

$$\text{Relevance} = \frac{\text{Sessions where instruction was actively consulted or violated}}{\text{Total analyzed sessions}}$$

### Placement Rules:
1. **Broad Relevance ($\ge 20\%$):** Stays in `AGENTS.md`. Must be ambiently visible to all tasks (e.g., Captain/First Mate persona, prohibited drawing JS, verification tools requirement).
2. **Narrow Relevance ($< 20\%$):** Automatically proposed for extraction to a skill under `.agents/skills/<name>/SKILL.md`. The detailed procedure is moved to the skill body, leaving behind a concise ~25-token description.
3. **Zero Relevance ($0\%$ over 90 days):** Evaluated for candidate retirement or consolidation during proposal synthesis.
