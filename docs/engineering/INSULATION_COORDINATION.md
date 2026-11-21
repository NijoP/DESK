# Insulation coordination engine (`desk/insulation`)

Status: software-tested with fixtures; not validated on a live design. No output of this engine is a safety
compliance statement.

Standard reference: IEC 60664-1:2020 (Edition 3.0) including Amendment 1:2025, where applicable. DESK does not hold
the licensed text.

## What it computes

Two quantities, two code paths, two result types (`ClearanceResult`, `CreepageResult`). They are never mixed.

| | Clearance (`evaluate_clearance`) | Creepage (`evaluate_creepage`) |
|---|---|---|
| Distance | through air | along the insulating surface |
| Voltage input | rated impulse voltage (declared, or overvoltage category + mains voltage through the rated-impulse table) | working voltage, V RMS |
| Other inputs | insulation type, pollution degree, altitude | insulation type, pollution degree, material group (or CTI through the CTI table), coating |
| Altitude correction | yes (altitude table above the table's altitude basis) | never |
| Reinforced | dataset rule `clearance_reinforced` (`impulse_step` or `factor`) | dataset rule `creepage_reinforced_factor` |
| Functional | basic lookup, status capped at PROVISIONAL (DESK assumption) | same column as basic (per the table reference) |

Each result has `value_mm` (derived from the dataset with every input declared), `guidance_mm` (conservative
provisional spacing for preliminary layout guidance: the value, or the worst case over undeclared inputs when the
dataset covers every case, else none), `status`, `references`, `standard`, `dataset_id`, `assumptions`,
`missing_inputs` and the `provenance` of every value used.

Status:

- `VERIFIED-AGAINST-TABLE`: every value used is a VERIFIED dataset cell hit exactly. It is not a compliance claim.
- `PROVISIONAL`: derived from the dataset, but a value is PROVISIONAL, the lookup rounded up, or a DESK assumption applies.
- `UNVERIFIED`: a required input, table or rule is missing. A missing input is never defaulted.

Coating is recorded but never credited (IEC 60664-3 is out of scope). The uncoated value is used.

## Data

`desk/insulation/data/iec60664-1_2020_a1_2025.provisional.json` ships only values the repository already held (the
creepage table formerly in `desk/ipc.py` and the reinforced-creepage x2 rule formerly in `desk/spacing.py`), all
PROVISIONAL with their source. It has no clearance, rated-impulse, altitude or CTI table, so clearance is UNVERIFIED
until the owner supplies them.

To supply the purchased table data, write a dataset in the same schema (`desk.insulation.dataset/1`, documented in
`desk/insulation/tables.py`), mark each transcribed value `"status": "VERIFIED"` with `verified_by`, and set
`DESK_INSULATION_DATASET` to its path (or call `load_dataset(path)`). No code change is needed. The loader rejects
values without provenance, VERIFIED values without a verifier, misaligned rows and tables that decrease.

The legacy router rule (`ipc.creepage_mm`, `spacing.creepage_for_barrier`) always reads the shipped dataset, so
configuring an owner dataset never moves an existing routing rule.

## Consumers

- `DesignProfile.insulation_environment` (new, optional): inputs shared by every barrier. Barrier keys
  (`working_voltage_v`, `insulation`, `pollution_degree`, `material_group`, `rated_impulse_voltage_v`,
  `overvoltage_category`, `mains_voltage_v`, `cti`, `altitude_m`, `coating`, `environment`) override it. Legacy
  barrier defaults are not inputs.
- `DesignProfile.insulation_assessments()`, `spacing.assess_barrier()`, `SpacingRequirement.insulation` (when a
  barrier separates the pair) and `RoutingPlan.insulation` report the assessment. None of them changes a router rule.

## Compliance language

Only `InsulationAssessment.compliance_statement(signoff)` / `to_dict(signoff)` may say "compliant", and only with an
`EngineeringSignoff` record whose `assessment_digest` and `dataset_id` match the assessment and when both results are
VERIFIED-AGAINST-TABLE. Engineering review is required before safety compliance sign-off.
