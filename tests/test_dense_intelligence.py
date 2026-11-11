"""Dense PCB intelligence, fixtures and placement refinement tests (synthetic boards; deterministic)."""
import copy
import unittest

from desk.routing.density import DensePCBIntelligence, dump_to_board_mm, MIL
from desk.routing.fixtures import make_board, SCENARIOS, plane_layers_from_planes, qfn, passive
from desk.placement_refine import PlacementRefiner


def engine_for(fx, grid=None):
    return DensePCBIntelligence(fx["dump"], fx["board_mm"], fx["origin_mm"], stackup=fx["stackup"],
                                plane_layers=plane_layers_from_planes(fx["planes"], fx["stackup"]),
                                keepouts_mm=fx["keepouts"], grid_mil=grid)


class TestFixtures(unittest.TestCase):
    def test_all_scenarios_build_valid_dumps(self):
        for sc in SCENARIOS:
            fx = make_board(sc)
            self.assertGreater(len(fx["dump"]), 3, sc)
            for ref, c in fx["dump"].items():
                self.assertIn("pads", c, ref)
                for p in c["pads"]:
                    self.assertEqual(len(p["shape"]), 4)
                    self.assertIn("net", p)

    def test_deterministic(self):
        a = make_board("dense_sensor", seed=3)["dump"]
        b = make_board("dense_sensor", seed=3)["dump"]
        self.assertEqual(a, b)
        c = make_board("dense_sensor", seed=4)["dump"]
        self.assertNotEqual(a, c)


class TestDensityEngine(unittest.TestCase):
    def test_empty_board_has_zero_congestion(self):
        r, c = passive("R1", 10, 10, "A", "B")
        eng = DensePCBIntelligence({r: c}, (20, 20))
        rep = eng.analyze()
        self.assertEqual(rep.overloaded_cells, 0)
        self.assertEqual(rep.hotspot_cells, 0)
        self.assertEqual(rep.hotspots, [])

    def test_fine_pitch_qfn_is_a_hotspot_with_escape_cause(self):
        fx = make_board("qfn_fine_pitch")
        rep = engine_for(fx).analyze()
        self.assertGreaterEqual(len(rep.hotspots), fx["expect"]["min_hotspots"])
        self.assertTrue(any("fine-pitch escape" in h.causes for h in rep.hotspots), [h.causes for h in rep.hotspots[:5]])
        self.assertGreater(rep.escape_summary.get("RESTRICTED_ESCAPE", 0) + rep.escape_summary.get("CRITICAL_ESCAPE", 0), 0)
        self.assertEqual(rep.hotspots[0].recommended_strategy, "ESCAPE_FIRST")

    def test_plane_layers_are_not_routable_for_signals(self):
        fx = make_board("esp32_4layer")
        eng = engine_for(fx)
        self.assertEqual(eng.routable_layers, [1, 4])
        rep = eng.analyze()
        self.assertEqual(sorted(rep.plane_nets), ["3V3", "GND"])
        self.assertNotIn("GND", rep.priority_net_order)

    def test_report_is_serialisable_and_mission_control_payload(self):
        fx = make_board("mcu_2layer_compact")
        rep = engine_for(fx).analyze(include_cells=True)
        import json
        d = rep.to_dict(include_cells=True)
        json.dumps(d)
        mc = rep.to_mission_control()
        self.assertIn("hotspots", mc)
        self.assertIn("priority_nets", mc)
        self.assertTrue(all(len(h["bbox_mm"]) == 4 for h in mc["hotspots"]))

    def test_incremental_update_matches_rebuild(self):
        fx = make_board("dense_sensor")
        eng = engine_for(fx, grid=50.0)
        eng.analyze()
        ref = next(r for r in eng.dump if r.startswith("C"))
        moved = copy.deepcopy(eng.dump[ref])
        moved["x"] += 3.0 * MIL
        eng.update_components({ref: moved})
        inc = eng.analyze()
        dump2 = copy.deepcopy(fx["dump"]); dump2[ref] = moved
        full = DensePCBIntelligence(dump2, fx["board_mm"], fx["origin_mm"], stackup=fx["stackup"],
                                    plane_layers=plane_layers_from_planes(fx["planes"], fx["stackup"]),
                                    keepouts_mm=fx["keepouts"], grid_mil=50.0).analyze()
        self.assertEqual(inc.ratsnest_crossings, full.ratsnest_crossings)
        self.assertAlmostEqual(inc.overall_congestion, full.overall_congestion, places=2)
        self.assertEqual(inc.overloaded_cells, full.overloaded_cells)

    def test_priority_puts_escape_constrained_and_diff_pairs_first(self):
        fx = make_board("esp32_4layer")
        rep = engine_for(fx).analyze()
        top = rep.priority_net_order[:8]
        self.assertTrue("USB_DP" in top or "USB_DM" in top, top)

    def test_analysis_is_fast(self):
        fx = make_board("multi_rail_limited_layers")
        rep = engine_for(fx).analyze()
        self.assertLess(rep.analysis_ms, 1500.0)

    def test_board_extent_fallback(self):
        fx = make_board("rf_board")
        (w, h), (ox, oy) = dump_to_board_mm(fx["dump"])
        self.assertGreater(w, 5); self.assertGreater(h, 5)


class TestPlacementRefiner(unittest.TestCase):
    def _plan(self, fx):
        return {"board_mm": list(fx["board_mm"]), "origin_mm": list(fx["origin_mm"]), "layers": len(fx["stackup"]),
                "keepouts": fx["keepouts"], "planes": fx["planes"], "parts": [], "roles": {}}

    def test_locked_parts_are_never_proposed(self):
        fx = make_board("mcu_2layer_compact")
        ref = PlacementRefiner(fx["dump"], self._plan(fx), stackup=fx["stackup"])
        res = ref.refine(max_moves=3)
        moved = {p.ref for p in res.proposals}
        for r in moved:
            self.assertNotIn(r, ref.locked)
            self.assertTrue(r[0] in "RCL", r)
        self.assertIn("U1", ref.locked)
        self.assertIn("J1", ref.locked)

    def test_proposals_only_improve_objective_and_respect_hard_rules(self):
        fx = make_board("dense_sensor")
        ref = PlacementRefiner(fx["dump"], self._plan(fx), stackup=fx["stackup"])
        res = ref.refine(max_moves=4)
        self.assertLessEqual(res.objective_end, res.objective_start)
        for p in res.proposals:
            self.assertGreater(p.improvement, 0)
            self.assertIsNone(ref._violates_hard_rules(p.ref, p.to_mm[0], p.to_mm[1], p.to_rot))

    def test_decoupling_proximity_is_preserved(self):
        fx = make_board("buck_boost")
        ref = PlacementRefiner(fx["dump"], self._plan(fx), stackup=fx["stackup"], decap_max_mm=1.0)
        for cap, anchor in ref._decap_anchor.items():
            x, y = ref._mm(cap)
            far = ref._violates_hard_rules(cap, x + 5.0, y, ref.dump[cap].get("rot") or 0)
            self.assertIsNotNone(far)

    def test_apply_writes_only_placement_json(self):
        import json, os, tempfile
        fx = make_board("dense_sensor")
        plan = self._plan(fx)
        plan["parts"] = [[r, c["x"] / MIL, c["y"] / MIL, c.get("rot") or 0, "T", "fixture"] for r, c in fx["dump"].items()]
        ref = PlacementRefiner(fx["dump"], plan, stackup=fx["stackup"])
        res = ref.refine(max_moves=2)
        d = tempfile.mkdtemp(prefix="desk_plan_")
        path = os.path.join(d, "placement.json")
        json.dump(plan, open(path, "w", encoding="utf-8"))
        with self.assertRaises(ValueError):
            ref.apply_to_plan(res, path, authorised_by="")
        n = ref.apply_to_plan(res, path, authorised_by="unit-test")
        self.assertEqual(n, len(res.proposals))
        saved = json.load(open(path, encoding="utf-8"))
        self.assertEqual(len(saved["refinement_log"]), 1)
        for p in res.proposals:
            part = next(x for x in saved["parts"] if x[0] == p.ref)
            self.assertAlmostEqual(part[1], p.to_mm[0], places=2)
            self.assertIn("refined", part[5])


if __name__ == "__main__":
    unittest.main()
