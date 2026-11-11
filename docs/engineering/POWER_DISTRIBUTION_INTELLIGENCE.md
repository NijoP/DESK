# Power Distribution Intelligence

**Module:** `desk/power_distribution.py` (`PowerDistributionPlanner`, `RailPlan`, `ZoneCheck`, `PowerDistributionReport`). **Sizing:** `desk/ipc.py`. **Tests:** `tests/test_power_distribution.py`. **Benchmark:** `tools/dense_benchmarks.py` (power section).

## Inputs that are never guessed

- Rail current and voltage from `DesignProfile.current_limits_A` / `voltage_rails`. An undeclared rail is reported as `BLOCKED` with the exact key to add; it is never sized by a name heuristic (H-02).
- Copper weight and allowed temperature rise from the profile.
- Pad geometry from the PCB dump; planes and keep-outs from `placement.json`.
- Source identification: `placement.json` `roles.power_sources[net]` when present, else the regulator/connector/battery reference with the most pads on the net (reported, so the engineer can correct it).

## Per-rail decision

| Condition | Strategy | Copper |
|---|---|---|
| a plane is declared for the net | PLANE | loads tap the plane with `vias_required(I)` vias each (IPC-2221 barrel ampacity, 80 % sharing derating) |
| I ≥ 2 A, or worst-path drop > 2 % of V, or width > 60 mil | POLYGON | `CopperPlaneEngine.plan_power_polygons` around the rail's pads; width from `ipc.trace_width_mil` |
| I > 0.5 A | WIDE_TRACE | width from `ipc.trace_width_mil` at the profile's ΔT and copper weight |
| otherwise | TRACE | manufacturer minimum or IPC width |
| loads spread > 15 mm with WIDE_TRACE/POLYGON | note | star/trunk with branches, not a daisy chain |

Voltage drop estimate: R = ρ L / (w t) with ρ = 1.72 × 10⁻⁸ Ω·m, t = 34.8 µm per oz, L = MST length as an upper bound of the worst path. Reported in mΩ and mV and as % of the rail voltage.

## Ground plane

- Continuous reference plane when one is declared; otherwise pours on both outer layers with stitching.
- Rules enforced in the report: no splits by functional block name; thermal relief on hand-soldered / through-hole pads, solid on power stages (`ConnectionRuleResolver`); stitching pitch from the highest edge rate when known, else 2.5 mm; continuity verified only on poured copper (never on the outline).
- `continuity_verified` is reported `false` until a poured-copper readback exists (the live board had 12 pour outlines and 0 poured objects).

## Switching converters (buck/boost)

The fixture `buck_boost` carries VIN / SW / VOUT with input and output capacitors. The planner sizes SW like any rail from its declared current; loop-area minimisation and switch-node constraint are placement rules (decoupling proximity is enforced by the refiner) and remain **[R]** for a dedicated check: identify the input-cap → switch → inductor → output-cap loop and report its area. Status: OPEN (H-12).

## Copper-zone validation (`ZoneCheck`)

For every declared plane and every proposed polygon: net, layer, area (shoelace), pads of the net inside vs outside the polygon (outside = unresolved, needs a via or trace), boundary and keep-out violations (`check_polygon_boundary`), island detection (`detect_copper_islands`), status `OK | UNRESOLVED_PADS | BOUNDARY_VIOLATION | EMPTY`. A visually filled area is never evidence; the verdict needs poured copper and pad containment.

## Measured (synthetic `multi_rail_limited_layers`, declared currents)

| Rail | Current | Strategy | Width | Worst-path drop | Vias per transition |
|---|---:|---|---:|---:|---:|
| 3V3 | 1.5 A | PLANE (Inner2) | 20.6 mil | — | 2 |
| 5V | 1.5 A | WIDE_TRACE | 20.6 mil | reported | 2 |
| VIN_12V | 1.0 A | WIDE_TRACE | 11.9 mil | reported | 2 |
| 1V8, 1V2 | 0.4 A | POLYGON (drop > 2 % of a low rail) | — | reported | 1 |

Whole plan: 3 ms. On the live WATCH board no `design_profile.json` exists, so every rail is `BLOCKED` until currents are declared; that is the intended behaviour.
