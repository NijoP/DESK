# DESK Rework Mode: The 8-Domain Engineering Audit

**Document ID:** `docs/rework/05_ENGINEERING_AUDIT.md`  

---

## The 8 Independent Audit Domains

The Rework Audit Engine (`desk/rework/audit.py`) executes deterministic physics audits across 8 independent domains:

### Domain A: Requirements & Design Intent
- Ingests `REQUIREMENTS.md` and `design_profile.json`.
- Audits operating voltages, current demands, mechanical dimensions, and environmental constraints.
- Identifies missing constraints without guessing.

### Domain B: Schematic & Netlist Continuity
- Authoritative netlist comparison between schematic blocks and PCB pads.
- Detects pin net discrepancies, missing schematic components on the PCB, and unintended shorts.
- Validates power tree dependencies and switching regulator feedback loops.

### Domain C: Components & Footprints
- Footprint package integrity, pad counts, pin-1 rotation, and polarity.
- Detects duplicate pad numbers, unpadded mechanical parts, and footprint invariant violations.

### Domain D: Mechanical Placement
- Component-to-board-edge clearance (minimum 0.5mm default).
- Component overlap and package collision detection.
- Connector accessibility and mechanical keepouts.

### Domain E: PCB Connectivity & Routing
- Full graph connectivity traversal.
- Detects unrouted airwires, single-pad dangling nets, and incomplete multi-point nets.
- Distinguishes critical nets (`3V3`, `VBUS`, differential pairs) from general digital nets.

### Domain F: Power & Thermal Engineering
- IPC-2152 current ampacity validation for all power traces.
- Compares actual trace width against target current.
- Flags undersized traces and thermally constrained paths.

### Domain G: Copper & Ground Planes
- Validates continuous reference ground planes.
- Identifies unpoured or stale copper zones.
- Detects isolated copper islands and broken return paths.

### Domain H: DRC & Manufacturing Constraints
- Ingests live EasyEDA DRC violations.
- Classifies errors into clearance violations, short circuits, annular ring failures, and silkscreen collisions.
- Prepares structured data for the recovery planner.
