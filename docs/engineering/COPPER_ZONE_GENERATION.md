# Copper Zone Generation and Verification

Scope: how DESK plans, declares, creates and verifies copper zones. Planning and verification are offline and tested; creation on a live board uses `desk/adapters/easyeda_pcb_adapter.py` pour scripts and is **IMPLEMENTED_UNVERIFIED** (never executed on a live project; see `docs/LIVE_INTEGRATION_CHECKLIST.md` stages 4-7).

## Pipeline

1. **Plan** (`PowerDistributionPlanner.analyze`): ground strategy, per-rail strategy, polygon proposals, via arrays.
2. **Declare** (`placement.json` `planes`): net, layer name, polygon in mm. `tools/route.py` injects them into the DSN as `(plane NET (polygon LAYER …))` and passes `plane_nets` to the engine so plane nets are not routed as traces.
3. **Create** (live, authorised): `pcb_MathPolygon.createPolygon` + `pcb_PrimitivePour.create` with the exact polygon format recorded in `learning/lessons/LES-20261111-mains-dropper-pcb.md`; then `rebuildCopperRegion`. Requires `ops.write_op` and explicit approval.
4. **Verify**: poured-region readback (`pcb_PrimitivePoured.getAll`), `ZoneCheck` (pads inside/outside, islands, boundary), DRC through EasyEDA, and connectivity that treats poured copper as a conductor.

## Rules

- Correct net and layer per zone; clearance from `DesignProfile.derive_clearance_mil` (standards tables since H-01).
- Thermal relief vs solid from `ConnectionRuleResolver` (current ≥ 3 A or switch-node nets solid; everything else relief with 4 spokes sized 8 × I mil, 10-30 mil). Known defect: the ref-prefix heuristic matches `L` for LEDs and `SW` for any `SW_*` GPIO (H-07 follow-up).
- Island handling: islands below `min_island_area_mm2` removed; islands with no same-net pad reported.
- No plane splits derived from net names; AGND/DGND partitioning only when the profile declares it.
- Stitching vias (`synthesize_stitching_vias`) on a 2.54 mm grid by default, avoiding obstacles and keep-outs; pitch should come from the highest edge rate when the profile declares it.

## Verification gaps (open)

- `PhysicalConnectivityVerifier.verify_board` accepts `zones` and ignores them; pads reached only through a plane via are reported PARTIALLY_CONNECTED (SW-11, P1).
- `evaluate_return_path_continuity` samples the zone outline, not poured copper (H-07).
- Poured copper polygon geometry is not exposed through the properties read in the live observation; the readback must use the documented poured-region getters.

## Acceptance for Stage 4 of the 225-minute programme

Correct net and layer on every zone; zero unresolved islands and zero pads outside their rail's zone without a via/trace; ground continuity verified on poured copper; power zones sized by declared current with drop within budget; thermal connection settings reviewed in the `ZoneCheck` report. Target 30 minutes: planning is milliseconds; the budget is EasyEDA pour/rebuild/readback and DRC time (unmeasured live).
