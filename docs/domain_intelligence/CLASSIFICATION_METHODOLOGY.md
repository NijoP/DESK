# Classification methodology

`desk/domain_intelligence/classifier.py`. Deterministic; the same input always yields the same output. An LLM may be used upstream to turn a conversation into the structured dict, but the dict then goes through exactly the same scoring as plain text.

## 1. Requirement extraction

`extract_requirements(source)` accepts text or a dict (`text` plus declared fields). It produces normalised features:

| Feature | How |
|---|---|
| `input_voltage_v`, `voltages_v` | numbers followed by V/mV/kV; kV values in an isolation context become `isolation_voltage_v`, not input voltage |
| `current_a`, `peak_current_a`, `continuous_current_a` | numbers with A/mA/uA; "peak" / "continuous" words tag them |
| `power_w`, `rf_frequency_hz`, `switching_frequency_hz` | W/kW, MHz/GHz, kHz with switching context |
| `protocols` | usb, can, rs485, ethernet, gigabit, wifi, ble, lora, lte, gnss, hdmi, mipi, pcie, ddr, sata, i2c, spi, uart, zigbee, uwb, subghz, poe, lin, i2s |
| `power_source` | battery, usb, mains, solar, vehicle, poe, dc_input |
| `motor`, `converter`, `chemistry`, `cells` | bldc/brushed/stepper/servo/ac/solenoid/fan; buck/boost/.../pfc; li_ion/li_po/lifepo4/...; "4S", "2 cells", "single cell" |
| `mains`, `isolation` | mains words or >= 85 V with "AC"; "isolated"/"galvanic"/"SELV" true, "non-isolated"/"transformerless" false |
| `max_ambient_c`, `environment`, `conformal_coating`, `usb_role`, `usb_pd`, `rf_region`, `resolution_bits`, `signal_type`, `enclosure`, `manufacturing` | keyword and number patterns |

Declared dict fields always override extracted ones and are listed in `provided_fields`.

## 2. Scoring

Every archetype carries a `classification` block: weighted keywords and feature ranges (`library/pcb_domains/archetypes/*.json`). Score = sum of matched keyword weights (whole-word match; a keyword ending in a digit, such as `stm32`, may continue with a suffix) plus feature points: input voltage within range +3 (far outside −2), protocol intersections +3 each (cap 6), power source +3, RF band +4 (outside −3), motor +4 (wrong type −3), converter +4, mains +4 (no mains source −2), isolation match +2 (contradiction −3), cells +2, power +2. Every point is recorded as a reason or penalty.

Interface archetypes (`interfaces_comms`) describe a feature, not a board: when one tops the list but the text names a controller (MCU, STM32, ESP32 ...), the best controller-class candidate becomes primary and the interface becomes a secondary archetype. The margin is then computed without the demoted interface.

## 3. Status and confidence

| Status | Condition |
|---|---|
| CLASSIFIED | top score >= 8 and margin over the runner-up >= 3; confidence 0.5 + 0.04 x margin + 0.01 x score (max 0.95) |
| REVIEW_REQUIRED | top score >= 4 but the margin is small, or a safety conflict exists (below) |
| UNCLASSIFIED | top score < 4; the compiler blocks |

## 4. Safety conflicts that are never resolved silently

* Mains or HV detected (or a mains archetype scoring >= 4) while the primary is not a mains archetype: `mains_safety_isolation` overlay is added, a conflict is recorded, status drops to REVIEW_REQUIRED.
* A mains archetype is primary but the text also describes a controller or sensor product: conflict + REVIEW_REQUIRED (is this the supply section or a mains-powered device?).
* A motor is mentioned but the primary is not a motor archetype: `motor_drive` overlay added, conflict recorded.

## 5. Overlays, families, missing information

Overlays = the primary archetype's typical overlays plus every overlay whose `applies_when` conditions match the features. Required component families = the primary's required roles plus the families each overlay adds (roles only, never parts). Missing information = a fixed checklist (supply, current/power, power source, interfaces, environment, enclosure, manufacturing) plus the primary archetype's typical input requirements, plus domain-specific fail-closed items (`voltage_rails` for mains, chemistry for batteries).

## 6. Output

`ClassificationResult`: primary, secondary, overlays, families, ranked candidates with reasons/penalties, missing information, conflicts, confidence, status, evidence, features. `python tools/desk.py domains classify "<text>" --json` prints it; `classify_requirements` exposes it to the agent loop.

## 7. Measured behaviour (2026-11-12)

18 representative sentences classify to the intended archetype (`tests/test_requirement_classifier.py`); nine multi-domain cases compile end to end (`tests/test_cross_domain_cases.py`). Median classification 19.6 ms warm, first call ~280 ms (file loads and regex compilation).
