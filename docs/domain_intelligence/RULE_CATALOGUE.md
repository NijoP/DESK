# Rule catalogue

66 rules across 10 rule sets. Mode says what DESK does; status says how far the claim is checked.

| Rule | Name | Category | Severity | Mode | Subsystem | Status | Evaluator | References |
|---|---|---|---|---|---|---|---|---|
| `BAT-CHEM-130` | Charge voltage derived from the declared chemistry | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.charge_voltage` | IEC-62133-2, MFR-DATASHEET |
| `BAT-NTC-132` | Thermistor at the cell feeding the charger/BMS | electrical | ERROR | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.family_present` | IEC-62133-2 |
| `BAT-PROT-131` | Cell protection present and independent of the charger | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.family_present` | IEC-62133-2, UL-2054 |
| `BOOST-SC-122` | Boost output short-circuit path acknowledged (disconnect switch or accepted) | electrical | WARNING | ADVISORY | none | ADVISORY | `advisory` | MFR-DATASHEET |
| `COPPER-ANT-045` | No copper in the antenna keep-out on any layer | copper | BLOCKING | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.zone_boundary` | MFR-DATASHEET |
| `COPPER-BARRIER-044` | No copper across the isolation barrier | copper | BLOCKING | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.zone_boundary` | IEC-60664-1 |
| `COPPER-GND-040` | Continuous ground plane; stitching vias near fast signals | copper | ERROR | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.ground_plane` | IPC-2221B |
| `COPPER-ISLAND-043` | No unconnected copper islands | copper | ERROR | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.islands` |  |
| `COPPER-RELIEF-042` | Thermal relief only where hand-soldered; solid on power pads | copper | WARNING | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.connection_rule` | MFR-DATASHEET |
| `COPPER-THERMVIA-046` | Thermal via array under exposed pads | copper | WARNING | ADVISORY | copper | ADVISORY | `advisory` | JESD51, MFR-DATASHEET |
| `COPPER-ZONE-041` | Zone clearance to other nets from the profile, never a literal | copper | BLOCKING | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.zone_clearance` | IPC-2221B, IEC-60664-1 |
| `DCDC-ISAT-120` | Inductor saturation current above the peak inductor current | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.inductor_margin` | MFR-DATASHEET |
| `DCDC-VIN-121` | Input voltage range inside the converter IC rating | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.range_within` | MFR-DATASHEET |
| `ELEC-CLEAR-003` | Electrical clearance from working voltage (IPC-2221B Table 6-1) | electrical | BLOCKING | ENFORCED | routing.clearance | OFFLINE_TESTED | `desk.profile.clearance` | IPC-2221B, JLCPCB-CAPABILITIES |
| `ELEC-CREEP-004` | Creepage from working voltage, pollution degree and material group (IEC 60664-1 Table F.4) | electrical | BLOCKING | ENFORCED | routing.clearance | OFFLINE_TESTED | `desk.profile.creepage` | IEC-60664-1 |
| `ELEC-DROP-006` | Voltage drop on power paths within budget | electrical | ERROR | ENFORCED | power.distribution | OFFLINE_TESTED | `desk.power_distribution.voltage_drop` | IPC-2221B |
| `ELEC-RATING-007` | Component voltage/current ratings exceed applied stress with margin | electrical | ERROR | UNSUPPORTED | none | ADVISORY | `advisory` | MFR-DATASHEET |
| `ELEC-UNKNOWN-002` | Unknown electrical inputs fail closed | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.profile.validate_electrical_inputs` | IPC-2221B |
| `ELEC-VIA-005` | Via ampacity and parallel via count | electrical | ERROR | ADVISORY | routing.vias | IMPLEMENTED | `desk.ipc.via_current` | IPC-2221B |
| `ELEC-WIDTH-001` | Trace width from declared current (IPC-2221) | electrical | BLOCKING | ENFORCED | routing.width | OFFLINE_TESTED | `desk.ipc.trace_width` | IPC-2221B, JLCPCB-CAPABILITIES |
| `EMI-ESD-062` | ESD protection on every externally accessible signal | emi_emc | ERROR | ADVISORY | none | ADVISORY | `advisory` | IEC-61000-4-2 |
| `EMI-FILTER-061` | Input filter footprints when the product is EMC tested | emi_emc | WARNING | ADVISORY | none | ADVISORY | `advisory` | CISPR-32, CISPR-25 |
| `EMI-LOOP-060` | Hot-loop area minimised and recorded | emi_emc | ERROR | ADVISORY | placement | ADVISORY | `advisory` | CISPR-32 |
| `EMI-RFHARM-064` | Switching harmonics out of the radio band | emi_emc | WARNING | ENFORCED | none | OFFLINE_TESTED | `desk.rules.harmonic_check` |  |
| `EMI-SURGE-063` | Surge/burst protection at every field terminal | emi_emc | ERROR | ADVISORY | none | ADVISORY | `advisory` | IEC-61000-4-5, IEC-61000-4-4, ISO-7637-2 |
| `LORA-BAND-110` | Matching network and band plan per region | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.band_plan` | ETSI-EN-300-220, LoRaWAN-RP002, FCC-Part-15 |
| `MAINS-DECL-160` | Every mains/HV net declared in voltage_rails before any spacing is derived | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.profile.validate_electrical_inputs` | IEC-60664-1 |
| `MAINS-FUSE-161` | Fuse first after the mains connector; MOV after the fuse | electrical | ERROR | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.family_present` | IEC-62368-1, IEC-60335-1 |
| `MAINS-INS-163` | Insulation grade (basic/double/reinforced) declared for the barrier | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.field_present` | IEC-62368-1, IEC-60664-1 |
| `MAINS-XDIS-162` | Discharge resistor across X capacitors | electrical | ERROR | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.family_present` | IEC-62368-1 |
| `MCU-RADIO-101` | 3.3 V rail delivers the radio TX peak with headroom | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.rail_headroom` | MFR-DATASHEET |
| `MCU-STRAP-100` | Strapping/boot pins at the documented level at reset | electrical | BLOCKING | ADVISORY | quality.gate | IMPLEMENTED | `desk.spec.strap_pins` | MFR-DATASHEET |
| `MCU-USB-102` | USB D+/D- as a 90 ohm pair with ESD at the connector | routing | ERROR | ADVISORY | routing | IMPLEMENTED | `desk.routing.diff_pair` | USB-2.0, IEC-61000-4-2 |
| `MFG-COAT-073` | Conformal coating changes the clearance condition (B4) | manufacturing | WARNING | ENFORCED | routing.clearance | OFFLINE_TESTED | `desk.profile.clearance` | IPC-2221B |
| `MFG-DRILL-071` | Via drill and annular ring within the fabricator capability | manufacturing | ERROR | ENFORCED | routing | IMPLEMENTED | `desk.profile.manufacturing_floor` | JLCPCB-CAPABILITIES |
| `MFG-EDGE-072` | Copper setback from the board edge | manufacturing | ERROR | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.edge_setback` | JLCPCB-CAPABILITIES |
| `MFG-MIN-070` | Trace width and clearance at or above the fabricator minimum | manufacturing | BLOCKING | ENFORCED | routing | OFFLINE_TESTED | `desk.profile.manufacturing_floor` | JLCPCB-CAPABILITIES |
| `MFG-SLOT-074` | Slot the board where creepage cannot be met in the barrier | manufacturing | WARNING | ADVISORY | none | ADVISORY | `advisory` | IEC-60664-1 |
| `MOTOR-OC-141` | Over-current trip wired from the sense amplifier to the driver fault input | electrical | ERROR | ADVISORY | none | ADVISORY | `advisory` | MFR-DATASHEET |
| `MOTOR-PEAK-140` | Peak phase current declared; devices and copper rated with margin | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.peak_margin` | MFR-DATASHEET, IPC-2221B |
| `PLACE-ANT-014` | Antenna at the board edge with the datasheet keep-out | placement | BLOCKING | ENFORCED | placement | OFFLINE_TESTED | `desk.placement.keepout` | MFR-DATASHEET |
| `PLACE-DECAP-010` | Decoupling capacitor within 2 mm of the supply pin | placement | ERROR | ENFORCED | placement | OFFLINE_TESTED | `desk.placement.decoupling_proximity` | MFR-DATASHEET |
| `PLACE-FB-013` | Feedback network at the FB pin, away from the switch node and inductor | placement | WARNING | ADVISORY | placement | ADVISORY | `advisory` | MFR-DATASHEET |
| `PLACE-HOTLOOP-012` | Converter hot loop minimal: Cin, switches and rectifier adjacent | placement | ERROR | ADVISORY | placement | IMPLEMENTED | `desk.placement.group_proximity` | MFR-DATASHEET |
| `PLACE-ISO-016` | Only isolating components bridge the isolation barrier | placement | BLOCKING | ENFORCED | placement | OFFLINE_TESTED | `desk.placement.keepout` | IEC-60664-1, IEC-62368-1 |
| `PLACE-KEEPOUT-011` | Keep-outs (antenna, barrier, mechanical) are empty on every layer | placement | BLOCKING | ENFORCED | placement | OFFLINE_TESTED | `desk.placement.keepout` | MFR-DATASHEET |
| `PLACE-SENSE-018` | Current-sense resistor with Kelvin pads adjacent to its amplifier | placement | ERROR | ADVISORY | placement | IMPLEMENTED | `desk.placement.group_proximity` | MFR-DATASHEET |
| `PLACE-THERM-017` | Heat-sensitive parts away from dissipating parts | placement | WARNING | ADVISORY | placement | ADVISORY | `advisory` | JESD51 |
| `PLACE-XTAL-015` | Crystal and load capacitors within 5 mm of the oscillator pins | placement | WARNING | ADVISORY | placement | IMPLEMENTED | `desk.placement.group_proximity` | MFR-DATASHEET |
| `PWR-ROUTE-170` | High-current routing constraint: polygons, parallel vias, Kelvin sense | routing | BLOCKING | ENFORCED | power.distribution | OFFLINE_TESTED | `desk.power_distribution.strategy` | IPC-2221B, IPC-2152 |
| `ROUTE-DIFF-021` | Differential pairs at the interface impedance with matched length | routing | ERROR | ADVISORY | routing | IMPLEMENTED | `desk.routing.diff_pair` | USB-2.0, IEEE-802.3, PCIe-CEM, ISO-11898-2, TIA-485-A |
| `ROUTE-ENC-029` | Encoder/hall signals routed away from phase copper and filtered | routing | WARNING | ADVISORY | routing | ADVISORY | `advisory` |  |
| `ROUTE-GATE-028` | Gate drive loops short with return on the adjacent layer | routing | WARNING | ADVISORY | routing | ADVISORY | `advisory` | MFR-DATASHEET |
| `ROUTE-GUARD-030` | Guard rings on high-impedance analog nodes | routing | WARNING | ADVISORY | routing | ADVISORY | `advisory` |  |
| `ROUTE-HV-025` | No vias or signals inside the isolation barrier | routing | BLOCKING | ENFORCED | routing | OFFLINE_TESTED | `desk.routing.keepout` | IEC-60664-1 |
| `ROUTE-KELVIN-024` | Sense traces from the inner pad edges; no current in sense traces | routing | ERROR | ADVISORY | routing | ADVISORY | `advisory` | MFR-DATASHEET |
| `ROUTE-POLY-026` | Nets above 3 A as polygons sized by IPC-2221 | routing | ERROR | ENFORCED | power.distribution | OFFLINE_TESTED | `desk.power_distribution.strategy` | IPC-2221B |
| `ROUTE-PRIO-020` | Route in priority order: diff pairs/RF, high-current, critical, power, signal | routing | ERROR | ENFORCED | routing | OFFLINE_TESTED | `desk.routing.priority` | IPC-2221B |
| `ROUTE-RETURN-027` | Return path continuity: no high-speed or switching nets across plane splits | routing | ERROR | ENFORCED | copper | OFFLINE_TESTED | `desk.copper.return_path` | IPC-2221B |
| `ROUTE-RF-022` | RF feed as a 50 ohm line with ground fence and no vias | routing | BLOCKING | ADVISORY | routing | IMPLEMENTED | `desk.routing.rf_line` | MFR-DATASHEET |
| `ROUTE-SW-023` | Switch node short, wide, single layer; never under feedback | routing | ERROR | ADVISORY | routing | ADVISORY | `advisory` | MFR-DATASHEET |
| `THERM-COPPER-051` | Copper area per watt from the device datasheet | thermal | WARNING | ADVISORY | copper | ADVISORY | `advisory` | MFR-DATASHEET |
| `THERM-DERATE-052` | Continuous dissipators derated to 60-70 % of rating | thermal | WARNING | ADVISORY | none | ADVISORY | `advisory` | MFR-DATASHEET |
| `THERM-TJ-050` | Junction temperature below the datasheet limit at max ambient | thermal | ERROR | UNSUPPORTED | none | ADVISORY | `advisory` | JESD51, MFR-DATASHEET |
| `USBC-CC-150` | CC pull-down/up configuration matches the port role | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.usbc_cc` | USB-Type-C-2.2 |
| `USBC-VBUS-151` | VBUS components rated for the maximum negotiated voltage | electrical | BLOCKING | ENFORCED | quality.gate | OFFLINE_TESTED | `desk.rules.range_within` | USB-PD-3.1 |
