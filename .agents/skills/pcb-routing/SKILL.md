---
name: pcb-routing
description: 6-stage net priority scheduling, trace widths, clearances, and via placement.
triggers:
  - "route"
  - "routing"
  - "track"
  - "trace"
  - "via"
  - "fanout"
inputs:
  net_names: list
  routing_layers: list
  profile: DesignProfile
outputs:
  routed_tracks: list
  unrouted_nets: list
  drc_passed: boolean
authoritative_pipeline: M3
replay_safety: SAFE_IDEMPOTENT
---

# PCB Routing Skill

## Purpose
Coordinates deterministic net scheduling, escape routing, via transitions, and clearance enforcement across PCB routing layers.

## When to Use
- Planning or executing net routing on a placed board.
- Configuring 6-stage priority scheduling in `desk/router.py`.
- Resolving routing congestions, differential pair skew, or DRC clearance violations.

## Required Inputs
- Placed component footprints and pad coordinates.
- Authoritative netlist specification.
- Project `DesignProfile`.

## Relevant DESK Modules
- `desk/router.py`: 6-stage autonomous priority router.
- `AutorouteEngine.class` / Freerouting Specctra DSN bridge.

## Required Engineering Constraints
- Net Priority Invariant: Stage 1 (GND) -> Stage 2 (Edge/Connectors) -> Stage 3 (High-Speed/RF) -> Stage 4 (Controls) -> Stage 5 (Power) -> Stage 6 (General).
- Chamfered Bends: Strict 45° trace bends; 90° right angles are prohibited.
- High-speed differential pairs must maintain continuous ground reference without crossing plane splits.

## Recommended Workflow
1. Verify component placement completion and locked mechanical anchors.
2. Build the plan: `RoutingPlanGenerator.generate_plan(net_graph, dump, board_mm, rules, profile)`; then `DensePCBIntelligence(dump, board_mm, origin_mm, stackup, plane_layers, keepouts).analyze()` for hotspots, corridors and the priority order (see docs/engineering/DENSE_PCB_INTELLIGENCE.md).
3. Schedule nets into priority stages.
4. Synthesize pin escape stubs from fine-pitch SMD components.
5. Execute routing passes; perform rip-up and retry on congested channels.
6. Verify 100% netlist connectivity and run DRC checks.

## Validation Steps
- Verify connectivity: `python tools/verify.py projects/<P> routing`.
- Execute routing test suite: `python -m unittest tests.test_routing_dsn tests.test_routing_escape tests.test_routing_priority tests.test_routing_pass_tracker tests.test_dense_intelligence`.

## Failure Conditions & Recovery
- **"No SES" is a tool defect, not a routing result** (KF-20261111-006). Never re-run the same job; check
  `state/route/progress.json` (best pass, problem nets) and the smoke run. If the engine cannot return a
  partial board on this host (Freerouting 2.1.0 on Java < 25), the fallback is EasyEDA's native autorouter,
  driven from the GUI by the Captain, followed by `tools/route.py --continue`-style readback verification.
- Pre-flight refusal (planes / outline / pads inside router keep-outs): fix `placement.json` `planes` /
  `route_keepouts` or the outline (one plain "R" polyline, KF-20261111-007); do not weaken the gate.
- Unrouted nets after a run: read the net names from `progress.json` and the connectivity report; apply a
  targeted placement fix (`desk/placement_refine.py` proposals, authorised) and re-run with `--continue`.
- Stub/antenna detection: Purge floating track segments via DRC cleanup pass.

## Expected Output
- Fully routed copper tracks meeting clearance, impedance, and length constraints.

## Documentation References
- [Routing Specification](file:///docs/05_ROUTING.md)
