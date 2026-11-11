# Live EasyEDA Observation 01 — Read-Only Engineering Inspection

**Classification key used throughout:** **[F]** directly observed fact · **[M]** measurement derived from observed data · **[I]** engineering interpretation · **[H]** hypothesis · **[R]** recommendation requiring independent validation · **UNKNOWN** not establishable from the data.

This project is a learning reference, not a master benchmark. Nothing here qualifies DESK for any PCB category.

## Section 1 — Connection

| Item | Value |
|---|---|
| Gateway | `http://127.0.0.1:49620` (service `easyeda-bridge`) **[F]** |
| Gateway health | `status: ok`, `edaConnected: true`, `edaWindowCount: 1`, `pendingRequests: 0` **[F]** |
| Gateway version | UNKNOWN. `/health` and `/eda-windows` do not report a version; `/version`, `/api`, `/docs`, `/openapi.json` return 404. The expected `1.0.5` could not be confirmed. |
| Window ID | `2ff825bb-d8f5-4d67-92ce-e7f60a9ae137`, `connected: true`, `active: true` **[F]** |
| EasyEDA Pro editor | `3.2.149.88089769` **[F]** |
| Read method | `GET /health`, `GET /eda-windows`, then 13 `POST /execute` calls carrying only documented getter methods (`get*`, `getAll*`, `getState_*`, `getPrimitivesBBox`), explicit `windowId`, `retries=0`, 25–45 s timeouts. No `openDocument`, no window select, no writer lock. |
| Observation window | 2026-11-11 18:04:12Z (probe) to 18:05:39Z (last read); the 13 execute calls completed in 484 ms total **[M]** |
| Raw results | saved outside the project in the session temp folder; nothing written into `projects/WATCH` |

**LIVE_PROJECT_MUTATION_BY_INSPECTION: NONE.** Supported by the call log: every script was a getter chain; start/end counts were identical (components 87/87, tracks 36/36, vias 4/4); `getCalculatingRatlineStatus` stayed `active` throughout, consistent with the other terminal still working.

## Section 2 — Project identity

- Project `nijoponnachan/watch`, friendly name `watch`, uuid `c1859960f83648a892c64af27feb9e63` **[F]**
- Boards: `Board1` (schematic `Schematic1`, 1 page `c75145b22afda01f`; PCB `PCB1` uuid `d8c5340d62893518`) and `Panel1` (no schematic, no PCB) **[F]**
- Active document: type 3 (PCB), uuid `d8c5340d62893518` = the repository's `project.json` `pcb_uuid` **[F]**
- Board outline: one closed rectangle on layer 11, `["R", 0, 1771.65, 1181.10, 1771.65, 0, 0]` → 30.0 × 45.0 mm **[M]**; no arcs on the outline layer **[F]**
- Copper layers in use: 1 Top, 2 Bottom, 15 Inner1, 16 Inner2 (EasyEDA exposes Inner1…Inner32 as SIGNAL type regardless of use) **[F]**; four copper layers **[I]**
- Physical stackup configuration: `null` (no saved stacking configuration name or table) **[F]** → dielectric thicknesses UNKNOWN
- Units of the API: mil **[F]**; canvas origin offset 0,0 **[F]**
- Design rules: one rule configuration with groups `Spacing`, `Physics`, `Plane`, `Expansion` **[F]**; spacing tables for 1 oz and 2 oz copper; `hole2Hole` 0.3 mm; creepage distance 0 (ignored) **[F]**; rule-set name is non-ASCII and did not survive transport (UNKNOWN)
- Real-time DRC: off **[F]**
- Net classes defined in EasyEDA: GND (1), PWR (5: VBUS, VSYS, VBAT, 3V3, VBUS_BOOST), USB (2), SPI (6), AUDIO (9), I2C (3), LED (6); 28 of 60 nets have no class **[F]**
- Differential pairs: one, `USB_D` = USB_DP/USB_DM **[F]**

## Section 3 — Component analysis

- 87 components, 330 pads (313 of them on named nets) **[F]**; 78 on top, 9 on bottom **[F]**
- Reference prefixes: R 32, C 28, LED 6, U 7, SW 5, J 4, MIC 3, L 2 **[F]**
- Footprints: R0402 ×32, C0402 ×15, C0603 ×13, LED0603 ×6, 5.1 mm tactile switches ×5, MEMS mics ×3, XFL4020 inductors ×2, battery wire pads ×2, USB-C 12-pin, SOT-23-6, VSON-10 (0.5 mm), SOT-563 (0.5 mm), LGA-14 (0.5 mm, QMI8658A), 1.27 mm 8-pin header **[F]**
- Board density: 6.4 components/cm², 23 pads/cm² over 13.5 cm² **[M]**
- MPN / LCSC identifiers: the component property schema exposes `LCSC Part Name`, `Supplier Footprint`, `JLCPCB Part Class`, `Datasheet`, `Value`, `Voltage Rating` and others **[F]**, but the generic `getState_Device`/`getState_Properties` calls returned nothing for all 87 parts, so per-component MPN/LCSC values are UNKNOWN from this pass. A follow-up read would need the documented per-property getter.
- Placement drift: 29 of 87 components differ in position or rotation from the repository's `state/pcb_dump.json` (last written 21:43); the repository copy is stale relative to the live board **[M]**
- Fine-pitch clusters **[M, from the density engine on the live dump]**: 78 pads classified RESTRICTED_ESCAPE, 3 MODERATE, 232 EASY, 0 NO_LEGAL_ESCAPE. Hotspot regions with fine-pitch pads: around U2 (22–24, 38–40 mm), U4 (24–25, 27–29 mm), U3 (14–15, 39–40 mm), J1 (5–8, 29–30 mm).
- Cluster interpretation **[I]**: upper third of the board = power/charge/boost ICs and USB-C (U2, U4, J1 region); middle = MCU-side passives and the 1.27 mm header; lower half = the castellated module U5 on the bottom side with the antenna keep-out at the bottom edge; right edge = LED column; three MEMS mics along the right edge with port keep-outs. Functional identities beyond prefixes are **[H]** until the schematic is read.

## Section 4 — Connectivity

- Nets: 60 **[F]**; 313 net-bound pads **[F]**
- Tracks: 36 `pcb_PrimitiveLine` objects, all on layer 11 (board outline), width 8 mil, no net → these are outline/mechanical lines, **not signal routing** **[F/I]**
- Signal tracks on copper layers: 0 **[F]**
- Vias: 4, all GND, 118 mil diameter / 86 mil drill at the four corners → mounting holes modelled as vias **[F/I]**
- Pours: 12 defined (GND on Top ×3, GND on Bottom ×3, GND on Inner1 ×3, 3V3 on Inner2 ×3) **[F]**; poured copper objects: 0 **[F]** → the pours exist as outlines but have not been poured (no copper yet) **[I]**
- Keep-out regions via `pcb_PrimitiveRegion`: 0 **[F]** (the repository's keep-outs live in `placement.json`, not on the board)
- Ratline calculation status: `active` at both ends of the pass **[F]**
- Routing state **[I]**: the board is at the "pre-route" state: placement done, pours drawn, no signal copper. The other terminal's Freerouting run from 22:59 to 23:17 local ended at its timeout without an SES (repository log), so nothing was imported.
- Multi-terminal nets, unconnected pads, per-net connectivity: derivable from the dump; computed below. Unrouted airwires = all 60 nets **[M]**.

## Section 5 — Routing complexity (density engine, 43 ms on the live dump) **[M]**

| Metric | Value |
|---|---|
| Routable signal layers for the density model | Top (1) and Bottom (4); Inner1 = GND plane, Inner2 = 3V3 plane (from the repository plane declarations) |
| Ratsnest crossings (MST, non-power nets) | 233 |
| MST wirelength | 1,260 mm |
| Overall congestion (mean of busiest 10 % of 50 mil cells) | 0.69 |
| Overloaded cells (demand > supply) | 11 |
| Hotspot cells (≥ 0.8) | 30 in 18 regions |

Top hotspot regions (bbox mm, max score, measured causes → strategy):

| Region | bbox (mm) | Score | Pads / fine | Nets | Causes | Strategy |
|---|---|---|---|---|---|---|
| H1 | 3–4, 41–43 | 5.0 (capped) | 0 / 0 | 1 | ratsnest crosses the corner keep-out, detour required | PLACEMENT_REFINE_THEN_ROUTE |
| H2 | 7–8, 14–16 | 1.38 | 6 / 3 | 7 | VBUS, VBUS_BOOST trunk through a signal corridor (C19, U5, U6) | POWER_TO_POLYGON |
| H3 | 5–8, 29–30 | 1.34 | 5 / 5 | 8 | power trunk through corridor at J1 | POWER_TO_POLYGON |
| H4 | 24–25, 27–29 | 1.32 | 3 / 3 | 10 | VBUS_BOOST, VBUS_BOOST_EN, VSYS at U4 | POWER_TO_POLYGON |
| H5 | 24–25, 23–25 | 1.31 | 3 / 0 | 12 | demand exceeds supply (SW5, U5) | CORRIDOR_RESERVE_LAYER_SPLIT |
| H6 | 22–23, 27–28 | 1.25 | 2 / 2 | 6 | power trunk + only one free layer | POWER_TO_POLYGON |
| H7 | 22–24, 38–40 | 1.19 | 4 / 4 | 10 | VBAT, VBUS, VSYS at U2 + layer scarcity | POWER_TO_POLYGON |
| H8 | 15–21, 25–26 | 1.10 | 5 / 0 | 19 | demand exceeds supply along U5's top edge | CORRIDOR_RESERVE_LAYER_SPLIT |

Corridors found: C1 vertical at x 25–26 mm, y 13–28 mm (adjacent to five hotspots); C2 horizontal y 26–27 mm, x 16–24 mm; C3 horizontal y 30–31 mm, x 0–14 mm. **[M]**

Priority order the engine proposes for Freerouting (`priority_net_classes`): LCD_BL, USB_DM, USB_DP, PGOOD_N, VSYS, VBUS, VBUS_BOOST, VBUS_BOOST_EN, VBAT, AMP_SD_MODE, I2S_SPK_BCLK, I2S_SPK_DOUT … **[M]**

Interpretation **[I]**: the dominant problem is not fine-pitch escape (no NO_LEGAL_ESCAPE pads) but power trunks (VBUS / VBUS_BOOST / VSYS / VBAT) competing with signals in narrow corridors on a 2-routable-layer board whose inner layers are planes. Seven of the top ten regions have a power cause. The second problem is the module edge (H5, H8): 19 nets converge on one 6 mm strip.

Observed Freerouting behaviour from the repository log of the run that preceded this read **[F]**: 49 passes in 16.6 min, unrouted oscillating 64→51→27→18→11→12→11→…→7 (pass 20)→…→25; 11 "Restoring an earlier board that has the score of 708.76 (51 unrouted)" events; no SES written. Engine v2.1.0, which scores by trace length and via count, not completion **[F, from Freerouting docs]**.

## Section 6 — Power and ground

- Power rails by net class: VBUS, VSYS, VBAT, 3V3, VBUS_BOOST **[F]**; additional rail-like nets without a class: VBUS_SENSE, VBUS_BOOST_EN, NET_BST_FB, PGOOD_N **[F]**
- Planes: Inner1 GND pours (3 outlines), Inner2 3V3 pours (3 outlines), plus GND pours on Top and Bottom (3 each) **[F]**; none poured yet **[F]**
- Power components **[H from footprints]**: XFL4020 inductors ×2 (boost/charger), SOT-23-6 and VSON-10 regulators/chargers, battery wire pads; USB-C input. Currents, voltages and the actual topology are UNKNOWN: no `design_profile.json` exists for this project and the schematic was not read.
- Ground continuity: cannot be assessed; no poured copper exists yet **[F]**
- Conclusion: the live project exposes enough geometry to plan power distribution, but not enough electrical data (rail currents, source/load roles) to size it. That data must come from the design profile or the schematic, never from net names **[I]**.

## Section 7 — DESK capability mapping

| Observed challenge | Existing DESK module | Status |
|---|---|---|
| Read board geometry safely | `desk/bridge.py` + getter scripts | works; 484 ms for the whole board |
| Pad escape classification | `desk/routing/escape.py` | works (313 pads in < 20 ms) |
| Ratsnest, MST, crossings | `desk/routability.py` | works |
| Congestion map with causes, corridors, priority order | `desk/routing/density.py` (new this milestone) | works offline; not yet wired into `tools/route.py` |
| Priority order reaching the router | `orchestrator.build_config(priority_net_classes=…)` (new) | implemented; needs Freerouting ≥ 2.2 to honour `priority_net_classes` (UNKNOWN for 2.1.0) |
| Engine stagnation on oscillation | `orchestrator.PassTracker` (new, improvement-based) | implemented; replaces the identical-count rule that never fired |
| Plane declaration to the router | `tools/route.py` plane injection + `plane_nets` config | works (DSN) |
| Pour planning / islands / return path | `desk/copper.py` | exists, no pipeline caller, verifier ignores pours |
| Placement refinement for routability | none before this milestone; `desk/placement_refine.py` planned | missing |
| Power distribution sizing | `desk/ipc.py` + `desk/profile.py` (M2) | sizing exists; needs declared currents |

## Section 8 — Missing capabilities (prioritised from this observation)

1. Per-component MPN/LCSC readback through the documented property getter (needed for BOM and library verification).
2. Pours treated as conductors in `PhysicalConnectivityVerifier`; poured-region readback for ground continuity.
3. Router integration that consumes the density engine's output (priority classes, plane nets, via costs) and keeps routed copper between attempts (`-de dsn+ses`).
4. A Freerouting engine that scores by completion (v2.2+ needs Java 25 on this machine; v2.1.0 is the only runnable JAR).
5. A design profile for the project so power trunks are sized and routed as polygons or plane taps instead of competing in signal corridors.
6. Placement-routing feedback: the gate accepted 233 crossings and seven power-in-corridor hotspots.
7. Keep-outs as board regions: the live board has none; the repository's keep-outs are DESK-only knowledge.

## Section 9 — Engineering recommendations **[R]**

- Route the five PWR-class nets as polygons/plane taps on Top/Bottom with via arrays sized by `desk/ipc.vias_required`, then run the signal router with those nets excluded (`ignore_net_classes`) — removes the dominant cause in 7 of 10 hotspots.
- Reserve corridor C1 (x 25–26 mm) and C2 (y 26–27 mm) for the U5 edge nets by routing them first with `priority_net_classes`.
- Replace the identical-count stagnation rule with the improvement-based tracker (done) and stop at ~pass 26 instead of the 17-minute timeout on runs like the recorded one.
- Install Java 25 so the v2.5.0 JAR already in `library/tools` can be used; its router score is completion-dominant and it restores the best board itself.
- Add a `design_profile.json` with declared rail currents before the next routing attempt; otherwise widths come from heuristics.

## Section 10 — Evidence limitations

- Single read-only pass; multiple reads were not one atomic snapshot (counts were stable, ratline status was `active`).
- The gateway version and the rule-set name could not be read. Stackup dielectrics are not configured in the project.
- Component MPN/LCSC properties were not retrieved; functional block identities are inferred from reference prefixes and footprints only.
- No signal copper existed, so routing-state observations (track widths, layer utilisation, routing failures) are UNKNOWN for the live board; the routing-behaviour facts come from the repository's Freerouting log of the previous run.
- The density engine is new and calibrated only on this board and synthetic fixtures; its absolute scores are relative indices, not predictions of Freerouting outcomes, until validated on more datasets (roadmap QA-01).
- No test or tool was run against the live project; all analysis ran on the saved copy of the read results.
