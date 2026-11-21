"""Insulation coordination engine (desk/insulation): clearance and creepage kept apart, statuses, provenance, sign-off.

The FIXTURE dataset below is SYNTHETIC: its numbers are invented round values that exercise the engine's mechanics
(lookup, reinforced rules, altitude correction, status). They are NOT IEC 60664-1 values and must never be copied into
a dataset. Software-tested with fixtures; not validated on a live design.
"""
import copy
import json
import os
import tempfile
import unittest

from desk import insulation as INS
from desk import ipc
from desk import spacing as SP
from desk.errors import InsulationDataInvalid
from desk.insulation import tables as T
from desk.profile import DesignProfile
from desk.router import RoutingPlanGenerator
from desk.models import NetConnectivityGraph, NetEndpoint

SYN = {"status": "VERIFIED", "source": "SYNTHETIC TEST FIXTURE (not IEC values)", "verified_by": "unit-test"}
FIXTURE = {
    "schema": "desk.insulation.dataset/1",
    "dataset_id": "SYNTHETIC-FIXTURE-1",
    "standard": {"id": "IEC 60664-1", "edition": "Edition 3.0 (2020)", "amendments": ["Amendment 1 (2025)"],
                 "label": "IEC 60664-1:2020+A1:2025"},
    "tables": {
        "creepage": {
            "reference": "synthetic creepage table", "default_provenance": SYN,
            "columns": {
                "PD1": {"pollution_degree": 1, "material_groups": ["I", "II", "IIIa", "IIIb"],
                        "rows_v": [50, 100, 250], "values_mm": [0.1, 0.2, 0.5]},
                "PD2-I": {"pollution_degree": 2, "material_groups": ["I"], "rows_v": [50, 100, 250],
                          "values_mm": [0.5, 0.7, 1.2]},
                "PD2-II": {"pollution_degree": 2, "material_groups": ["II"], "rows_v": [50, 100, 250],
                           "values_mm": [0.7, 1.0, 1.8]},
                "PD2-III": {"pollution_degree": 2, "material_groups": ["IIIa", "IIIb"], "rows_v": [50, 100, 250],
                            "values_mm": [1.0, 1.4, 2.5]},
            }},
        "clearance": {
            "reference": "synthetic clearance table", "default_provenance": SYN,
            "altitude_basis_m": 2000,
            "columns": {
                "PD1": {"pollution_degree": 1, "rows_v": [500, 1000, 2000, 4000], "values_mm": [0.05, 0.1, 0.5, 2.0]},
                "PD2": {"pollution_degree": 2, "rows_v": [500, 1000, 2000, 4000], "values_mm": [0.2, 0.2, 0.5, 2.0]},
            }},
        "rated_impulse_voltage": {
            "reference": "synthetic rated impulse table", "default_provenance": SYN,
            "rows_v": [100, 300],
            "columns": {"I": {"values_v": [500, 1000]}, "II": {"values_v": [1000, 2000]},
                        "III": {"values_v": [2000, 4000]}}},
        "altitude_correction": {"reference": "synthetic altitude table", "default_provenance": SYN,
                                "rows_m": [2000, 3000, 5000], "factors": [1.0, 1.5, 2.0]},
        "material_group_by_cti": {"reference": "synthetic CTI table", "default_provenance": SYN,
                                  "bands": [{"group": "I", "cti_min": 600, "cti_max": None},
                                            {"group": "II", "cti_min": 400, "cti_max": 600},
                                            {"group": "IIIa", "cti_min": 175, "cti_max": 400},
                                            {"group": "IIIb", "cti_min": 0, "cti_max": 175}]},
    },
    "rules": {
        "creepage_reinforced_factor": {"value": 2.0, "reference": "synthetic rule", "provenance": SYN},
        "clearance_reinforced": {"method": "impulse_step", "reference": "synthetic rule", "provenance": SYN},
    },
}


def fixture(mutate=None):
    d = copy.deepcopy(FIXTURE)
    if mutate:
        mutate(d)
    return T.parse_dataset(d, "<fixture>")


FULL = dict(insulation_type="basic", working_voltage_v=100, rated_impulse_voltage_v=1000, pollution_degree=2,
            material_group="IIIb", altitude_m=1000, coating="none")


def inputs(**kw):
    d = dict(FULL)
    d.update(kw)
    return INS.InsulationInputs(**{k: v for k, v in d.items() if v is not None})


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v)


class TestSeparation(unittest.TestCase):
    def test_types_and_code_paths_are_separate(self):
        ds = fixture()
        c, k = INS.evaluate_clearance(inputs(), ds), INS.evaluate_creepage(inputs(), ds)
        self.assertIsInstance(c, INS.ClearanceResult)
        self.assertIsInstance(k, INS.CreepageResult)
        self.assertFalse(isinstance(c, INS.CreepageResult) or isinstance(k, INS.ClearanceResult))
        self.assertEqual((c.to_dict()["quantity"], k.to_dict()["quantity"]), ("clearance", "creepage"))
        with self.assertRaises(TypeError):
            INS.InsulationAssessment(inputs=inputs(), clearance=k, creepage=c, standard="x", dataset_id="y")

    def test_clearance_never_reads_creepage_data_and_vice_versa(self):
        full = fixture()
        no_creep = fixture(lambda d: d["tables"].pop("creepage"))
        no_clear = fixture(lambda d: d["tables"].pop("clearance"))
        self.assertEqual(INS.evaluate_clearance(inputs(), full).value_mm,
                         INS.evaluate_clearance(inputs(), no_creep).value_mm)
        self.assertEqual(INS.evaluate_creepage(inputs(), full).value_mm,
                         INS.evaluate_creepage(inputs(), no_clear).value_mm)
        # creepage-only inputs do not move clearance; clearance-only inputs do not move creepage
        base_c = INS.evaluate_clearance(inputs(), full)
        for kw in ({"working_voltage_v": 250}, {"material_group": "I"}, {"cti": 700, "material_group": None}):
            self.assertEqual(INS.evaluate_clearance(inputs(**kw), full).value_mm, base_c.value_mm, kw)
        base_k = INS.evaluate_creepage(inputs(), full)
        for kw in ({"rated_impulse_voltage_v": 4000}, {"altitude_m": 4000}):
            self.assertEqual(INS.evaluate_creepage(inputs(**kw), full).value_mm, base_k.value_mm, kw)


class TestMonotonicity(unittest.TestCase):
    def test_creepage_never_decreases_with_voltage(self):
        for ds in (fixture(), T.default_dataset()):
            for pd, mg in ((1, "I"), (2, "I"), (2, "II"), (2, "IIIb")):
                last = 0.0
                for v in range(0, 1001, 5):
                    r = INS.evaluate_creepage(inputs(working_voltage_v=v, pollution_degree=pd, material_group=mg), ds)
                    if r.value_mm is None:
                        break
                    self.assertGreaterEqual(r.value_mm, last, (ds.dataset_id, pd, mg, v))
                    last = r.value_mm

    def test_clearance_never_decreases_with_impulse_or_altitude(self):
        ds = fixture()
        last = 0.0
        for u in range(0, 4001, 50):
            v = INS.evaluate_clearance(inputs(rated_impulse_voltage_v=u), ds).value_mm
            self.assertGreaterEqual(v, last)
            last = v
        last = 0.0
        for alt in range(0, 5001, 250):
            v = INS.evaluate_clearance(inputs(altitude_m=alt), ds).value_mm
            self.assertGreaterEqual(v, last)
            last = v

    def test_loader_rejects_a_decreasing_table(self):
        with self.assertRaises(InsulationDataInvalid):
            fixture(lambda d: d["tables"]["creepage"]["columns"]["PD1"].update(values_mm=[0.5, 0.2, 0.6]))


class TestAltitude(unittest.TestCase):
    def test_altitude_correction_applies_to_clearance_only(self):
        ds = fixture()
        low, high = INS.evaluate_clearance(inputs(altitude_m=1000), ds), INS.evaluate_clearance(inputs(altitude_m=3000), ds)
        self.assertEqual(low.altitude_factor, 1.0)
        self.assertEqual(high.altitude_factor, 1.5)
        self.assertAlmostEqual(high.value_mm, low.value_mm * 1.5)
        self.assertEqual(INS.evaluate_creepage(inputs(altitude_m=1000), ds).value_mm,
                         INS.evaluate_creepage(inputs(altitude_m=5000), ds).value_mm)
        self.assertNotIn("altitude_factor", INS.evaluate_creepage(inputs(), ds).to_dict())
        self.assertIn("altitude_m", INS.evaluate_clearance(inputs(altitude_m=None), ds).missing_inputs)
        self.assertNotIn("altitude_m", INS.evaluate_creepage(inputs(altitude_m=None), ds).missing_inputs)

    def test_altitude_above_basis_without_correction_table_is_unverified(self):
        ds = fixture(lambda d: d["tables"].pop("altitude_correction"))
        self.assertEqual(INS.evaluate_clearance(inputs(altitude_m=1500), ds).status, INS.Status.VERIFIED_AGAINST_TABLE)
        r = INS.evaluate_clearance(inputs(altitude_m=3000), ds)
        self.assertEqual(r.status, INS.Status.UNVERIFIED)
        self.assertIsNone(r.value_mm)
        self.assertIsNone(r.guidance_mm)


class TestInsulationTypeOrdering(unittest.TestCase):
    def test_reinforced_ge_basic_ge_functional(self):
        for ds in (fixture(), fixture(lambda d: d["rules"].update(clearance_reinforced={
                "method": "factor", "value": 1.6, "reference": "synthetic", "provenance": SYN}))):
            for u in (400, 1000, 2000):
                c = [INS.evaluate_clearance(inputs(insulation_type=t, rated_impulse_voltage_v=u), ds).value_mm
                     for t in ("functional", "basic", "reinforced")]
                self.assertLessEqual(c[0], c[1])
                self.assertLessEqual(c[1], c[2])
        for ds in (fixture(), T.default_dataset()):
            for v in (50, 100, 250):
                k = [INS.evaluate_creepage(inputs(insulation_type=t, working_voltage_v=v), ds).value_mm
                     for t in ("functional", "basic", "reinforced")]
                self.assertLessEqual(k[0], k[1])
                self.assertLessEqual(k[1], k[2])

    def test_reinforced_impulse_step_uses_next_row(self):
        r = INS.evaluate_clearance(inputs(insulation_type="reinforced", rated_impulse_voltage_v=2000), fixture())
        self.assertEqual(r.value_mm, 2.0)                           # next synthetic row (4000 V)
        self.assertEqual(r.status, INS.Status.VERIFIED_AGAINST_TABLE)

    def test_functional_clearance_is_capped_provisional(self):
        r = INS.evaluate_clearance(inputs(insulation_type="functional"), fixture())
        self.assertEqual(r.status, INS.Status.PROVISIONAL)


class TestMissingInputs(unittest.TestCase):
    def test_each_missing_input_gives_unverified_and_is_named(self):
        ds = fixture()
        for key, quantity in (("insulation_type", "both"), ("pollution_degree", "both"), ("altitude_m", "clearance"),
                              ("rated_impulse_voltage_v", "clearance"), ("working_voltage_v", "creepage"),
                              ("material_group", "creepage"), ("coating", "creepage")):
            a = INS.assess(inputs(**{key: None}), ds)
            for r in ((a.clearance, a.creepage) if quantity == "both" else
                      ((a.clearance,) if quantity == "clearance" else (a.creepage,))):
                self.assertEqual(r.status, INS.Status.UNVERIFIED, (key, r.QUANTITY))
                self.assertIsNone(r.value_mm, key)
                self.assertTrue(any(m.startswith(key) for m in r.missing_inputs), (key, r.missing_inputs))

    def test_no_silent_default(self):
        r = INS.evaluate_creepage(INS.InsulationInputs(working_voltage_v=230), fixture())
        self.assertEqual(r.status, INS.Status.UNVERIFIED)
        self.assertIsNone(r.pollution_degree)
        self.assertIsNone(r.material_group)
        self.assertIsNone(r.insulation_type)

    def test_conservative_guidance_over_undeclared_inputs(self):
        ds = fixture()
        r = INS.evaluate_creepage(inputs(material_group=None, insulation_type=None), ds)
        self.assertEqual(r.status, INS.Status.UNVERIFIED)
        worst = INS.evaluate_creepage(inputs(material_group="IIIb", insulation_type="reinforced"), ds).value_mm
        self.assertEqual(r.guidance_mm, worst)
        self.assertIn("PROVISIONAL LAYOUT GUIDANCE", r.guidance_basis)
        # pollution degree undeclared: PD3/PD4 are not in the dataset, so no number can be shown conservative
        self.assertIsNone(INS.evaluate_creepage(inputs(pollution_degree=None), ds).guidance_mm)
        self.assertIsNone(INS.evaluate_creepage(inputs(working_voltage_v=None), ds).guidance_mm)

    def test_cti_needs_a_cti_table_and_conflicts_are_unverified(self):
        ds = fixture()
        self.assertEqual(INS.evaluate_creepage(inputs(material_group=None, cti=650), ds).material_group, "I")
        no_cti = fixture(lambda d: d["tables"].pop("material_group_by_cti"))
        self.assertEqual(INS.evaluate_creepage(inputs(material_group=None, cti=650), no_cti).status,
                         INS.Status.UNVERIFIED)
        self.assertEqual(INS.evaluate_creepage(inputs(material_group="IIIb", cti=650), ds).status,
                         INS.Status.UNVERIFIED)

    def test_ovc_and_mains_voltage_give_rated_impulse_through_the_table(self):
        ds = fixture()
        r = INS.evaluate_clearance(inputs(rated_impulse_voltage_v=None, overvoltage_category="II",
                                          mains_voltage_v=300), ds)
        self.assertEqual(r.rated_impulse_voltage_v, 2000)
        self.assertEqual(r.status, INS.Status.VERIFIED_AGAINST_TABLE)
        low = INS.evaluate_clearance(inputs(rated_impulse_voltage_v=500, overvoltage_category="II",
                                            mains_voltage_v=300), ds)
        self.assertEqual(low.status, INS.Status.UNVERIFIED)        # declared below the table: review, never accept

    def test_bad_inputs_raise(self):
        for kw in ({"insulation_type": "double"}, {"pollution_degree": 5}, {"material_group": "IV"},
                   {"overvoltage_category": "V"}, {"working_voltage_v": "230"}):
            with self.assertRaises(ValueError, msg=kw):
                INS.InsulationInputs(**kw)
        with self.assertRaises(ValueError):
            INS.InsulationInputs.from_dict({"voltage": 230})


class TestShippedDataset(unittest.TestCase):
    def test_shipped_dataset_is_provisional_and_matches_ipc(self):
        ds = T.default_dataset()
        self.assertEqual(ds.standard_label, "IEC 60664-1:2020+A1:2025")
        self.assertEqual(set(ds.tables), {"creepage"})               # no clearance / impulse / altitude / CTI data
        for col in ds.table("creepage").columns.values():
            for cell in col.cells:
                self.assertEqual(cell.provenance.status, "PROVISIONAL")
                self.assertIn("desk/ipc.py", cell.provenance.source)
        for v in (10, 48, 50, 230, 250, 400, 1000):
            for pd, mg in ((1, "IIIb"), (2, "I"), (2, "II"), (2, "IIIa")):
                r = INS.evaluate_creepage(inputs(working_voltage_v=v, pollution_degree=pd, material_group=mg), ds)
                self.assertEqual(r.value_mm, ipc.creepage_mm(v, pd, mg))
                self.assertEqual(r.status, INS.Status.PROVISIONAL)

    def test_missing_tables_give_unverified(self):
        ds = T.default_dataset()
        c = INS.evaluate_clearance(inputs(), ds)
        self.assertEqual(c.status, INS.Status.UNVERIFIED)
        self.assertIsNone(c.value_mm)
        self.assertIsNone(c.guidance_mm)
        self.assertIn("table: clearance", c.missing_inputs)
        pd3 = INS.evaluate_creepage(inputs(pollution_degree=3), ds)
        self.assertEqual(pd3.status, INS.Status.UNVERIFIED)
        self.assertIsNone(pd3.guidance_mm)
        above = INS.evaluate_creepage(inputs(working_voltage_v=1200), ds)
        self.assertEqual(above.status, INS.Status.UNVERIFIED)
        no_rule = fixture(lambda d: d["rules"].pop("creepage_reinforced_factor"))
        self.assertEqual(INS.evaluate_creepage(inputs(insulation_type="reinforced"), no_rule).status,
                         INS.Status.UNVERIFIED)

    def test_every_result_carries_edition_references_and_assumptions(self):
        r = INS.evaluate_creepage(inputs(working_voltage_v=230, coating="acrylic", environment="indoor"),
                                  T.default_dataset())
        d = r.to_dict()
        self.assertEqual(d["standard"], "IEC 60664-1:2020+A1:2025")
        self.assertTrue(d["references"] and d["provenance"] and d["dataset_id"])
        self.assertTrue(any("rounded up" in a for a in d["assumptions"]))
        self.assertTrue(any("no coating credit" in a for a in d["assumptions"]))


class TestLoader(unittest.TestCase):
    def test_owner_dataset_through_config_without_code_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "owner.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(FIXTURE, f)
            old = os.environ.get(T.CONFIG_KEY)
            os.environ[T.CONFIG_KEY] = path
            try:
                self.assertEqual(T.load_dataset().dataset_id, "SYNTHETIC-FIXTURE-1")
                self.assertEqual(INS.evaluate_clearance(inputs()).status, INS.Status.VERIFIED_AGAINST_TABLE)
                self.assertEqual(ipc.creepage_mm(100, 2, "III"), 1.40)   # legacy router path keeps the shipped data
            finally:
                if old is None:
                    os.environ.pop(T.CONFIG_KEY, None)
                else:
                    os.environ[T.CONFIG_KEY] = old

    def test_loader_rejects_untraceable_data(self):
        bad = [
            lambda d: d.update(schema="x"),
            lambda d: d["tables"].update(made_up={"reference": "r"}),
            lambda d: d["tables"]["creepage"].pop("default_provenance"),
            lambda d: d["tables"]["creepage"].update(default_provenance={"status": "VERIFIED", "source": "s"}),
            lambda d: d["tables"]["creepage"]["columns"]["PD1"].update(values_mm=[0.1, 0.2]),
            lambda d: d["tables"]["clearance"].pop("reference"),
            lambda d: d["rules"]["creepage_reinforced_factor"].update(value=0.5),
        ]
        for i, m in enumerate(bad):
            with self.assertRaises(InsulationDataInvalid, msg=i):
                fixture(m)

    def test_per_cell_provenance_downgrades_status(self):
        def mut(d):
            d["tables"]["creepage"]["columns"]["PD2-III"]["values_mm"][1] = {
                "value": 1.4, "provenance": {"status": "PROVISIONAL", "source": "synthetic, unchecked"}}
        r = INS.evaluate_creepage(inputs(working_voltage_v=100), fixture(mut))
        self.assertEqual(r.status, INS.Status.PROVISIONAL)
        self.assertEqual(r.value_mm, 1.4)


class TestComplianceLanguage(unittest.TestCase):
    def _signoff(self, a, **kw):
        d = dict(signoff_id="INS-SO-TEST", reviewer="Test Reviewer", role="test", date="2026-11-21",
                 assessment_digest=a.digest(), dataset_id=a.dataset_id, scope="synthetic fixture only")
        d.update(kw)
        return INS.EngineeringSignoff(**d)

    def test_no_output_says_compliant_without_signoff(self):
        shipped = T.default_dataset()
        cases = [INS.assess(inputs(), fixture()), INS.assess(inputs(), shipped),
                 INS.assess(INS.InsulationInputs(), shipped),
                 INS.assess(inputs(insulation_type="reinforced", pollution_degree=None), fixture())]
        for a in cases:
            text = " ".join(strings(a.to_dict())) + a.summary() + a.compliance_statement()
            self.assertNotIn("compliant", text.lower())
            self.assertTrue(a.to_dict()["engineering_review_required"])

    def test_signoff_is_the_only_path_and_must_match(self):
        a = INS.assess(inputs(), fixture())
        self.assertEqual(a.status, INS.Status.VERIFIED_AGAINST_TABLE)
        ok = a.to_dict(self._signoff(a))
        self.assertIn("compliant", ok["compliance_statement"])
        self.assertFalse(ok["engineering_review_required"])
        stale = a.to_dict(self._signoff(a, assessment_digest="0" * 64))
        self.assertNotIn("compliant", stale["compliance_statement"].lower())
        prov = INS.assess(inputs(working_voltage_v=90), fixture())          # rounded up -> PROVISIONAL
        self.assertNotIn("compliant", prov.compliance_statement(self._signoff(prov)).lower())

    def test_signoff_record_validation(self):
        a = INS.assess(inputs(), fixture())
        with self.assertRaises(InsulationDataInvalid):
            self._signoff(a, reviewer=" ")
        with self.assertRaises(InsulationDataInvalid):
            self._signoff(a, date="21/11/2026")
        with self.assertRaises(InsulationDataInvalid):
            INS.EngineeringSignoff.from_dict({"signoff_id": "x"})


class TestConsumers(unittest.TestCase):
    BARRIER = {"name": "HV-SELV", "nets_a": ["VBUS"], "nets_b": ["3V3"], "working_voltage_v": 60.0,
               "insulation": "reinforced", "pollution_degree": 2, "material_group": "IIIa"}

    def profile(self, env=None, barrier=None):
        return DesignProfile(project_id="T_INS", voltage_rails={"VBUS": 60.0, "3V3": 3.3},
                             current_limits_A={"VBUS": 1.0, "3V3": 0.5}, spacing_policy="FUNCTIONAL",
                             insulation_barriers=[barrier or self.BARRIER], insulation_environment=env or {})

    def test_router_rule_is_unchanged_and_assessment_is_attached(self):
        p = self.profile({"coating": "none"})
        req = p.spacing_requirement("VBUS", "3V3")
        self.assertAlmostEqual(req.creepage_mm, 2.0 * ipc.creepage_mm(60.0, 2, "IIIa"))
        self.assertAlmostEqual(p.derive_clearance_mil("VBUS", "3V3"), req.router_rule_mil)
        ins = req.to_dict()["insulation"]
        self.assertEqual(ins["creepage"]["status"], "PROVISIONAL")
        self.assertEqual(ins["clearance"]["status"], "UNVERIFIED")      # no rated impulse / altitude / table
        self.assertNotIn("insulation", p.spacing_requirement("VBUS", "GND").to_dict())

    def test_legacy_barrier_defaults_are_not_inputs(self):
        p = self.profile(barrier={"name": "B", "nets_a": ["VBUS"], "nets_b": ["3V3"], "working_voltage_v": 60.0})
        a = p.insulation_assessments(T.default_dataset())[0]
        self.assertEqual(a.creepage.status, INS.Status.UNVERIFIED)
        for key in ("insulation_type", "pollution_degree", "material_group", "coating"):
            self.assertTrue(any(m.startswith(key) for m in a.creepage.missing_inputs), key)
        self.assertEqual(SP.parse_barriers([{"name": "B", "working_voltage_v": 60.0}])[0].pollution_degree, 2)

    def test_profile_hash_unchanged_without_insulation_environment(self):
        p = DesignProfile(project_id="T_INS", voltage_rails={"VBUS": 60.0})
        self.assertNotIn("insulation_environment", p.to_dict())
        q = DesignProfile.from_dict(self.profile({"altitude_m": 1000}).to_dict())
        self.assertEqual(q.insulation_environment, {"altitude_m": 1000})

    def test_routing_plan_reports_insulation_without_changing_constraints(self):
        graph = NetConnectivityGraph(nets={
            "VBUS": [NetEndpoint("U1", "1", "VBUS", 0.0, 0.0, 1), NetEndpoint("C1", "1", "VBUS", 5.0, 0.0, 1)],
            "3V3": [NetEndpoint("U1", "2", "3V3", 0.0, 1.0, 1), NetEndpoint("U2", "2", "3V3", 5.0, 1.0, 1)]})
        p = self.profile({"coating": "none", "altitude_m": 500})
        plan = RoutingPlanGenerator.generate_plan(graph, {}, (50.0, 50.0), rules={"power_nets": ["VBUS"]}, profile=p)
        self.assertEqual(len(plan.insulation), 1)
        self.assertEqual(plan.insulation[0]["label"], "HV-SELV")
        self.assertNotIn("compliant", " ".join(strings(plan.insulation)).lower())
        self.assertAlmostEqual(plan.net_constraints["VBUS"].clearance_mil,
                               p.worst_case_clearance_mil("VBUS", graph.nets)[0])


if __name__ == "__main__":
    unittest.main()
