# Profile schema: how DDIS extends DesignProfile

There is one profile system: `desk/profile.py` `DesignProfile`, saved as `projects/<P>/design_profile.json`. DDIS adds one optional field and a compiler; nothing else changes.

## New field

```json
"domain_profile": {
  "primary_archetype": "three_phase_bldc_controller",
  "secondary_archetypes": ["can_bus_interface"],
  "overlays": ["motor_drive", "high_current", "thermal_management", "emi_emc", "can_interface"],
  "component_families": ["mcu", "three_phase_gate_driver", "mosfet", "current_sense_resistor", "dc_link_capacitor", "motor_connector", "can_transceiver", "tvs_diode", ...],
  "rule_ids": ["ELEC-WIDTH-001", "..."],
  "enforced_rule_ids": ["..."], "advisory_rule_ids": ["..."], "unsupported_rule_ids": ["THERM-TJ-050", "ELEC-RATING-007"],
  "classification_status": "CLASSIFIED", "confidence": 0.95,
  "status": "READY | REVIEW_REQUIRED | BLOCKED",
  "library_version": "1.0.0@2026-11-12", "compiled_at": "2026-11-12T06:40:00"
}
```

`domain_profile` is informational: no engine reads numbers from it. Engines keep reading `voltage_rails`, `current_limits_A`, `clearance_condition`, `pollution_degree`, `material_group`, `manufacturing`, `rf_lines`, `diff_pairs`, `keepouts` exactly as before.

## What the compiler sets

| Field | Source | Never |
|---|---|---|
| `voltage_rails`, `current_limits_A` | only from declared requirement fields (`voltage_rails`, `current_limits_A`) or the base profile | invented from the archetype |
| `clearance_condition` | `B4` when `conformal_coating` is declared, else declared or default `B2` | — |
| `pollution_degree`, `material_group` | declared values (PD 1/2 only; 3/4 are not implemented in `desk/ipc.py`) | guessed from environment |
| `layer_count`, `manufacturing` | 4 layers + JLCPCB 4-layer preset when an RF / high-speed / precision-analog overlay is active, else 2 layers | — |
| `critical_nets`, `keepouts` | declared lists | — |
| `unknown_current_policy` | always `fail` | relaxed |

## Backward compatibility

* Profiles written before DDIS load unchanged (`domain_profile` defaults to `{}`), verified by `tests/test_profile_compiler.py`.
* A profile with `domain_profile` loads in older DESK code paths that ignore unknown keys through `from_dict` because the field exists on the dataclass.
* `DesignProfile.compute_hash` is unchanged; `domain_profile` is included in `to_dict`, so the hash changes when the compile result changes, which is intended (zones and plans keyed on the hash are invalidated).

## Versioning

`library/pcb_domains/taxonomy.json` carries `schema_version` and `generated`; every archetype, overlay, family document and rule carries `schema_version`/`version`. `DomainLibrary.version` is recorded in every compiled profile. Invalid versions or unknown references fail `validate_library` (`python tools/desk.py domains check`).
