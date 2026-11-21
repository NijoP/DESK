"""Offline performance benchmark (roadmap I-10): the checked-in synthetic fixture and `profile_perf --offline`.

Smoke tests with generous ceilings: they prove the benchmark runs on a fresh clone and reports every stage, not that
DESK is fast. The measured numbers live in docs/performance/BENCHMARK_REPORT.md (taken from CI). Software-only,
synthetic fixture; nothing here touches EasyEDA, Freerouting or the network.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from desk import perf_bench as pb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestSyntheticFixture(unittest.TestCase):

    def test_checked_in_fixture_matches_the_generator(self):
        with open(pb.FIXTURE_PATH, encoding="utf-8") as f:
            on_disk = f.read().replace("\r\n", "\n")
        self.assertEqual(on_disk, pb.fixture_json(pb.generate_fixture()),
                         "tests/fixtures/perf/synth_board.json is stale: run python tools/profile_perf.py --write-fixture")

    def test_fixture_is_watch_sized_and_marked_synthetic(self):
        fx = pb.load_fixture()
        self.assertIn("not a real design", fx["note"])
        c = pb.board_counts(fx["dump"])
        self.assertEqual((c["components"], c["pads"], c["nets"]), (41, 162, 49))
        for ref, comp in fx["dump"].items():
            for key in ("x", "y", "layer", "bbox", "pads", "fp"):
                self.assertIn(key, comp, ref)

    def test_scaling_copies_signal_nets_and_shares_power_nets(self):
        fx = pb.load_fixture()
        base = pb.board_counts(fx["dump"])
        x4 = pb.scale_fixture(fx, 4)
        c = pb.board_counts(x4["dump"])
        self.assertEqual(c["components"], 4 * base["components"])
        self.assertEqual(c["pads"], 4 * base["pads"])
        self.assertEqual(c["nets"], 4 * (base["nets"] - len(pb.SHARED_NETS)) + len(pb.SHARED_NETS))
        self.assertEqual(x4["plan"]["board_mm"], [100.0, 80.0])
        with self.assertRaises(ValueError):
            pb.scale_fixture(fx, 0)

    def test_synthetic_ses_and_drc_are_parsed_by_the_real_parsers(self):
        from desk.drc_engine import DRCParser
        from desk.routing.connectivity import SESParser
        dump = pb.load_fixture()["dump"]
        tracks, vias = SESParser.parse_ses_copper(pb.synthetic_ses(dump))
        self.assertGreater(len(tracks), 100)
        self.assertGreater(len(vias), 10)
        self.assertGreater(len(DRCParser.parse(pb.synthetic_drc(dump))), 10)


class TestOfflineRun(unittest.TestCase):

    def test_every_offline_stage_is_measured_and_live_stages_are_not(self):
        res = pb.run_offline(pb.load_fixture(), repeat=1)
        self.assertEqual(set(res["stages"]), set(pb.STAGE_NAMES))
        for name, s in res["stages"].items():
            self.assertGreaterEqual(s["median_wall_ms"], 0.0, name)
            self.assertLess(s["median_wall_ms"], 10000.0, name)   # generous ceiling: a smoke test, not a budget
            self.assertGreaterEqual(s["peak_traced_kb"], 0.0, name)
        self.assertEqual(res["hotspots"][0]["stage"], max(res["stages"], key=lambda n: res["stages"][n]["median_wall_ms"]))
        self.assertAlmostEqual(sum(h["share"] for h in res["hotspots"]), 1.0, places=2)
        for live in ("01_bridge_discovery", "14_freerouting_execution", "16_drc_execution"):
            self.assertIn(live, res["not_measured"])
            self.assertNotIn(live, res["stages"])
        rss = pb.peak_rss_mb()
        if rss is not None:
            self.assertGreater(rss, 1.0)

    def test_offline_run_restores_an_active_tracemalloc_session(self):
        import tracemalloc
        tracemalloc.start()
        try:
            pb.run_offline(pb.load_fixture(), repeat=1)
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()

    def test_cli_offline_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, md = os.path.join(tmp, "perf.json"), os.path.join(tmp, "perf.md")
            cp = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "profile_perf.py"), "--offline", "--scale", "1",
                                 "--repeat", "1", "--out", out, "--summary", md], capture_output=True, text=True,
                                timeout=300, cwd=ROOT)
            self.assertEqual(cp.returncode, 0, cp.stderr[-2000:])
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["schema"], "desk.perf.offline/1")
            self.assertEqual(len(data["runs"]), 1)
            self.assertNotIn("error", data["runs"][0])
            self.assertEqual(data["runs"][0]["scale"], 1)
            self.assertIsNotNone(data["cold_engine_import"]["median_ms"])
            self.assertIn("not validated on a live design", data["note"])
            with open(md, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("08_mst_computation", text)
            self.assertIn("Not measured offline", text)


if __name__ == "__main__":
    unittest.main()
