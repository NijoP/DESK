# Acceptance Criteria - ESP32-S3 Development Board

## Stage 1: Schematic Creation and Validation (45 minutes)

### Must Pass (Hard Gates)
- [ ] **Complete Required Blocks**: All 15 essential circuit blocks implemented
  - [ ] ESP32-S3 module with correct pin mapping
  - [ ] USB-C power and data interface
  - [ ] USB ESD protection (4-channel on D+/D-/CC1/CC2)
  - [ ] 5V input distribution with reverse polarity protection
  - [ ] 3.3V regulation (LDO with enable, input/output caps)
  - [ ] Input/output capacitors per datasheet (10µF + 1µF + 100nF per rail)
  - [ ] Reset circuit (EN pin, RC delay, button)
  - [ ] Boot/strapping circuit (GPIO0 button, strapping resistors)
  - [ ] Programming interface (native USB on GPIO19/20)
  - [ ] BOOT and RESET buttons (accessible, labeled)
  - [ ] GPIO header interfaces (all available GPIOs broken out)
  - [ ] Power/status LED (3.3V rail + GPIO48 or dedicated)
  - [ ] Test points (VBUS, 5V, 3.3V, GND, EN, BOOT, USB D+/D-)
  - [ ] Protection (VBUS TVS, polyfuse, GPIO ESD optional)
  - [ ] Decoupling (module VDD pins, regulator, USB PHY)

- [ ] **Correct Component Identities**: Every component has verified LCSC part number
  - [ ] Module: ESP32-S3-WROOM-1 variant with LCSC PN
  - [ ] USB-C: Receptacle with LCSC PN
  - [ ] Regulator: LDO with LCSC PN
  - [ ] ESD: TVS array with LCSC PN
  - [ ] All passives: LCSC PN with correct package/value
  - [ ] Buttons/LEDs/Headers: LCSC PN

- [ ] **Verified Critical Pin Mappings**:
  - [ ] ESP32-S3 USB PHY: GPIO19 (D-), GPIO20 (D+)
  - [ ] ESP32-S3 EN pin: Reset circuit
  - [ ] ESP32-S3 GPIO0: BOOT button + pull-up
  - [ ] ESP32-S3 Strapping pins: Correct pull-up/down per datasheet
  - [ ] ESP32-S3 VDD/VDD_SPI/GND: Power connections
  - [ ] USB-C: VBUS, GND, D+, D-, CC1, CC2, SHIELD
  - [ ] Regulator: VIN, VOUT, EN, GND
  - [ ] Headers: All GPIO pins mapped to correct header positions

- [ ] **Correct Supply Topology**:
  - [ ] VBUS → Polyfuse → Schottky → 5V rail → LDO → 3.3V rail
  - [ ] 3.3V rail → Module VDD, VDD_SPI, regulator output caps
  - [ ] 5V rail → Header 5V pins, USB-C VBUS passthrough
  - [ ] GND: Single net, star-connected at USB-C shield

- [ ] **No Unresolved Critical ERC Errors**:
  - [ ] No floating input pins (except intentional)
  - [ ] No shorted power nets
  - [ ] No missing pin connections on critical components
  - [ ] No incorrect pin types (output driving output, etc.)
  - [ ] All power pins connected to appropriate rails

- [ ] **ERC Evidence**: ERC report generated and saved to `schematic/reports/erc_report.txt`

- [ ] **Native Schematic Saved**: EasyEDA schematic document saved in project

### Should Pass (Quality Gates)
- [ ] Schematic organized logically (functional blocks separated)
- [ ] Net labels clear and consistent
- [ ] Component reference designators follow standard (U, J, R, C, L, D, Q, SW, LED, TP)
- [ ] Power flags/power ports used correctly
- [ ] No duplicate reference designators
- [ ] Sheet size appropriate (A4 or similar)

## Stage 2: Component Placement (45 minutes)

### Must Pass (Hard Gates)
- [ ] **Complete Component Placement**: All components placed on PCB
- [ ] **No Critical Component Collisions**: No overlapping pads/courtyards
- [ ] **Mechanical Constraints Satisfied**:
  - [ ] USB-C at board edge, centered on short side
  - [ ] Mounting holes at 4 corners (3.2mm diameter)
  - [ ] Board outline rectangular with rounded corners
  - [ ] Components within board outline (courtyard clearance >0.5mm)
- [ ] **Decoupling Proximity**: Decoupling caps within 2mm of module VDD pins
- [ ] **Boot/Reset Button Access**: Buttons at board edge, accessible
- [ ] **GPIO Header Alignment**: Headers aligned on 2.54mm grid, long edges
- [ ] **Thermal Considerations**: Regulator on copper pour for heatsinking
- [ ] **Routing Corridor Planning**: Space for USB diff pair, power routing
- [ ] **Escape Feasibility**: All module pads have via escape routes
- [ ] **Antenna Keepout**: No copper/components in antenna zone (per datasheet)
- [ ] **Placement Accepted by Deterministic Checks**: DESK placement validation passes
- [ ] **Native PCB Placement Saved**: EasyEDA PCB document saved

### Should Pass (Quality Gates)
- [ ] Functional grouping visible (power, USB, MCU, headers)
- [ ] Visual symmetry where appropriate
- [ ] Consistent header pitch and alignment
- [ ] Readable reference designators (not overlapping pads)
- [ ] Logical pin labels on silkscreen
- [ ] Balanced density across board

## Stage 3: PCB Routing (90 minutes)

### Must Pass (Hard Gates)
- [ ] **All Required Nets Physically Connected**:
  - [ ] USB D+/D- differential pair (module ↔ USB-C)
  - [ ] Power nets (VBUS, 5V, 3.3V, GND)
  - [ ] Critical control (EN, BOOT, strapping)
  - [ ] All GPIO header pins to module
  - [ ] LED/resistor connections
  - [ ] Test point connections
- [ ] **No Unintended Shorts**: Zero DRC short violations
- [ ] **No New Critical DRC Violations**: Clearance, trace width, via size
- [ ] **Correct Via and Layer Transitions**: Signal integrity preserved
- [ ] **USB Constraints Reviewed**:
  - [ ] D+/D- length matched (<5mm difference)
  - [ ] D+/D- spacing consistent (approximate 90Ω)
  - [ ] D+/D- referenced to GND plane
  - [ ] No stubs on USB lines
- [ ] **Physical Pad-to-Pad Verification Passed**: Connectivity matrix 100% for populated nets
- [ ] **Routing Record Saved**: Routing passes documented in `pcb/routing/`

### Should Pass (Quality Gates)
- [ ] Power traces wide enough (0.3mm+ for 500mA)
- [ ] GND return paths short and direct
- [ ] Minimal via count on critical signals
- [ ] No acute angle traces (45° preferred)
- [ ] Teardrops on power pad/via connections
- [ ] Diff pair routing parallel where possible

## Stage 4: Copper Pouring (30 minutes)

### Must Pass (Hard Gates)
- [ ] **Correct Copper Zones**: GND pour on top and bottom layers
- [ ] **Correct Layer Assignments**: GND on inner layers if 4-layer
- [ ] **No Critical Copper Shorts**: Copper-to-copper clearance OK
- [ ] **No Unresolved Floating Copper**: All islands removed or connected
- [ ] **Verified Ground Connectivity**: All GND pads connected to pour
- [ ] **Appropriate Power Distribution**: 3.3V/5V pours where beneficial
- [ ] **Ground Stitching**: Stitching vias at ~5mm grid
- [ ] **Thermal Reliefs**: Through-hole pads have thermal relief
- [ ] **Copper Clearances**: >0.15mm to non-GND nets
- [ ] **Island Removal**: No floating copper islands >2mm²
- [ ] **Antenna Keepout Respected**: No copper in antenna zone
- [ ] **Native Copper Saved**: EasyEDA PCB with copper zones saved

### Should Pass (Quality Gates)
- [ ] Even copper distribution
- [ ] No narrow copper slivers
- [ ] Proper edge clearance (0.5mm+ from board edge)
- [ ] Via stitching at layer transitions

## Stage 5: Manufacturing Preflight (15 minutes)

### Must Pass (Hard Gates)
- [ ] **PCB Dimensions**: Within JLCPCB limits (max 500×500mm standard)
- [ ] **Board Outline**: Closed polygon, no self-intersections
- [ ] **Layer Count**: 2 or 4 layers as designed
- [ ] **Clearance**: ≥0.127mm (5mil) all nets
- [ ] **Trace Widths**: ≥0.127mm (5mil) signals, ≥0.254mm (10mil) power
- [ ] **Drill Sizes**: ≥0.2mm (8mil) vias, ≥0.3mm (12mil) component holes
- [ ] **Via Geometry**: 0.3mm drill / 0.6mm pad standard
- [ ] **Solder Mask**: Openings on all pads, no mask between fine-pitch pads
- [ ] **Silkscreen**: No silk on pads, readable text (≥0.8mm height)
- [ ] **Copper-to-Edge**: ≥0.5mm clearance
- [ ] **Gerbers Generated**: All layers (GTL, GBL, GTS, GBS, GTO, GBO, GM1, GM2, GTP, GBP, GML)
- [ ] **Drill Files Generated**: Excellon format (PTH + NPTH)
- [ ] **BOM Generated**: LCSC part numbers, quantities, references
- [ ] **LCSC Identifiers**: All components have valid LCSC PN
- [ ] **CPL/Centroid Generated**: If assembly considered
- [ ] **Component Orientation**: Consistent rotation for assembly
- [ ] **No Unresolved Critical Manufacturing Blockers**

### Should Pass (Quality Gates)
- [ ] Gerber viewer inspection clean
- [ ] Drill file matches via/hole count
- [ ] BOM cost within budget
- [ ] All components in stock at LCSC

## Overall Success Criteria

### SUCCESS Verdict
- All 5 stages pass Must Pass gates
- Total engineering time ≤ 225 minutes
- Critical electrical correctness verified
- Complete required physical connectivity
- No unresolved critical DRC blockers
- Manufacturing package validated

### TIME_TARGET_FAILED Verdict
- Engineering quality achieved but time > 225 minutes

### PARTIAL_COMPLETION Verdict
- Some stages incomplete, work preserved, documented

### FAILURE Verdict
- Time met but critical engineering quality gates failed