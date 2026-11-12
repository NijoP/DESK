"""M3: declarative applicability, deterministic evaluators, fail-closed behaviour, unsupported handling."""
import unittest

from desk.domain_intelligence import get_library
from desk.domain_intelligence.models import Rule
from desk.domain_intelligence.rule_engine import evaluate_condition, applies, in_scope, EvalContext, evaluate_rule, evaluate_rules, EVALUATORS
from desk.profile import DesignProfile


def _rule(method, params=None, applicability=None, severity="BLOCKING", mode="ENFORCED"):
    return Rule.from_dict({"rule_id": "T-1", "name": "t", "domain": "core", "category": "electrical", "scope": {"archetypes": ["*"], "overlays": [], "component_families": []},
                           "severity": severity, "applicability": applicability or {}, "required_inputs": [], "evaluation_method": method, "parameters": params or {},
                           "source_references": [], "verification_method": "", "status": "OFFLINE_TESTED", "enforcement": {"subsystem": "quality.gate", "mode": mode}})


class ConditionTests(unittest.TestCase):
    def test_operators(self):
        f = {"v": 24, "p": ["can", "usb"], "m": True, "e": "outdoor"}
        self.assertTrue(evaluate_condition({"field": "v", "op": ">=", "value": 24}, f))
        self.assertFalse(evaluate_condition({"field": "v", "op": "<", "value": 24}, f))
        self.assertTrue(evaluate_condition({"field": "v", "op": "between", "value": [18, 36]}, f))
        self.assertTrue(evaluate_condition({"field": "p", "op": "intersects", "value": ["usb"]}, f))
        self.assertTrue(evaluate_condition({"field": "e", "op": "in", "value": ["outdoor", "marine"]}, f))
        self.assertTrue(evaluate_condition({"field": "m", "op": "==", "value": True}, f))
        self.assertTrue(evaluate_condition({"field": "x", "op": "exists", "value": False}, f))
        self.assertFalse(evaluate_condition({"field": "x", "op": ">", "value": 1}, f))
        self.assertFalse(evaluate_condition({"field": "e", "op": ">", "value": 1}, f))  # type error -> False, never raises

    def test_all_any_and_empty(self):
        f = {"v": 100, "mains": True}
        self.assertTrue(applies({}, f))
        self.assertTrue(applies({"all": [{"field": "v", "op": ">", "value": 50}], "any": [{"field": "mains", "op": "==", "value": True}, {"field": "iso", "op": "exists", "value": True}]}, f))
        self.assertFalse(applies({"all": [{"field": "v", "op": ">", "value": 500}]}, f))

    def test_scope_reasons(self):
        r = get_library().rule("PLACE-ANT-014")
        self.assertEqual(in_scope(r, ["buck_converter"], ["rf_communication"], []), "overlay:rf_communication")
        self.assertIsNone(in_scope(r, ["buck_converter"], [], []))
        self.assertEqual(in_scope(get_library().rule("ELEC-WIDTH-001"), [], [], []), "global")


class EvaluatorTests(unittest.TestCase):
    def test_unknown_evaluator_is_unsupported_not_pass(self):
        e = evaluate_rule(_rule("desk.nope"), EvalContext())
        self.assertEqual(e.outcome, "UNSUPPORTED")

    def test_applicability_gate(self):
        e = evaluate_rule(_rule("desk.rules.field_present", {"fields": ["x"]}, {"all": [{"field": "mains", "op": "==", "value": True}]}), EvalContext(features={}))
        self.assertEqual(e.outcome, "NOT_EVALUATED")

    def test_harmonic_check(self):
        r = _rule("desk.rules.harmonic_check", {"max_harmonic": 50})
        self.assertEqual(evaluate_rule(r, EvalContext(features={"switching_frequency_hz": 2.0e6, "rf_frequency_hz": 868e6})).outcome, "PASS")
        bad = evaluate_rule(r, EvalContext(features={"switching_frequency_hz": 1.0e6, "rf_frequency_hz": 10e6}))
        self.assertEqual(bad.outcome, "FAIL")
        self.assertEqual(bad.details["harmonic"], 10)

    def test_rail_headroom(self):
        r = _rule("desk.rules.rail_headroom", {"min_headroom_pct": 20, "tx_peak_a_default": 0.5})
        self.assertEqual(evaluate_rule(r, EvalContext(features={"regulator_rating_a": 0.8})).outcome, "PASS")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"regulator_rating_a": 0.5})).outcome, "FAIL")
        self.assertEqual(evaluate_rule(r, EvalContext(features={})).outcome, "NOT_EVALUATED")

    def test_band_plan(self):
        r = get_library().rule("LORA-BAND-110")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"rf_region": "EU868", "rf_frequency_hz": 868e6})).outcome, "PASS")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"rf_region": "US915", "rf_frequency_hz": 868e6})).outcome, "FAIL")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"rf_region": "XX", "rf_frequency_hz": 868e6})).outcome, "FAIL")

    def test_inductor_margin_buck_and_boost(self):
        r = get_library().rule("DCDC-ISAT-120")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"output_current_a": 3.0, "inductor_isat_a": 4.5})).outcome, "PASS")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"output_current_a": 3.0, "inductor_isat_a": 3.0})).outcome, "FAIL")
        boost = evaluate_rule(r, EvalContext(features={"output_current_a": 1.0, "inductor_isat_a": 6.0, "converter": ["boost"], "input_voltage_v": 3.7, "output_voltage_v": 12.0}))
        self.assertEqual(boost.outcome, "PASS")
        self.assertGreater(boost.details["required_isat_a"], 4.5)   # input current (not output) sizes a boost inductor
        self.assertEqual(evaluate_rule(r, EvalContext(features={"output_current_a": 1.0, "inductor_isat_a": 4.0, "converter": ["boost"], "input_voltage_v": 3.7, "output_voltage_v": 12.0})).outcome, "FAIL")

    def test_charge_voltage_fails_closed(self):
        r = get_library().rule("BAT-CHEM-130")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"cells": 1})).outcome, "FAIL")
        ok = evaluate_rule(r, EvalContext(features={"cells": 4, "chemistry": "lifepo4"}))
        self.assertEqual(ok.outcome, "PASS")
        self.assertAlmostEqual(ok.details["charge_voltage_v"], 14.6, places=2)
        self.assertEqual(evaluate_rule(r, EvalContext(features={"cells": 1, "chemistry": "li_ion", "charge_voltage_v": 4.35})).outcome, "FAIL")
        self.assertEqual(evaluate_rule(r, EvalContext(features={"cells": 1, "chemistry": "unobtainium"})).outcome, "FAIL")

    def test_family_present_and_peak_margin_and_usbc(self):
        lib = get_library()
        self.assertEqual(evaluate_rule(lib.rule("BAT-PROT-131"), EvalContext(families_present={"li_ion_charger"})).outcome, "FAIL")
        self.assertEqual(evaluate_rule(lib.rule("BAT-PROT-131"), EvalContext(families_present={"battery_protection_ic"})).outcome, "PASS")
        self.assertEqual(evaluate_rule(lib.rule("MOTOR-PEAK-140"), EvalContext(features={})).outcome, "FAIL")
        self.assertEqual(evaluate_rule(lib.rule("MOTOR-PEAK-140"), EvalContext(features={"peak_current_a": 10, "fet_id_rating_a": 20})).outcome, "PASS")
        self.assertEqual(evaluate_rule(lib.rule("MOTOR-PEAK-140"), EvalContext(features={"peak_current_a": 10, "fet_id_rating_a": 12})).outcome, "FAIL")
        cc = lib.rule("USBC-CC-150")
        self.assertEqual(evaluate_rule(cc, EvalContext(features={"usb_role": "sink", "cc_resistors": {"CC1": 5100, "CC2": 5100, "type": "pulldown"}})).outcome, "PASS")
        self.assertEqual(evaluate_rule(cc, EvalContext(features={"usb_role": "sink", "cc_resistors": {"CC1": 5100, "type": "pulldown"}})).outcome, "FAIL")
        self.assertEqual(evaluate_rule(cc, EvalContext(features={})).outcome, "NOT_EVALUATED")

    def test_profile_backed_rules(self):
        lib = get_library()
        p = DesignProfile(project_id="T", voltage_rails={"VIN": 24.0, "3V3": 3.3}, current_limits_A={"VIN": 2.0, "3V3": 1.0})
        ctx = EvalContext(features={}, profile=p, nets=["VIN", "3V3", "SIG"])
        self.assertEqual(evaluate_rule(lib.rule("ELEC-WIDTH-001"), ctx).outcome, "PASS")
        self.assertEqual(evaluate_rule(lib.rule("ELEC-UNKNOWN-002"), ctx).outcome, "PASS")
        self.assertEqual(evaluate_rule(lib.rule("ELEC-CLEAR-003"), ctx).outcome, "PASS")
        bad = DesignProfile(project_id="T", voltage_rails={"3V3": 3.3}, current_limits_A={})
        e = evaluate_rule(lib.rule("ELEC-UNKNOWN-002"), EvalContext(profile=bad, nets=["VBUS", "MAINS_L"]))
        self.assertEqual(e.outcome, "FAIL")
        self.assertIn("MAINS_L", e.message)
        self.assertEqual(evaluate_rule(lib.rule("ELEC-WIDTH-001"), EvalContext()).outcome, "NOT_EVALUATED")

    def test_creepage_doubles_for_reinforced(self):
        r = get_library().rule("ELEC-CREEP-004")
        basic = evaluate_rule(r, EvalContext(features={"isolation": True, "working_voltage_v": 250.0, "isolation_voltage_v": 3000.0, "insulation_grade": "basic"}))
        reinf = evaluate_rule(r, EvalContext(features={"isolation": True, "working_voltage_v": 250.0, "isolation_voltage_v": 3000.0, "insulation_grade": "reinforced"}))
        self.assertEqual(evaluate_rule(r, EvalContext(features={"isolation": True, "isolation_voltage_v": 3000.0})).outcome, "NOT_EVALUATED")
        self.assertEqual(basic.outcome, "PASS")
        self.assertAlmostEqual(reinf.details["creepage_mm"], 2 * basic.details["creepage_mm"], places=3)
        self.assertFalse(basic.details["verified_against_standard"])

    def test_deferred_rules_are_not_claimed_enforced_offline(self):
        e = evaluate_rule(get_library().rule("PLACE-DECAP-010"), EvalContext())
        self.assertEqual(e.outcome, "DEFERRED")
        self.assertEqual(e.subsystem, "placement")

    def test_evaluation_order_is_deterministic(self):
        lib = get_library()
        rs = list(lib.rules().values())
        a = [e.rule_id for e in evaluate_rules(rs, EvalContext())]
        b = [e.rule_id for e in evaluate_rules(reversed(rs), EvalContext())]
        self.assertEqual(a, b)
        self.assertEqual(a, sorted(a))

    def test_every_library_evaluator_exists(self):
        for r in get_library().rules().values():
            self.assertIn(r.evaluation_method, EVALUATORS, r.rule_id)


if __name__ == "__main__":
    unittest.main()
