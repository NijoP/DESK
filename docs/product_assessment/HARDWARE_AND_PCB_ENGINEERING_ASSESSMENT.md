# Hardware Architecture and PCB Engineering Assessment (Teams A and D)

**Scope:** read-only audit of DESK's hardware-engineering depth, as an experienced hardware engineer would judge it.
**Method:** every claim cites `file:line` in this repository. Offline numeric checks were run with `python -c` against the modules named. Nothing was modified; no live EasyEDA calls were made.
**Date:** 2026-11-11. **Owner:** Principal Hardware Architect (Team A) with Principal PCB Engineer (Team D).

## 1. Trace width (labelled "IPC-2152")

- The implemented formula is IPC-2221 (`I = k·ΔT^0.44·A^0.725`, k = 0.048 external / 0.024 internal), mislabelled as IPC-2152: `desk/routing/width.py:128-146`, `desk/profile.py:254-259`, `desk/router.py:186-192`. Numerically correct for 2221. Offline check: 1 A / 10 °C / 1 oz external → 11.9 mil; 3 A → 54.1 mil; 10 A → 284.9 mil; internal 1 A → 30.9 mil. IPC-2152 does not penalise internal layers 2.6×; no 2152 chart data exists anywhere in the tree.
- Copper thickness 1.37 mil/oz (`profile.py:36`, `width.py:144`) vs 1.378; negligible. Clamps `max(0.5, thickness)` / `max(0.1, …)` are arbitrary (`width.py:145`, `profile.py:259`).
- **Three inconsistent implementations:** `width.py` (power law, min 5 mil, `current<=0 → 6 mil`); `router.py:TraceWidthCalculator` (power law, `current<=0.3 → 5 mil`, silent cap `max_power_width_mil=120` at `router.py:169,192`, so a 10 A rail is capped at 120 mil with no warning); `rework/audit.py:343` uses a linear "10 mil/A, min 8 mil" rule (3 A → 30 mil vs 54 mil). `audit_power_thermal` also reads `profile.power_nets` (`audit.py:335`), which does not exist on `DesignProfile` → AttributeError when a profile is passed; no test covers it.
- **The production routing path bypasses all of it.** `tools/route.py:139-148` hard-codes DSN widths (VBAT/VSYS/VBUS 10 mil, 3V3/GND 8 mil) and `tools/route.py:247-265` hard-codes widening targets 30/25 mil for nets literally named VBAT/VSYS. `tools/route.py` never imports `DesignProfile`.
- Tests assert only monotonicity (`tests/test_routing_width.py:13-21`, `tests/test_profile_and_mental_models.py:50-60`). No reference-value check against IPC tables.

## 2. Differential pairs

- Exists: `DiffPairProfile` (`profile.py:56-66`: Z, tolerance, width, spacing, max_length_diff); pairs scheduled in stage 3 (`router.py:111-116,131`); strategy D (`routing/strategy.py:54-81`) which ignores the profile and hard-codes 90 Ω, 6 mil width, 6 mil clearance, 5 mil skew; `pcb_rules.json` → EasyEDA diff-pair / equal-length rule objects via `tools/pcb_rules.py:27` (EasyEDA enforces, not DESK).
- Missing: `DiffPairVerification` (`router.py:41-55`) is never instantiated. No skew/length computation, no coupling/spacing check, no impedance calculation, no DSN diff-pair rule injection (`routing/dsn.py` has no pair handling); Freerouting routes pairs as independent nets. The skill promises ≤0.15 mm skew and W/S from εr/H (`.agents/skills/differential-pair-engineering/SKILL.md:32-38`) with no backing code.

## 3. Controlled impedance and RF

- The stackup stores εr, tanδ, dielectric thickness and reference layer (`profile.py:32-41`) but nothing consumes them. No microstrip/stripline/CPW calculator. The default 2-layer stackup assigns 60 mil dielectric to each of two layers (`profile.py:167-170`), double-counting board thickness; the 4-layer default 6/40/6 mil (`profile.py:160-165`) is never used for Z.
- `RFProfile` (`profile.py:69-77`) only pushes a fixed width and ground clearance into the routing constraint (`router.py:474-477`, `strategy.py:84-93`). Strategy G "top layer over unbroken ground" is not verified.
- Antenna: placement rule `rf_edge_mm` 0.5 mm and keep-out rectangles (`placement.py:13,188-197`). No antenna clearance to copper pours, no λ-based stitching pitch (stitching grid fixed 2.54 mm, `copper.py:104,410`).

## 4. High current

- Unknown power-pattern nets silently become 1.0 A (`profile.py:219-220`); `allow_unknown_default=False` is never called outside its definition, so the fail-closed path is dead code. `strategy.py:109` also defaults to 1.0 A.
- Via current: nothing. The skill claims "1.5 A per 0.3 mm via" (`.agents/skills/high-current-design/SKILL.md:34`) but no via ampacity, parallel-via count or via-farm sizing exists. Vias are fixed 24/12 mil everywhere (`profile.py:50-51`, `copper.py:102-103`, `drc_engine.py:190-191`, `routing/escape.py:116`).
- Thermal relief: spoke width = 8·I clamped 10–30 mil, 4 spokes (`copper.py:143-149`); no spoke ampacity check. "Solid" only when ref prefix ∈ {Q, M, U_MOS, D_PWR, L, RS, SHUNT} and (I ≥ 3 A or net contains SW/PHASE/LX/VBAT/VBUS/VOUT) (`copper.py:131-134`). Prefix "L" matches LED1; "SW" matches any SW_xxx GPIO.
- Pours: power polygon = pad bounding box + 1.5 mm margin (`copper.py:191-241`); no area-vs-current sizing.
- Neckdown: handled geometrically (`width.py:166-322`); Freerouting `automatic_neckdown: true`. No check that neck length/width stays within ampacity.

## 5. Power integrity, return paths, plane splits

- `evaluate_return_path_continuity` (`copper.py:456-521`) tests 5 sample points of a track against the ground-zone outline polygon only. It does not model poured copper, antipads, other-net zones on the plane layer, slots, or routed tracks cutting the "plane" on 2-layer boards (layer 2 is both signal and plane: `profile.py:168-169`, `copper.py:170-171`). `plane_split` is declared (`copper.py:117`) but never emitted.
- Island detection = "no same-net pad inside polygon" (`copper.py:363-404`), not connectivity of poured copper.
- Quality gate `copper_zones_connected` consumes a caller-supplied discontinuity count (`quality.py:352-369`); nothing in the pipeline computes it from the live board.
- No PDN/decoupling impedance, no plane-split crossing detection against real geometry, no stitching-capacitor logic.

## 6. Thermal

Only `max_temperature_rise_c` feeds width (`profile.py:256`) and a 5 mm heat-spacing bump when < 10 °C (`placement.py:102-104`). `airflow_lfm` and `max_junction_temp_c` are never read. No θJA / power-dissipation model, no thermal-via farm sizing, no copper-area-per-watt rule. `thermal_clearance_verified=True` was hard-coded in the readiness report (`drc_engine.py:277`; fixed in this milestone, see roadmap H-09).

## 7. Mechanical

- Board outline is always a W×H rectangle. The DSN boundary is overwritten with a rectangle (`router.py:340`, `routing/dsn.py:231-260`); non-rectangular outlines, slots and cutouts are lost for the autorouter. Keep-outs are axis-aligned rectangles only (`copper.py:277-285`, `dsn.py:262-270`).
- Placement checks (`placement.py`): edge distance, connector at edge + front keep-out + MLCC near connector, ESD ≤ 3 mm, sensor-vs-heat, height zones, keep-outs, density. Mounting holes = user keep-out rectangles or auto corner placement at 4 mm with 6.5 mm keep-out (`placement_intel.py:87-98,288-304`). No hole-to-copper annular clearance, no plated/non-plated distinction, no slot support, no panel/V-cut rules.

## 8. ERC and DRC

- Offline ERC (`desk/erc.py:300-331`): GND-named pin on non-GND net, supply pin on GND, supply net without any capacitor to GND, NC pin connected, capacitor voltage rating vs rail-name voltage (`RAIL_V` hard-coded at `erc.py:291`), non-numeric R value. Nothing on driver conflicts, floating inputs, pull-ups, polarity, open-drain, I/O voltage compatibility.
- Offline lint (`desk/spec.py:425-490`): every pin decided, pin exists in cache, single-pin nets, QA formula evaluation (`calc.py`).
- DRC: `desk/drc_engine.py` contains no rule checker. It parses EasyEDA DRC output (`30-81`), classifies by substring (`95-115`) and plans rip-ups. Clearance / short / width / annular / drill checking is entirely delegated to EasyEDA and Freerouting. `ManufacturingReadinessReport` hard-coded `disconnected_tracks=0`, `orphan_vias=0`, and footprint/mechanical/thermal `verified=True` (`drc_engine.py:270-277`; fixed this milestone). `routing/quality.py` only diffs fingerprints of violations it is given.
- Connectivity verifier (`routing/connectivity.py`) is per-net; pads are circles of radius max(w,h)/2 (`242-253`); the `zones` parameter is accepted but unused (`213-218`); `ILLEGAL_CONNECTION` is never assigned, so there is no offline inter-net short detection.

## 9. Component selection and pin maps

- MPN → EasyEDA device by exact name/LCSC match else human `--pick` (`tools/resolve.py:19-29`); `library/devices.json` stores uuid + footprint name; many entries have `footprint: ""`.
- Pin-map provenance is the EasyEDA/LCSC symbol (`tools/pins.py:17-21` → `library/pins/<MPN>.json`, 109 files), not the datasheet. No datasheet cross-check and no symbol↔footprint pad-number verification.
- Wrong-pin prevention: `spec.lint` rejects pin numbers absent from the cache and undecided pins (`spec.py:455-460`); `erc.py` uses pin names for GND/PWR sanity; `netcheck.compare` verifies live sheet nets == spec (`netcheck.py:337-371`). A symbol with a wrong name→number mapping passes all three. `docs/04_PLACEMENT.md:36` claims mirrored-footprint pin validation; no such code exists.

## 10. Hardware compatibility matrix

See `HARDWARE_COMPATIBILITY_MATRIX.md` for the per-category table. Summary: buck/boost PARTIALLY_IMPLEMENTED; flyback/forward/buck-boost/full-bridge/DAB MISSING (no isolation, creepage, transformer or HV clearance model; `derive_clearance_mil` tops out at 24 mil above 50 V, `profile.py:279-282`); motor drivers MISSING; ESP32 PARTIALLY_IMPLEMENTED; STM32 MISSING; USB PARTIALLY_IMPLEMENTED and NEEDS_HARDWARE_VALIDATION; I2C/SPI/UART IMPLEMENTED_UNVERIFIED; CAN/Ethernet MISSING; RF PARTIALLY_IMPLEMENTED; high-speed digital MISSING; analog/mixed-signal PARTIALLY_IMPLEMENTED; mechanical/manufacturing PARTIALLY_IMPLEMENTED.

## 11. Top 10 gaps a 20-year engineer hits first

1. **Voltage clearance model unsafe above 50 V** (`profile.py:272-283`; 300 V → 24 mil). Fix: IPC-2221B Table 6-1 B1–B4 by coating/altitude plus IEC 60664-1 creepage with explicit net-pair voltage. Verify: unit tests against table values and a mains example project.
2. **Unknown-current rails silently sized at 1 A** (`profile.py:219-220`, `strategy.py:109`); fail-closed path dead. Fix: default `allow_unknown_default=False` in `RoutingPlanGenerator` and `tools/route.py`; emit an ERROR gate. Verify: an undeclared VBAT blocks routing.
3. **Production route tool ignores the profile** (`tools/route.py:139-148, 247-265`). Fix: derive net widths/clearances from `DesignProfile`. Verify: e2e test asserting DSN class widths equal profile output.
4. **No differential-pair verification** (`router.py:41` unused). Fix: post-route length/skew from SES or readback tracks, pair-gap sampling, uncoupled-length %; W/S solver for edge-coupled microstrip using stackup fields. Verify: synthetic SES fixtures with known skew.
5. **No impedance calculator** despite stackup fields. Fix: Hammerstad–Jensen microstrip, stripline, CPWG closed forms; validate ±5 % against published reference points.
6. **Via ampacity / thermal-via sizing absent.** Fix: IPC-2221 via cross-section (π·d·plating) plus parallel-via count; thermal via farm from θ budget.
7. **Return-path check ignores real copper** (`copper.py:456-521`). Fix: build plane geometry from EasyEDA poured-region readback minus antipads and other-net zones; sample at ≤ 0.5 mm. Verify: fixture with a split plane under a USB pair.
8. **Rectangular-only outline and keep-outs in DSN** (`router.py:340`, `dsn.py:231-270`). Fix: pass the actual outline polygon and arcs from the PCB dump. Verify: DSN round-trip test with an L-shaped board.
9. **Readiness report fabricated verified=True flags** (`drc_engine.py:270-277`, `models.py:279-281`). Fixed this milestone: defaults are now False and the summary says which checks were not performed.
10. **Three inconsistent ampacity rules and the IPC-2152 label.** Fix: single `desk/ipc.py` with the 2221 formula plus optional 2152 chart interpolation used by `width.py`, `router.py`, `audit.py`; fix the `profile.power_nets` AttributeError. Verify: parity tests across the three call sites and table-value asserts.

## 12. Physically wrong assumptions and dangerous defaults

- Unknown power net → 1.0 A silently; "MOTOR"/"HEATER"/"COIL" regex gets the same 1 A.
- `current<=0` → 6 mil width (`width.py:131-132`) hides missing data.
- Width cap 120 mil in `router.py:169` without diagnostic.
- Clearance: unknown net voltages default to 3.3 V vs 0 V (`profile.py:275-276`); only two tiers (8 mil > 15 V, 24 mil > 50 V); no creepage.
- 2-layer bottom layer assumed to be an unbroken GND plane (`profile.py:168-169`, `copper.py:171`, `docs/05_ROUTING.md:32`) while routing also uses layer 2 (`router.py:449`).
- Fixed 24/12 mil vias and 4.02 mil clearance baked into escape, recovery and stitching regardless of profile or fabricator preset.
- Default 2-layer stackup gives 60 mil dielectric per layer: double-counted board thickness.
- `freerouting.json` job_timeout 20 s, max_passes 15: aggressive for anything beyond a small board (the mode configs in `desk/routing/modes.py` override this at run time).
- Regex net classification: "EN" matches SENSE/GREEN, "CS" matches VCS, "SW" solid-pour rule matches any SW_* GPIO (`router.py:140,153`, `copper.py:132`).
- Skills reference non-existent code: `desk.copper.create_copper_zone` (`.agents/skills/copper-ground-engineering/SKILL.md:43`) and `tests/test_router.py` (`.agents/skills/pcb-routing/SKILL.md:57`).
- Test suite: 63 files / 338 tests, none assert an IPC, impedance or skew numeric reference value; `rework.audit_power_thermal` is untested and broken.
