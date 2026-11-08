"""Mental-Model Policy Compiler for DESK.
Transforms high-level mental models and versioned Engineering Design Profiles
into compact, task-specific, token-budgeted policies for AI agents and deterministic engines.

Features:
- Task classification & context extraction
- Profile-driven constraint resolution (widths, clearances, keepouts, stackup)
- Output schema and verification checklist generation
- High-density prompt generation (< 400 tokens)
- Compiled-policy caching with fine-grained invalidation on profile changes.

Zero external dependencies.
"""
import os
import json
import hashlib
from typing import Dict, List, Optional, Any, Set
from desk.mental.models import MentalModel, CompiledPolicy
from desk.mental.registry import MentalModelRegistry
from desk.profile import DesignProfile

class PolicyCompiler:
    _cache: Dict[str, CompiledPolicy] = {}

    @classmethod
    def get_cache_key(cls, model_id: str, task_type: str, profile: DesignProfile, model_ver: str) -> str:
        return f"{model_id}:{task_type}:{profile.profile_hash}:{model_ver}"

    @classmethod
    def clear_cache(cls, domain: Optional[str] = None):
        if not domain:
            cls._cache.clear()
        else:
            cls._cache = {k: v for k, v in cls._cache.items() if not k.startswith(domain)}

    @classmethod
    def compile(cls, model_id: str, task_type: str, profile: DesignProfile,
                extra_context: Optional[Dict[str, Any]] = None) -> CompiledPolicy:
        """Compile a compact, task-specific policy."""
        model = MentalModelRegistry.get(model_id)
        if not model:
            raise ValueError(f"Unknown mental model: {model_id}. Available: {MentalModelRegistry.list_models()}")

        cache_key = cls.get_cache_key(model_id, task_type, profile, model.version)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        extra = extra_context or {}
        compact_rules: List[str] = []
        hard_constraints: Dict[str, Any] = dict(model.hard_constraints)
        checklist: List[str] = list(model.verification_requirements)
        output_schema: Dict[str, Any] = dict(model.output_schema)

        # ------------------------------------------------------------- M1_SCHEMATIC
        if model_id == "M1_SCHEMATIC":
            block_id = extra.get("block_id", "GENERAL")
            compact_rules.append(f"Design block {block_id} using 100-mil grid and UPPER-CASE title.")
            compact_rules.append("Every pin must be assigned to a net or explicit 'nc'.")
            compact_rules.append("Calculate every passive value from datasheet formula and record in qa[].")
            for rail, v in profile.voltage_rails.items():
                compact_rules.append(f"Rail {rail}: {v:.1f}V (Max current: {profile.get_current_for_net(rail):.2f}A)")
            if profile.critical_nets:
                compact_rules.append(f"Critical nets to preserve: {', '.join(profile.critical_nets)}")

        # ------------------------------------------------------------- M2_PLACEMENT
        elif model_id == "M2_PLACEMENT":
            W, H = profile.board_dimensions_mm
            compact_rules.append(f"Board envelope: {W:.1f} x {H:.1f} mm. Origin at (0,0).")
            compact_rules.append("Keep connectors flush to edge with mating corridor outward.")
            compact_rules.append("Protect screw-terminal screwdriver access cones (12mm) and wire entry.")
            compact_rules.append("Snap decoupling caps within 2.0mm of IC supply pins.")
            compact_rules.append("Maintain 7.0mm thermal isolation between heat sources and sensors.")
            hard_constraints["board_outline_mm"] = [W, H]
            hard_constraints["min_edge_clearance_pad_mm"] = 0.30
            hard_constraints["min_edge_clearance_body_mm"] = 0.00
            for ko in profile.keepouts:
                compact_rules.append(f"Enforce keepout: {ko.get('name', 'KEEPOUT')}")

        # ------------------------------------------------------------- M3_ROUTING
        elif model_id == "M3_ROUTING":
            layers = profile.get_stackup_layers()
            compact_rules.append(f"Actual Stackup: {', '.join(layers)} ({profile.layer_count} layers).")
            compact_rules.append("Route in strict 6 stages: GND -> Connectors -> Critical -> Control -> Power -> Remaining.")
            target_nets = extra.get("nets", [])
            for n in target_nets:
                w = profile.derive_trace_width_mil(n)
                compact_rules.append(f"Net {n}: min width {w:.1f} mil (current {profile.get_current_for_net(n):.2f}A)")
            for dp_name, dp in profile.diff_pairs.items():
                compact_rules.append(f"Diff Pair {dp_name} ({dp.pos_net}/{dp.neg_net}): {dp.target_impedance_ohms:.0f} ohm, width {dp.trace_width_mil:.1f} mil, space {dp.pair_spacing_mil:.1f} mil.")
            hard_constraints["stackup_layers"] = layers
            hard_constraints["min_signal_width_mil"] = profile.manufacturing.min_trace_width_mil
            hard_constraints["min_clearance_mil"] = profile.manufacturing.min_clearance_mil

        # ------------------------------------------------------------- M4_COPPER_GROUND
        elif model_id == "M4_COPPER_GROUND":
            layers = profile.get_stackup_layers()
            compact_rules.append(f"Ground reference layers based on stackup: {[l for l in layers if 'GND' in l or 'Bottom' in l]}")
            compact_rules.append("Solid connections on power/GND pads carry high current; use thermal relief only on hand-soldered passives.")
            compact_rules.append(f"Copper-to-edge minimum clearance: {profile.manufacturing.copper_to_edge_mil:.1f} mil.")
            compact_rules.append("Stitch ground reference planes across layer boundaries with 100-mil via grid.")
            hard_constraints["copper_to_edge_mil"] = profile.manufacturing.copper_to_edge_mil

        # ------------------------------------------------------------- M5_ELECTRICAL_MFG
        elif model_id == "M5_ELECTRICAL_MFG":
            mfg = profile.manufacturing
            compact_rules.append(f"Manufacturer capability baseline: {mfg.name}")
            compact_rules.append(f"Min trace width: {mfg.min_trace_width_mil:.1f} mil, min clearance: {mfg.min_clearance_mil:.1f} mil.")
            compact_rules.append(f"Min drill: {mfg.min_drill_mil:.1f} mil, min annular ring: {mfg.min_via_annular_ring_mil:.1f} mil.")
            compact_rules.append(f"Max thermal rise: {profile.thermal.max_temperature_rise_c:.1f}°C at {profile.thermal.max_ambient_temp_c:.1f}°C ambient.")
            hard_constraints["min_drill_mil"] = mfg.min_drill_mil
            hard_constraints["min_annular_ring_mil"] = mfg.min_via_annular_ring_mil

        # ------------------------------------------------------------- M6_VERIFICATION_REVIEW
        elif model_id == "M6_VERIFICATION_REVIEW":
            compact_rules.append("Hard gates are non-negotiable: 0 shorts, 0 opens, 0 clearance errors, all critical nets routed.")
            compact_rules.append("Weighted score weights: Electrical 25%, Routing 20%, Placement 15%, RF/Power 20%, Manufacturability 10%, Geometry 10%.")
            compact_rules.append("Deterministic tools (DRC, netlist check, manifest verification) take strict precedence over AI review.")

        policy_id = f"{model_id}_{task_type}_{profile.profile_hash[:8]}"
        raw_text = "\n".join(compact_rules)
        token_est = (len(raw_text) + 3) // 4

        compiled = CompiledPolicy(
            policy_id=policy_id,
            model_id=model_id,
            task_type=task_type,
            version=model.version,
            profile_hash=profile.profile_hash,
            compact_rules=compact_rules,
            hard_constraints=hard_constraints,
            output_schema=output_schema,
            verification_checklist=checklist,
            token_estimate=token_est
        )

        cls._cache[cache_key] = compiled
        return compiled

    @classmethod
    def invalidate_on_profile_change(cls, profile: DesignProfile, changed_keys: Set[str]):
        """Selectively invalidate cached policies affected by changed profile parameters."""
        affected = profile.affected_domains(changed_keys)
        cls._cache = {k: v for k, v in cls._cache.items() if not any(k.startswith(dom) for dom in affected)}
