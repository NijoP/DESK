"""Cross-domain composition: de-duplication, precedence, conflicts, stricter-wins, safety never discarded."""
import unittest

from desk.domain_intelligence import get_library
from desk.domain_intelligence.models import Rule
from desk.domain_intelligence.rule_composer import compose


def _r(rid, cat, params, severity="WARNING", overlays=(), arch=("*",)):
    return Rule.from_dict({"rule_id": rid, "name": rid, "domain": "test", "category": cat, "scope": {"archetypes": list(arch), "overlays": list(overlays), "component_families": []},
                           "severity": severity, "applicability": {}, "required_inputs": [], "evaluation_method": "advisory", "parameters": params,
                           "source_references": [], "verification_method": "", "status": "ADVISORY", "enforcement": {"subsystem": "none", "mode": "ADVISORY"}})


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()

    def test_scope_resolution_and_dedupe(self):
        c = compose(self.lib, ["three_phase_bldc_controller"], ["motor_drive", "high_current", "can_interface"], ["current_sense_resistor"])
        ids = [r.rule_id for r in c.rules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("ELEC-WIDTH-001", ids)       # global
        self.assertIn("MOTOR-PEAK-140", ids)       # overlay motor_drive
        self.assertIn("PLACE-SENSE-018", ids)      # family
        self.assertNotIn("LORA-BAND-110", ids)     # other archetype
        self.assertEqual(c.sources["ELEC-WIDTH-001"], ["global"])

    def test_precedence_blocking_first_then_overlay_precedence(self):
        c = compose(self.lib, ["isolated_ac_dc"], ["mains_safety_isolation", "switching_power", "low_power"], [])
        sev = [r.severity for r in c.rules]
        first_non_blocking = next(i for i, s in enumerate(sev) if s != "BLOCKING")
        self.assertTrue(all(s == "BLOCKING" for s in sev[:first_non_blocking]))

    def test_conflicting_numeric_parameters_keep_the_stricter(self):
        a = _r("A", "placement", {"max_distance_mm": 5.0})
        b = _r("B", "placement", {"max_distance_mm": 2.0})
        c = compose(self.lib, [], [], [], extra_rules=[a, b])
        conf = [x for x in c.conflicts if x.parameter == "placement.max_distance_mm"]
        self.assertTrue(conf)
        self.assertEqual(conf[0].resolution, "stricter_kept:B")
        ids = [r.rule_id for r in c.rules]
        self.assertIn("B", ids)
        self.assertNotIn("A", ids)

    def test_more_severe_rule_is_never_dropped_even_if_looser(self):
        a = _r("A", "routing", {"min_width_mil": 10.0}, severity="BLOCKING")
        b = _r("B", "routing", {"min_width_mil": 20.0}, severity="WARNING")
        c = compose(self.lib, [], [], [], extra_rules=[a, b])
        ids = [r.rule_id for r in c.rules]
        self.assertIn("A", ids)
        self.assertIn("B", ids)
        self.assertEqual([x.resolution for x in c.conflicts if x.parameter == "routing.min_width_mil"], ["stricter_kept:B"])

    def test_unknown_strictness_requires_review_and_keeps_both(self):
        a = _r("A", "thermal", {"spoke_count": 4})
        b = _r("B", "thermal", {"spoke_count": 2})
        c = compose(self.lib, [], [], [], extra_rules=[a, b])
        conf = [x for x in c.conflicts if x.parameter == "thermal.spoke_count"]
        self.assertEqual(conf[0].resolution, "review_required")
        self.assertEqual(sorted(r.rule_id for r in c.rules if r.rule_id in ("A", "B")), ["A", "B"])

    def test_library_rules_have_no_review_conflicts_for_any_archetype(self):
        for a in self.lib.archetypes():
            c = compose(self.lib, [a.archetype_id], a.overlays, a.families)
            self.assertEqual([x for x in c.conflicts if x.resolution == "review_required"], [], a.archetype_id)
            self.assertEqual(c.dropped, [], a.archetype_id)

    def test_composition_latency(self):
        import time
        t0 = time.perf_counter()
        for _ in range(20):
            compose(self.lib, ["battery_iot_node"], ["rf_communication", "battery_management", "low_power", "harsh_environment"], ["mcu", "rf_transceiver"])
        self.assertLess((time.perf_counter() - t0) / 20, 0.05)


if __name__ == "__main__":
    unittest.main()
