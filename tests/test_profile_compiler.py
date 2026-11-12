"""Compiled profiles extend the existing DesignProfile without inventing values; backward compatibility."""
import json
import os
import tempfile
import unittest

from desk.domain_intelligence import get_library
from desk.domain_intelligence.classifier import classify
from desk.domain_intelligence.profile_compiler import compile_profile, build_design_profile
from desk.profile import DesignProfile


class CompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()

    def test_compiled_profile_is_a_design_profile_and_round_trips(self):
        cls = classify({"text": "12 V to 3.3 V buck converter 3 A", "voltage_rails": {"VIN": 12.0, "3V3": 3.3}, "current_limits_A": {"VIN": 1.0, "3V3": 3.0},
                        "output_current_a": 3.0, "inductor_isat_a": 4.5, "ic_vin_min": 4.5, "ic_vin_max": 36.0}, self.lib)
        cp = compile_profile(cls, project_id="P_BUCK", lib=self.lib)
        self.assertEqual(cp.primary_archetype, "buck_converter")
        self.assertEqual(cp.status, "READY", cp.blocking_issues)
        prof = DesignProfile.from_dict(cp.design_profile)
        self.assertEqual(prof.voltage_rails["VIN"], 12.0)
        self.assertEqual(prof.current_limits_A["3V3"], 3.0)
        self.assertEqual(prof.domain_profile["primary_archetype"], "buck_converter")
        self.assertIn("ELEC-WIDTH-001", prof.domain_profile["enforced_rule_ids"])
        self.assertEqual(prof.unknown_current_policy, "fail")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "design_profile.json")
            prof.save(p)
            again = DesignProfile.load(p)
            self.assertEqual(again.domain_profile["rule_ids"], prof.domain_profile["rule_ids"])

    def test_never_invents_voltages_or_currents(self):
        cls = classify("24 V motor controller with BLDC motor 10 A peak", self.lib)
        cp = compile_profile(cls, project_id="P", lib=self.lib)
        prof = DesignProfile.from_dict(cp.design_profile)
        self.assertEqual(prof.voltage_rails, {})
        self.assertEqual(prof.current_limits_A, {})

    def test_blocking_rule_failure_blocks(self):
        cls = classify("24 V motor controller with BLDC motor, ESP32 and CAN", self.lib)   # no peak current declared
        cp = compile_profile(cls, project_id="P", lib=self.lib)
        self.assertEqual(cp.status, "BLOCKED")
        self.assertTrue(any(b.startswith("MOTOR-PEAK-140") for b in cp.blocking_issues))

    def test_mains_without_declared_rails_is_blocked(self):
        cls = classify({"text": "230 V AC mains input protection with fuse and MOV", "nets": ["MAINS_L", "MAINS_N", "VBULK"]}, self.lib)
        cp = compile_profile(cls, project_id="P", lib=self.lib, nets=["MAINS_L", "MAINS_N", "VBULK"])
        self.assertEqual(cp.status, "BLOCKED")
        self.assertTrue(any("MAINS_L" in b or "ELEC-UNKNOWN-002" in b for b in cp.blocking_issues), cp.blocking_issues)

    def test_conformal_coating_sets_b4(self):
        cls = classify("48 V DC-DC buck converter 5 A with conformal coating", self.lib)
        prof = build_design_profile("P", cls, cls.features)
        self.assertEqual(prof.clearance_condition, "B4")

    def test_four_layers_for_rf_and_two_otherwise(self):
        rf = classify("LoRa 868 MHz sensor node", self.lib)
        self.assertEqual(build_design_profile("P", rf, rf.features).layer_count, 4)
        pw = classify("12 V to 5 V buck converter 2 A", self.lib)
        self.assertEqual(build_design_profile("P", pw, pw.features).layer_count, 2)

    def test_base_profile_is_extended_not_replaced(self):
        base = DesignProfile(project_id="BASE", voltage_rails={"VIN": 24.0}, current_limits_A={"VIN": 3.0}, layer_count=4)
        cls = classify("24 V buck converter 3 A", self.lib)
        cp = compile_profile(cls, project_id="BASE", lib=self.lib, base_profile=base)
        prof = DesignProfile.from_dict(cp.design_profile)
        self.assertEqual(prof.layer_count, 4)
        self.assertEqual(prof.voltage_rails, {"VIN": 24.0})
        self.assertEqual(prof.domain_profile["primary_archetype"], "buck_converter")

    def test_backward_compatibility_with_profiles_without_domain_profile(self):
        old = {"project_id": "OLD", "voltage_rails": {"3V3": 3.3}, "current_limits_A": {"3V3": 0.5}}
        prof = DesignProfile.from_dict(old)
        self.assertEqual(prof.domain_profile, {})
        self.assertIn("domain_profile", prof.to_dict())

    def test_unsupported_rules_are_listed_not_hidden(self):
        cls = classify("precision 24-bit ADC front end with thermal management for 70 C ambient", self.lib)
        cp = compile_profile(cls, project_id="P", lib=self.lib)
        self.assertTrue(set(cp.unsupported_rule_ids) & {"THERM-TJ-050", "ELEC-RATING-007"})
        for e in cp.evaluations:
            if e.rule_id in cp.unsupported_rule_ids:
                self.assertIn(e.outcome, ("ADVISORY", "NOT_EVALUATED", "UNSUPPORTED"))


if __name__ == "__main__":
    unittest.main()
