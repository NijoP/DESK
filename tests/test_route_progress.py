import json
import os
import shutil
import tempfile
import unittest

from desk.runtime.route_progress import load_route_progress


class TestRouteProgress(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_rp_")
        self.route = os.path.join(self.d, "state", "route")
        os.makedirs(self.route)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _w(self, name, obj):
        with open(os.path.join(self.route, name), "w", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_absent_files_give_no_data_verdict(self):
        out = load_route_progress(self.d)
        self.assertEqual(out["verdict"], "NO_ROUTING_DATA")
        self.assertIsNone(out["progress"])
        self.assertEqual(out["stage_target_min"], 90)

    def test_progress_and_preflight_are_summarised(self):
        self._w("progress.json", {"phase": "routing", "engine": "v2.5.0", "elapsed_s": 100.0, "budget_s": 600.0, "passes": 4,
                                  "initial_unrouted": 42, "last_unrouted": 13, "best_unrouted": 13, "best_pass": 4,
                                  "passes_since_best": 0, "restores": 0, "problem_nets": ["GND", "USB_DP"],
                                  "history": [{"pass": i, "unrouted": 50 - i * 9} for i in range(1, 5)]})
        self._w("preflight.json", {"passed": True, "errors": [], "warnings": ["w"], "planes_in_dsn": 2, "planes_declared": 2,
                                   "outline_primitives": 1, "pads_in_router_keepouts": []})
        self._w("dense_analysis.json", {"overall_congestion": 0.98, "overloaded_cells": 43, "ratsnest_crossings": 218,
                                        "escape_summary": {"EASY_ESCAPE": 200}, "priority_net_order": ["USB_DP", "USB_DM"],
                                        "plane_nets": ["GND", "3V3"], "corridors": [],
                                        "hotspots": [{"region_id": "H1", "bbox_mm": [1, 2, 3, 4], "max_score": 1.3, "causes": ["x"], "recommended_strategy": "S"}]})
        out = load_route_progress(self.d)
        self.assertEqual(out["verdict"], "ROUTING")
        self.assertEqual(out["engine"], "v2.5.0")
        self.assertEqual(out["progress"]["time_remaining_s"], 500.0)
        self.assertEqual(out["progress"]["problem_nets"], ["GND", "USB_DP"])
        self.assertEqual(out["preflight"]["planes"], "2/2")
        self.assertEqual(out["dense"]["hotspot_regions"], 1)
        self.assertEqual(out["dense"]["hotspots"][0]["id"], "H1")
        json.dumps(out)

    def test_refused_preflight_and_stopped_run_verdicts(self):
        self._w("preflight.json", {"passed": False, "errors": ["keep-outs: 3 pads"], "warnings": [], "planes_in_dsn": 0,
                                   "planes_declared": 2, "outline_primitives": 36, "pads_in_router_keepouts": ["U1.1"]})
        self.assertEqual(load_route_progress(self.d)["verdict"], "PREFLIGHT_REFUSED")
        self._w("progress.json", {"phase": "timeout", "elapsed_s": 700, "budget_s": 600, "last_unrouted": 9})
        self.assertEqual(load_route_progress(self.d)["verdict"], "STOPPED_NO_SES")
        self._w("progress.json", {"phase": "finished", "elapsed_s": 300, "budget_s": 600, "last_unrouted": 0})
        self.assertEqual(load_route_progress(self.d)["verdict"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
