# UPS_1000 INTERIM REVIEW (S1 requirements/schematic, S2 components/placement)

Examiner: ups-sonnet-examiner (Claude Sonnet), independent, read-only. Routing (S3+) NOT judged.
Method: raw files only (gen_blocks.py, blocks/*.json, library/pins, DATASHEET_FACTS.md, pcb_dump.json, placement.json, records, git diff). Numbers recomputed by me.

## 0. Verdict
Strong requirements work and honest process. Schematic pin maps are all correct against library/pins (zero pin-map errors found). Calculations are mostly right. The real problems are in placement (hot loop and gate loop geometry; decoupling proximity) and in a stale or incorrect design_profile.json. Several protection-behaviour weaknesses are documented only weakly. No false certification claims found.

## 1. Pin-map audit (Task 1) - result: NO ERRORS
Checked every IC pin against library/pins/*.json and DATASHEET_FACTS:
- UCC21520DWR: 1 INA=INA_S, 2 INB=INB_S, 3/8 VCCI=3V3, 4 GND, 5 DISABLE=DRV_DIS (10k to 3V3, 1 nF; active-high so disabled at reset - correct), 6 DT=20k||1nF (200 ns, 10 ns/kOhm - correct), 9 VSSB=GND, 10 OUTB, 11 VDDB=12V, 14 VSSA=SW, 15 OUTA, 16 VDDA=BST, 7/12/13 NC. Correct.
- INA240A1PWR: 2 IN+=SW (supply side), 3 IN-=PHASE (load side), 5 VS=3V3, 6 REF2=GND, 7 REF1=3V3 (mid-supply, datasheet 8.4.3.2), 1 NC. Correct. Full-scale (3.3-0.05-1.65)/0.1 = 16 A: matches qa.
- LM339DR polarity (the classic trap) - all four correct: C1 IN1-=ISENSE, IN1+=REF_OCP -> OUT1 low when ISENSE>REF (OC+); C2 IN2+=ISENSE, IN2-=REF_OCN -> low when ISENSE<REF (OC-); C3 IN3+=NTC_SNS, IN3-=REF_OT -> low when NTC node falls (hot, NTC pulls down); C4 IN4-=VBUS_SNS, IN4+=REF_OV -> low when VBUS_SNS>REF. Output pins 1/2/13/14 wired-OR to FAULT_N, pin 3 12V, pin 12 GND.
- SN74LVC2G08DCUR: 1A/1B -> 1Y(7), 5/6 -> 2Y(3), 4 GND, 8 VCC. Correct.
- STM32G431CBT6 (LQFP48): PA8 pin30 TIM1_CH1 PWM_H, PA7 pin15 TIM1_CH1N PWM_L (AF6), PA6 pin14 BKIN (AF6), PA0/PA1/PB0/PB1 ADC, PA11 pin33 FDCAN RX, PA12 pin34 TX (AF9), PA2/PA3 USART2 (AF7), PA13/PA14 SWD, PB8-BOOT0 pin45 with 10k pull-down, NRST 100 nF, VDD 24/36/48, VSS 23/35/47, VDDA 21, VSSA 19, VREF+ 20, VBAT 1. Matches DS Table 12/13. PB5/PB6/PB7 (pins 42/43/44) = LED/FAN/DRV_DIS plain GPIO. Correct.
- BSC070N10NS3G: Q1 S=SW(1-3) G=GH(4) D=VBUS(5-8); Q2 S=GND G=GL D=SW. Correct.
- SN65HVD230DR: 1 D, 2 GND, 3 VCC, 4 R, 6 CANL, 7 CANH, 8 RS=GND (high-speed), 5 Vref NC. Correct.
- LM5164: 1 GND, 2 VIN, 3 EN, 4 RON, 5 FB, 6 PGOOD NC, 7 BST, 8 SW, 9 EP=GND. TPS54202: 1 GND, 2 SW, 3 VIN, 4 FB, 5 EN floating (allowed), 6 BOOT. AP2112K: 1 VIN, 3 EN tied to 5V, 5 VOUT. AO3400A G/S/D, 1N4148W K=12V A=FAN_N, LED polarities (KT-0603G pin1=K, KT-0603R pin1=A) all consistent with the (builder-corrected) pin files.
- The builder's library/pins edits (AO3400A, KT-0603R pin order) are corrections, not weakenings: consistent with the real parts (git diff shows only reorder).
Minor doc inconsistencies only (see MINOR list): REQUIREMENTS s8 GPIO table is stale vs blocks (USART1/PA9-10, PA2 "..." vs real USART2 PA2/PA3).

## 2. Recomputed calculations (Task 2)
| Item | My result | Builder | Verdict |
|---|---|---|---|
| LM5164 Vout | 1.2*(1+91/10)=12.12 V (11.93-12.30 over Vref) | 12.12 | OK |
| fsw | 12.12*2500/100 = 303 kHz | 303 | OK |
| tON | 685 ns @58.4 V, 2.0 us @20 V (>=300 ns, so tOFF min 50 ns) | same | OK |
| Type-3 CA | >=10/(303k*9.01k)=3.66 nF; 10 nF chosen | 3.66 | OK (the || operator is assumed in the datasheet extract; builder flags it) |
| RA*CA | 75k*10n=750 us <= 2us*8/20mV = 800 us (only 6% margin at VIN=20 V) | same | OK but thin; FB ripple 26.7 mV @24 V, 21 mV @20 V - barely above the 20 mV rule at VIN min |
| CB | >=110 pF; 100 nF chosen (tau with 9 k = 0.9 ms) | 100 nF | Valid but oversized; will slow startup/line transients. Not an error |
| EN/UVLO | on 18.0 V, off 16.8 V | qa says 18.0/16.8 | OK, but REQUIREMENTS.md s1 says "about 16.5 V" - inconsistent |
| Inductor ripple 58.4 V | 0.67 A pp, Ipk = 0.343+0.335 = 0.68 A | Ipk=0.34+0.33=0.67 | OK vs 1.2 A valley / 1.5 A peak limit |
| TPS54202 Vout | 0.596*(1+75/10)=5.066 V (4.94-5.19) | same | OK (inside 4.8-5.2, only 0.01 V from top at Vref max: 5.19) |
| TPS54202 L | 10 uH, dI=0.58 A pp | same | Below datasheet 13.7 uH min at 2 A, justified by 0.13 A load; Ipk calc uses 0.15 A load (fine) |
| OC trips | REF_OCP 2.643 V -> +9.93 A; REF_OCN 0.657 V -> -9.93 A | same | OK. Tolerance (1% R, 5 mV offset) about +-0.15 A |
| OT trip | REF 0.300 V -> Rntc 1.000 k -> T=1/(1/298.15+ln(0.1)/3380)=374.1 K = 100.97 C | 101 C | OK arithmetic. B25/50 extrapolated to 100 C: real NCP18XH103 R100 about 0.97 k - fine. NO hysteresis |
| OV trip | REF 2.909 V / 0.048525 = 59.95 V | "60.0 V" | Arithmetic OK; DESIGN ISSUE, see MAJOR-3 |
| VBUS_SNS | 58.4*0.0485=2.83 V; 60 V=2.91 V | same | OK |
| FET loss | Pcond 25*0.007*1.5*0.5=0.131 W; Psw 0.5*58.4*10*40n*20k=0.234 W; total 0.365 W; Tj=40+0.365*50=58 C | same | Arithmetic OK. Omits Qrr/Coss loss (BSC070 Qrr ~100+ nC => ~0.1-0.15 W at 58 V) and the 40 ns tr+tf is ASSUMED. Even doubling, Tj < 80 C. Conclusion safe |
| Shunt | 25*0.005=0.125 W | same | OK |
| Conductor widths (IPC-2221, my recompute) | 10 A, dT10: outer 2oz ~139 mil, inner 1oz ~735 mil | 142 / 741 | OK (within 2%) |
| TVS | VRWM 60 >= 58.4; VC 96.8 V at 6.2 A | | See MAJOR-2 |
| Dead time | 10 ns/kOhm * 20k = 200 ns | same | OK |
| Bootstrap C | 10*55 nC/0.5 V = 1.1 uF; 1 uF+100 nF | OK |
| DS fact check | BOM text says Qg "64 nC max" in REQUIREMENTS s3 vs datasheet 55 nC max / 42 typ | conservative, inconsistent with qa (55 nC) |

## 3. Findings, ranked

### CRITICAL
None at the schematic level. (Placement items below are MAJOR because routing may still mitigate, but see MAJOR-1.)

### MAJOR
**MAJOR-1  Hot loop geometry is poor and not caught by any gate** (projects/UPS_1000/state/pcb_dump.json, placement.json).
My pad-to-pad measurements from the readback: Q1 drain pads (VBUS) at y=74.8 mm, Q2 source pads (GND) at y=57.2 mm -> the FET stack itself is 17.6 mm long. Nearest hot-loop MLCC C42 is 8.1 mm from Q1 drain and 17.0 mm from Q2 source; C43 11.2/19.0; C44 14.7/21.4; the 0603 HF cap C45 12.8/10.2 mm. The placement.json comment "directly below Q1: minimal hot loop" is not what the dump shows. Estimated loop length >30 mm => tens of nH, ringing risk against a 100 V FET whose clamp margin is already thin (MAJOR-2). PLACE-HOTLOOP-012 is ADVISORY in domain_validate.json so "PLACEMENT & ROUTABILITY OK" says nothing about it. Board utilisation is 12% with a 14.5k mm2 free region, so there was no space excuse.
**MAJOR-1b  Gate-drive loop is long**: UCC21520 U7 sits at x=56 mm, FET gates at x=33.9. Gate series resistor R20 (GHO-GH) is at (55.8,53.5), i.e. ~10 mm on the wrong side of the driver and ~22 mm from Q1's gate at (33.9,69.2); R21 (GLO-GL) is at (52,72.7), 20 mm from Q2's gate at (33.9,57.2). Gate loop of 40+ mm with 10 ohm resistors will ring and couple dv/dt. ROUTE-GATE-028 is also only ADVISORY.
**MAJOR-1c  Decoupling proximity degraded by the new legaliser**: pad-to-pad distances in the dump: LM5164 VIN caps C5/C6 6.4 / 12.4 mm from pin 2 (this is the buck's own hot loop on a 100 V part); UCC21520 VDDB cap 7.3 mm (C39, 100 nF) and 10 mm (10 uF), VCCI 5.8 mm, boot cap 3.2 mm; STM32 VDD pin caps 3-10 mm; INA240 VS cap 4.0 mm; TPS54202 VIN 5.7 mm. placement.json declares decap_max_mm=2.0 and PLACE-DECAP-010 is ENFORCED, yet the final gate printed only 3 WARNs. Either the check measures body edge to pin differently or the collision-aware legaliser (F-005 fix) pushed passives outward until they stopped being near pins. Examiner could not reproduce the gate; builder should state the metric and show that PLACE-DECAP-010 actually evaluated these parts.
**MAJOR-2  TVS clamp vs ratings is not a real margin** (blocks/01_PWR_IN.json qa, BOM_SELECTION s8). SMBJ60A VC=96.8 V at IPP 6.2 A (datasheet fact p2); BSC070N10NS3G VDS 100 V, LM5164 VIN 100 V (ROC; absolute max not checked), INA240 CM 80 V ROC. Margin is 3% against the FET, and negative for INA240, with zero allowance for hot-loop ringing (MAJOR-1) or VBUS-to-SW overshoot. The builder recorded it as "documented risk" with pass=true. Wrong tool for the job: either lower-clamp TVS, a lower-V part ladder or an explicit overvoltage-ratio statement. Also the OV comparator trips at about 60 V, the same number as the TVS stand-off.
**MAJOR-2b  Reverse-polarity claim not supported**: qa says reverse polarity "forward-conducts TVS and opens F1 (7 A)", but REQUIREMENTS s2 states the lab supply is limited to <=6 A. A 6 A current-limited supply never opens a 7 A fast fuse; the TVS (SMBJ, short-pulse device) then carries 6 A at ~1 V for as long as the operator leaves it connected, and the 100 uF electrolytics see reverse bias. The claim is unverified and probably false for the stated bench use. Needs a series reverse-protection FET/diode or a fuse/limit coordination statement.
**MAJOR-3  OV trip has no margin against 58.4 V full-charge** (08_PROTECTION qa). Trip nominal 59.95 V vs 58.4 V design max = 2.7%. Tolerances: REF_OV is ratiometric to 3V3 (AP2112K +-2%) while VBUS_SNS is not; resistors 1% each; LM339 offset up to +-5 mV (+-0.1 V at VBUS). Worst-case trip window about 57.7-62.2 V, so the board can nuisance-trip inside its own stated operating range (16S LiFePO4 full charge) and could also exceed 60 V. For 24 V bring-up this is harmless, hence MAJOR not CRITICAL.
**MAJOR-4  design_profile.json does not describe this board** (projects/UPS_1000/design_profile.json, domain_validate.json compiled.design_profile). board_dimensions_mm=[50,50] (client: 160x120), all copper 1.0 oz (client: 2 oz outer), default 6/40/6 mil dielectric stackup, net_classes/keepouts empty, compiled_at 16:53:51 (after placement started). Rules marked ENFORCED (ELEC-WIDTH-001, ELEC-CLEAR-003, MFG-EDGE-072, COPPER-*) are therefore being evaluated against a wrong board/stackup. conductor_sizing.txt uses the right 2 oz numbers independently, but the machine-readable profile and its hash 58cbda577a99e1fe are wrong. Also the profile applies the mains_safety_isolation overlay and mains rules (MAINS-DECL, MAINS-INS, MAINS-FUSE) to a SELV board with `"mains": false`; classification_status is still REVIEW_REQUIRED and classifier "conflicts" were not resolved in the saved file (a later "conflicts": [] appears in compiled, but the classification block still lists them). The builder did ship a LV rule set (builder-records/domain/rules_lv_prototype.json) but that is not what the saved profile uses.
**MAJOR-5  Protection behaviour is thinner than the narrative**: (a) no comparator hysteresis and no hardware latch; FAULT_N releases the moment current/temperature falls, so OC/OT will chatter (PWM gated -> current drops -> fault clears -> PWM resumes) unless firmware's TIM1 BKIN latch is correctly configured; the hardware shutdown is not self-latching as REQUIREMENTS s1 ("until firmware clears") implies. (b) The shunt is between SW and J5, so a shoot-through current (Q1->SW->Q2) bypasses it entirely; only the 200 ns hardware dead time and fuse protect against that. (c) 2-3 us response is an estimate (marked "to be MEASURED" - fine) but the lab bulk capacitance (200 uF + MLCC) can deliver kA into a hard short at the J5 terminals within that time; FET Idm 368 A. (d) No inrush/pre-charge; fine for lab. (e) LM339 U9 is at (86,46), about 70 mm from INA240 U8 (20,75): the fast OC analog path crosses the control zone.

### MINOR
- M1 Kelvin sense geometry: shunt R24 pads SW y=62.9, PHASE y=69.1; INA240 U8 at y=72.1-77.9 sits beyond the PHASE pad, so the IN+ (SW) sense trace must run past the PHASE pad and the whole shunt length (~9 mm to the SW pad) alongside high-current copper and the noisy SW node. Workable only with careful routing. ROUTE-KELVIN-024/PLACE-SENSE-018 are ADVISORY.
- M2 Isolation: honest (no safety isolation claimed, "functional only", single GND) - good. But REQUIREMENTS s10 says "unbroken L2 GND plane" while the copper keep-out is declared "all layers" under U7 (rect 52.8-59.2 x 60.8-71.2): contradictory. The keep-out is also only 6.4 mm wide, shorter than the driver's own 8 mm CLR/CPG; that is acceptable only because nothing is claimed.
- M3 Remaining placement WARNs left unresolved: D1 TVS 28.9 mm from J5 VBUS (the TVS is at J1; J5 is an output - arguably intended), 94 hotspot cells around J5/left edge (3.8, 54-61) next to a 14.5k mm2 empty region.
- M4 REQUIREMENTS.md stale vs blocks: s3 power budget says LM339 on 5 V (moved to 12 V), s8 UART on PB3/PB4/USART1, EN threshold "16.5 V" (real on 18.0 V), Qg 64 nC (datasheet 55 nC max). The blocks are right; the narrative is not.
- M5 conductor_sizing.txt prints clearance/creepage ("B2 @58.4 V 0.6 mm | creepage PD2 IIIa 1.25 mm") without an UNVERIFIED label. The rule engine does mark the table transcription as needing human review, and REQUIREMENTS M-04 says UNVERIFIED, but the number printed in the sizing record itself carries no flag. The 12.6 V creepage 0.04 mm is below fabricator minimum so irrelevant. No invented HV spacing - good.
- M6 Stackup deviation (L3 as second GND instead of client's DC power distribution; ledger L-0031) is documented with reasoning; acceptable but is a unilateral client-spec change that belongs in the Captain-facing deviation list. Dielectric thicknesses remain TBD (the profile uses 6/40/6 mil defaults, unrelated to a 2.0 mm board); L1-L2 spacing sets the hot-loop return inductance and is unknown.
- M7 ERC warning "BST has no capacitor to ground" is a true false-positive (cap is BST-SW, which is correct for a bootstrap); fine, but noted.
- M8 Instrument header J9/J7 puts ISENSE, FAULT_N, INA_S/INB_S directly on pins with no series resistor: a probe slip can disturb the protection chain.
- M9 Many parts have "TO VERIFY" (fuse, electrolytic ripple, terminal rating, inductor Isat, crystal CL, NTC B, commercial STPS1H100A, STM32 DS revision). Properly listed V-01..V-10: honest; they remain open release items.
- M10 5 V buck exists only to feed one 122 mA LDO; wasteful but fine for a prototype.

### Things done well (evidence)
- Scope split SYSTEM vs PROTOTYPE with explicit HV release BLOCK (REQUIREMENTS s0, s11, s12). No mains footprint placed.
- Missing-requirement register catches 16S LiFePO4 = 51.2 V nominal (58.4 V full, 15S = 48 V) - correct arithmetic; also insulation coordination, editions, output specs, charger.
- No false certification; all tables "UNVERIFIED" or TBD; datasheet mirror caveats and reduced-confidence sources disclosed.
- Failure register is candid (F-001..F-005), human-intervention counted (Apply on Import Changes dialog), timing/stage metrics consistent.

## 4. Code changes review (Task: git diff)
- tools/desk.py: `domains` argument parsing now drops values of --project/--overlays. Correct for both argument orders (index logic checked; first-position flag handled). Regression test tests/test_domains_cli_args.py exercises both orders and reads the declared rails: sound test. Not a gate weakening - it fixes a silent wrong result.
- tools/pcb_place.py: adds collision-aware legalisation. Does not remove any gate; but it silently falls back to the old spot if nothing is found within 8x7 search cells and, as MAJOR-1c suggests, may move passives away from their ICs. No unit test added (tests only cover domains fix). Needs a test and a statement of how PLACE-DECAP-010 interacts.
- tools/pcb_board.py (new): refuses to replace an existing outline, uses recorded CLI approval and write_op, readback verification. Uses only verified API calls cited. Acceptable.
- tools/resolve.py: --refresh only overwrites on exact match; harmless.
- library/devices.json: entries filled with footprint/uuid (previously empty footprints); deletions are the empty placeholders only. No rule or gate file under desk/ changed.
- Baseline test run: 717 tests, 2 failures + 1 error in test_orchestrator (07/10/11), builder attributes to environment variables leaking DESK_L*_MODEL_PI; plausible (assertions compare model names) and unrelated; I could not rerun (not allowed). A post-change full-suite run is not in the records I was given (baseline_tests.txt is pre-change) - process gap vs AGENTS.md section E.

## 5. Placement quality summary (Task 4)
Good: connectors on edges, power stage left / MCU right / comms right edge, mounting-hole keep-outs, UCC21520 oriented with output side toward FETs and a declared barrier keep-out, NTC near Q2, fan switch at the bottom edge, 123/123 parts placed, no collisions.
Bad: items MAJOR-1/1b/1c, M1, M3. Utilisation 12% shows there is room to tighten.

## 6. Provisional partial score (S1+S2 only; routing/copper/DRC/fab not scored)
Electrical engineering (/30): **21 / 30**
- + correct pin maps (all ICs), correct protection polarities, sound LM5164/TPS54202/INA240/UCC21520 derivations with datasheet citations, correct 51.2 V catch, honest isolation (+ about 22)
- - TVS vs 100 V parts margin and reverse-polarity logic (-2), OV trip margin (-1), no hysteresis/latch and shoot-through blind spot (-2), wrong design_profile (-1), placement of hot loop/gate loop/decaps if not mitigated in routing (-3; may recover partly at the final review)
Evidence & process (/20): **15 / 20**
- + execution log, failure register, timing and stage metrics consistent, UNVERIFIED/TO VERIFY honest, reusable tool fixes with a regression test, HV release explicitly blocked
- - design_profile not synced to the real board, no post-change full test run recorded, no test for pcb_place/pcb_board, stale REQUIREMENTS sections, PLACE-DECAP-010 result not reproducible from evidence (-5)

## 7. Requests for the builder before the final review
1. State the PLACE-DECAP-010 metric; show it evaluated U1/U7/U4 caps; fix or justify distances above.
2. Move gate resistors to the FET gates; move or re-orient FETs/MLCCs to shrink the hot loop (flip Q2 or put MLCCs across the 17 mm gap with several vias to L2).
3. Regenerate design_profile with 160x120, 2 oz outer and real stackup; drop mains overlay for the SELV board or document why it stays.
4. Fix OV reference (e.g. choose trip about 64 V or use a stable reference), add hysteresis or a latch.
5. Replace the reverse-polarity claim with a tested mechanism or a documented limitation; re-evaluate TVS choice.
6. Run the full test suite after the code changes and record it.
