"""Unified Mental-Model Registry for DESK.
Maintains versioned engineering mental models across the 6 primary domains:
M1: Schematic Intelligence
M2: Component Placement Intelligence
M3: Routing Intelligence
M4: Copper and Ground Intelligence
M5: Electrical and Manufacturing Intelligence
M6: Verification and Review Intelligence

Zero external dependencies.
"""
from typing import Dict, List, Optional, Any
from desk.mental.models import MentalModel

class MentalModelRegistry:
    _models: Dict[str, MentalModel] = {}

    @classmethod
    def register(cls, model: MentalModel):
        cls._models[model.model_id] = model

    @classmethod
    def get(cls, model_id: str) -> Optional[MentalModel]:
        return cls._models.get(model_id)

    @classmethod
    def list_models(cls) -> List[str]:
        return sorted(list(cls._models.keys()))

    @classmethod
    def initialize_defaults(cls):
        """Populate the 6 authoritative engineering mental models."""
        if cls._models:
            return

        # ------------------------------------------------------------- M1: SCHEMATIC
        cls.register(MentalModel(
            model_id="M1_SCHEMATIC",
            version="1.0.0",
            domain="schematic",
            applicability_conditions=[
                "block_spec_generation", "pin_mapping", "component_selection", "passives_dimensioning"
            ],
            required_context=[
                "client_requirements", "block_plan", "voltage_tree", "power_budget", "library_devices"
            ],
            decision_hierarchy=[
                "REQUIREMENT_DECOMPOSITION",
                "VOLTAGE_TREE_AND_POWER_PATHS",
                "PROTECTION_AND_FAILSAFE_DEFAULTS",
                "COMPONENT_AND_PASSIVE_SELECTION",
                "PIN_TYPE_AND_NET_CONNECTIVITY",
                "DATASHEET_FORMULA_QA"
            ],
            hard_constraints={
                "grid_size_mil": 100,
                "frame_title_case": "UPPER",
                "every_pin_accounted": True,
                "no_unresolved_mpn": True,
                "formula_required_for_passives": True,
                "default_off_reset_state": True
            },
            trade_off_priorities=[
                "electrical_correctness",
                "failsafe_reset_behaviour",
                "bom_consolidation",
                "drawing_neatness"
            ],
            output_schema={
                "type": "object",
                "required": ["id", "title", "parts", "ports", "qa"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "parts": {"type": "array"},
                    "ports": {"type": "array"},
                    "qa": {"type": "array"}
                }
            },
            verification_requirements=[
                "tools/lint.py prints PASS",
                "tools/verify.py matches live netlist",
                "zero single-pin nets at sheet acceptance"
            ],
            evidence_sources=["docs/00_REQUIREMENTS.md", "docs/01_MENTAL_MODEL.md", "docs/02_SCHEMATIC_STYLE.md"]
        ))

        # ------------------------------------------------------------- M2: PLACEMENT
        cls.register(MentalModel(
            model_id="M2_PLACEMENT",
            version="1.0.0",
            domain="placement",
            applicability_conditions=["component_placement", "clustering", "mechanical_clearance"],
            required_context=[
                "board_outline_mm", "mounting_holes", "enclosure_keepouts", "dump_pads", "block_specs"
            ],
            decision_hierarchy=[
                "MECHANICAL_ANCHORS (outline, mounting holes, keepouts)",
                "CONNECTORS_AND_TERMINALS (mating envelopes, screwdriver cones)",
                "CRITICAL_ICS_AND_PMICS (pin escape corridors)",
                "FUNCTIONAL_CLUSTERS (power stage, MCU, sensors, RF)",
                "TOPOLOGICAL_PASSIVES (decap <2mm, ESD at connector, crystals)",
                "ROUTABILITY_GATE (ratsnest crossings, escape congestion)"
            ],
            hard_constraints={
                "zero_mating_envelope_intrusion": True,
                "zero_screwdriver_corridor_intrusion": True,
                "footprint_invariants_immutable": True,
                "decap_max_distance_mm": 2.0,
                "esd_max_distance_mm": 3.0,
                "sensor_heat_isolation_mm": 7.0
            },
            trade_off_priorities=[
                "mechanical_access",
                "thermal_isolation",
                "high_speed_loop_area",
                "routing_area_optimisation"
            ],
            output_schema={
                "type": "object",
                "required": ["board_mm", "parts", "passives"],
                "properties": {
                    "board_mm": {"type": "array"},
                    "parts": {"type": "array"},
                    "passives": {"type": "array"}
                }
            },
            verification_requirements=[
                "tools/pcb_check.py --gate passes with 0 errors",
                "footprint invariant check passes for 100% of parts"
            ],
            evidence_sources=["docs/04_PLACEMENT.md", "desk/placement_intel.py"]
        ))

        # ------------------------------------------------------------- M3: ROUTING
        cls.register(MentalModel(
            model_id="M3_ROUTING",
            version="1.0.0",
            domain="routing",
            applicability_conditions=["net_routing", "dsn_tuning", "track_dimensioning", "diff_pairs"],
            required_context=[
                "stackup", "net_graph", "current_limits", "diff_pairs", "rf_lines", "manufacturing"
            ],
            decision_hierarchy=[
                "STAGE_1_GND_PREPARATION (plane access vias & escape stubs)",
                "STAGE_2_CONNECTOR_ESCAPES (fine-pitch breakout)",
                "STAGE_3_CRITICAL_SIGNALS (diff pairs, RF, clocks, analog sense)",
                "STAGE_4_CONTROL_AND_SENSORS (I2C, SPI, GPIO)",
                "STAGE_5_POWER_DISTRIBUTION (profile-driven width & thermal)",
                "STAGE_6_REMAINING_NETS"
            ],
            hard_constraints={
                "no_unintended_shorts": True,
                "no_unconnected_pads": True,
                "profile_driven_widths": True,
                "diff_pair_length_tolerance_respected": True,
                "no_blind_ground_vias": True
            },
            trade_off_priorities=[
                "signal_integrity_and_return_paths",
                "current_capacity",
                "via_count_minimisation",
                "overall_trace_length"
            ],
            output_schema={
                "type": "object",
                "required": ["board_stackup", "stage_nets", "net_constraints"],
                "properties": {
                    "board_stackup": {"type": "array"},
                    "stage_nets": {"type": "object"},
                    "net_constraints": {"type": "object"}
                }
            },
            verification_requirements=[
                "live DRC reports 0 clearance/short violations",
                "all critical nets 100% routed"
            ],
            evidence_sources=["docs/05_ROUTING.md", "desk/router.py"]
        ))

        # ------------------------------------------------------------- M4: COPPER & GROUND
        cls.register(MentalModel(
            model_id="M4_COPPER_GROUND",
            version="1.0.0",
            domain="copper",
            applicability_conditions=["plane_generation", "copper_pour", "stitching_vias", "return_paths"],
            required_context=[
                "stackup", "board_outline_mm", "ground_nets", "power_nets", "keepouts"
            ],
            decision_hierarchy=[
                "REFERENCE_PLANE_ALLOCATION (layer assignment based on actual stackup)",
                "HIGH_CURRENT_POLYGON_ZONES (power rail flooding)",
                "GROUND_FLOOD_AND_ISLAND_REMOVAL",
                "THERMAL_RELIEF_VS_SOLID_CONNECTIONS (solid for high-current, thermal for hand/wave)",
                "STITCHING_VIA_ARRAYS (perimeter and return path continuity)",
                "COPPER_TO_EDGE_CLEARANCE"
            ],
            hard_constraints={
                "ground_continuity_unbroken": True,
                "no_floating_copper_islands": True,
                "copper_to_board_edge_min_mil": 12.0,
                "no_unverified_inner_gnd_assumption": True
            },
            trade_off_priorities=[
                "unbroken_return_paths",
                "power_plane_low_impedance",
                "thermal_dissipation",
                "etching_balance"
            ],
            output_schema={
                "type": "object",
                "required": ["planes", "zones", "stitching_rules"],
                "properties": {
                    "planes": {"type": "array"},
                    "zones": {"type": "array"},
                    "stitching_rules": {"type": "object"}
                }
            },
            verification_requirements=[
                "ground polygon connectivity check 100% verified",
                "zero isolated copper islands exceeding 2.0 mm²"
            ],
            evidence_sources=["docs/05_ROUTING.md", "Master Directive Section 4 (M4)"]
        ))

        # ------------------------------------------------------------- M5: ELECTRICAL & MFG
        cls.register(MentalModel(
            model_id="M5_ELECTRICAL_MFG",
            version="1.0.0",
            domain="mfg",
            applicability_conditions=["clearance_calculation", "drill_selection", "annular_ring", "stackup_eval"],
            required_context=[
                "voltage_rails", "current_limits", "manufacturing_profile", "stackup"
            ],
            decision_hierarchy=[
                "MANUFACTURER_CAPABILITY_LIMITS (min trace, clearance, drill, annular ring)",
                "IPC_2152_CURRENT_AND_TEMPERATURE_RISE",
                "IPC_2221_VOLTAGE_CLEARANCE_AND_CREEPAGE",
                "CONTROLLED_IMPEDANCE_CALCULATION (dielectric height & er)",
                "ASSEMBLY_AND_SOLDERMASK_CONSTRAINTS"
            ],
            hard_constraints={
                "trace_width_gte_mfg_min": True,
                "clearance_gte_mfg_min": True,
                "drill_gte_mfg_min": True,
                "annular_ring_gte_mfg_min": True,
                "aspect_ratio_lte_mfg_max": True
            },
            trade_off_priorities=[
                "fabrication_yield",
                "electrical_safety_margin",
                "board_density",
                "fabrication_cost"
            ],
            output_schema={
                "type": "object",
                "required": ["rules", "mfg_limits", "impedance_targets"],
                "properties": {
                    "rules": {"type": "object"},
                    "mfg_limits": {"type": "object"},
                    "impedance_targets": {"type": "object"}
                }
            },
            verification_requirements=[
                "all geometries strictly satisfy target manufacturer parameters"
            ],
            evidence_sources=["IPC-2152", "IPC-2221", "Manufacturer Capability Catalog"]
        ))

        # ------------------------------------------------------------- M6: VERIFICATION & REVIEW
        cls.register(MentalModel(
            model_id="M6_VERIFICATION_REVIEW",
            version="1.0.0",
            domain="verification",
            applicability_conditions=["final_acceptance", "design_review", "manufacturing_release"],
            required_context=[
                "schematic_netlist", "pcb_dump", "drc_results", "design_profile", "manifest"
            ],
            decision_hierarchy=[
                "HARD_ACCEPTANCE_GATES (non-negotiable pass/fail)",
                "WEIGHTED_QUALITY_SCORING (optimisation metric)",
                "RESIDUAL_ENGINEERING_RISK_AUDIT"
            ],
            hard_constraints={
                "zero_unintended_shorts": True,
                "zero_unconnected_pads": True,
                "zero_clearance_violations": True,
                "all_critical_nets_routed": True,
                "stackup_assignment_valid": True,
                "copper_zone_connected": True
            },
            trade_off_priorities=[
                "deterministic_hard_gates_before_weighted_score",
                "traceability_to_requirements",
                "corroborated_evidence_before_ai_assertions"
            ],
            output_schema={
                "type": "object",
                "required": ["hard_gates_passed", "weighted_score", "report"],
                "properties": {
                    "hard_gates_passed": {"type": "boolean"},
                    "weighted_score": {"type": "number"},
                    "breakdown": {"type": "object"},
                    "report": {"type": "string"}
                }
            },
            verification_requirements=[
                "hard_gates_passed == True",
                "weighted_score >= 80.0",
                "manifest SHA-256 match"
            ],
            evidence_sources=["Master Directive Section 13 & 14"]
        ))

# Auto-initialize
MentalModelRegistry.initialize_defaults()
