"""DESK insulation coordination (IEC 60664-1:2020 + A1:2025 as the reference where applicable).

    from desk import insulation as INS
    a = INS.assess(INS.InsulationInputs(insulation_type="basic", working_voltage_v=230, pollution_degree=2,
                                        material_group="IIIb", coating="none", rated_impulse_voltage_v=2500,
                                        altitude_m=500))
    a.clearance.status, a.creepage.status, a.creepage.guidance_mm, a.compliance_statement()

engine.py  separate clearance / creepage evaluation, statuses, assessment
tables.py  versioned datasets with per-value provenance and the loader (DESK_INSULATION_DATASET)
signoff.py engineering sign-off records; the only path to a compliance statement

Software-tested with fixtures; not validated on a live design.
"""
from desk.insulation.engine import (NOT_A_COMPLIANCE_CLAIM, ClearanceResult, CreepageResult, InsulationAssessment,
                                    InsulationInputs, InsulationType, Status, assess, creepage_value_mm,
                                    evaluate_clearance, evaluate_creepage)
from desk.insulation.signoff import EngineeringSignoff, evaluate_signoff
from desk.insulation.tables import (DEFAULT_DATASET_PATH, Dataset, default_dataset, load_dataset, parse_dataset)

__all__ = ["NOT_A_COMPLIANCE_CLAIM", "ClearanceResult", "CreepageResult", "InsulationAssessment", "InsulationInputs",
           "InsulationType", "Status", "assess", "creepage_value_mm", "evaluate_clearance", "evaluate_creepage",
           "EngineeringSignoff", "evaluate_signoff", "DEFAULT_DATASET_PATH", "Dataset", "default_dataset",
           "load_dataset", "parse_dataset"]
