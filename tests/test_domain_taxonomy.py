"""M1: the 100-archetype taxonomy is complete, unique, schema-valid and allocated per the directive."""
import unittest
from collections import Counter

from desk.domain_intelligence import get_library
from desk.domain_intelligence.models import EVIDENCE_STATES
from desk.domain_intelligence.rule_engine import EVALUATORS
from desk.domain_intelligence.validation import validate_library, ALLOCATION

REQUIRED_FIELDS = ["archetype_id", "name", "domain", "description", "intended_applications", "typical_input_requirements", "electrical_characteristics",
                   "operating_voltage_ranges", "current_power_characteristics", "typical_component_families", "required_component_roles", "optional_component_roles",
                   "critical_electrical_constraints", "stackup_recommendations", "placement_rules", "routing_rules", "copper_ground_requirements", "thermal_considerations",
                   "emi_emc_considerations", "protection_requirements", "verification_requirements", "manufacturing_constraints", "applicable_standards",
                   "unsupported_conditions", "maturity"]


class TaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()

    def test_exactly_100_unique_archetypes(self):
        ids = self.lib.archetype_ids()
        self.assertEqual(len(ids), 100)
        self.assertEqual(len(set(ids)), 100)

    def test_domain_allocation_matches_directive(self):
        counts = Counter(m["domain"] for m in self.lib.archetype_index().values())
        self.assertEqual(dict(counts), ALLOCATION)
        self.assertEqual(sum(ALLOCATION.values()), 100)

    def test_every_archetype_has_the_25_fields_and_distinct_content(self):
        descs = set()
        for a in self.lib.archetypes():
            for f in REQUIRED_FIELDS:
                self.assertIn(f, a.data, f"{a.archetype_id} missing {f}")
            self.assertTrue(a.data["critical_electrical_constraints"], a.archetype_id)
            self.assertTrue(a.data["unsupported_conditions"], a.archetype_id)
            self.assertTrue(a.data["required_component_roles"], a.archetype_id)
            self.assertNotIn(a.data["description"], descs, f"duplicate description for {a.archetype_id}")
            descs.add(a.data["description"])
            self.assertIn(a.maturity, EVIDENCE_STATES)

    def test_library_validates_with_known_evaluators(self):
        problems = validate_library(self.lib, known_evaluators=set(EVALUATORS))
        self.assertEqual(problems, [], "\n".join(problems[:30]))

    def test_first_ten_priority_archetypes_are_offline_tested(self):
        for aid in ["esp32_dev_board", "stm32_controller", "lora_transceiver", "buck_converter", "boost_converter", "single_cell_liion_charger",
                    "battery_management_system", "three_phase_bldc_controller", "usb_c_interface", "ac_mains_input_protection"]:
            a = self.lib.archetype(aid)
            self.assertEqual(a.maturity, "OFFLINE_TESTED", aid)
            self.assertGreaterEqual(len(a.rule_ids), 10, aid)

    def test_standards_are_references_not_text(self):
        for ref in self.lib.references().values():
            self.assertFalse(ref["copyrighted_text_stored"])
            self.assertLess(len(ref["clause_notes"]), 400)

    def test_search_is_deterministic(self):
        a = self.lib.search("wireless battery sensor")
        b = self.lib.search("wireless battery sensor")
        self.assertEqual(a, b)
        self.assertTrue(a)
        self.assertIn(a[0]["archetype_id"], {"low_power_sensor_node", "battery_iot_node", "wifi_ble_module_board", "wearable_electronics"})


if __name__ == "__main__":
    unittest.main()
