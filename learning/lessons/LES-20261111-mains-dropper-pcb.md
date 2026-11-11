# LES-20261111 — Mains resistive-dropper LED board in EasyEDA Pro via API
- Electrical: half-wave dropper numbers come from numeric integration (I_avg ≈ I_pk/π, I_rms ≈ I_pk/2, P_R = I_rms²R); check resistor max working voltage (MOF2WS/3WS 350 V, RN3WS 500 V) and LED reverse voltage (anti-parallel diode across the string).
- Layout: with Ø8/Ø10/Ø8 holes 11 mm apart the gaps between holes are 2 mm → no copper can pass between them; chain the LEDs top → right → bottom and bring the ends out with vias at radius ≈ 8 mm, angle ≈ 110°/−110°.
- Rules that worked with 0 DRC: copper 0.3, TH Pad 2.5 (mounting holes), Board Outline 2.5, Hole 0.3, HV nets 3.0 via per-net rule.
- Deliverable checks: PANELIZE record readback (onlyOutline false), `%SR` header in every Gerber layer, drill hits = 6 × per-board, gerbonara SVG preview rasterised with pymupdf for a visual check.

## Copper pour + rule regions via API (live-verified 2026-11-11 22:00, project light)
- `pcb_PrimitivePour.create` / `pcb_PrimitiveRegion.create` accept ONLY an `IPCB_Polygon` built by `eda.pcb_MathPolygon.createPolygon([x,y,"L",x,y,...,x,y])` (mil, closed ring; `["R",x,y,w,h,0,0]` also valid). Raw arrays, point pairs or {points} fail with "parameters incorrect". Rings with holes: `createComplexPolygon([[outer],[hole]])`; arcs `"ARC",angle,x,y`.
- Region `ruleType` is numeric: 2=COMPONENT, 5=TRACK, 6=FILL, 7=COPPER(pour), 8=PLANE. The stored record name is always "PROHIBIT" (the regionName argument is not kept) → identify regions by layer + prohibitType + polygon, not by name.
- Pour verification chain: POUR + POURED records in `getDocumentSource()`, `rebuildCopperRegion()` true, Gerber copper layer object count rises and contains a `G36` region, DRC 0. `pcb_PrimitivePoured` objects expose no polygon getter.
- `keepIsland:false` (default) deletes unconnected islands — on a mains board with 2.5 mm hole rings and edge clearance the pour may shrink to the region that touches its net; check the Gerber render, not the polygon you drew.
- Independent evaluation by a sub-agent (Explore) reached the same conclusion from the repo evidence; DESK's `easyeda_pcb_adapter.build_create_zone_script` uses the correct format and is now live-verified in spirit (same call shape).
