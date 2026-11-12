"""Routing recoverability: adaptive chunks, the SES checkpoint, engine profiles and outcome naming.

Regression fixtures reproduce UPS_1000 (live-test/ups-1000/builder-records): pass durations of 184 / 36 / 35 / 126 / 26 s
on a 300 s chunk window, a chunk that times out after five passes with no SES, attempt 6's 420 s TIMEOUT with 3
passes, the 2.1.0 probe that blocks, and the engine that ignores its limits. Engine runs are mocked; no Java.
"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from desk.errors import DesignProfileInvalid
from desk.reliability import failure_classifier as FC
from desk.reliability.models import FailureCategory as C
from desk.routing import engine_profiles as EP
from desk.routing.adaptive import ChunkPlanner, PassStats, chunk_outcome
from desk.routing.checkpoint import RoutingCheckpoint, validate_ses
from desk.routing.orchestrator import RoutingEngineOrchestrator, EngineExecutionResult

UPS_PASSES = [184.24, 35.67, 34.94, 126.35, 26.44]      # freerouting.log of attempt 5

SES_OK = "(session x (routes (resolution mil 10) (network_out (net N1 (wire (path TopLayer 60 0 0 1000 0)) (via V1 500 500)))))\n"


def ses(path, text=SES_OK):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Planner(unittest.TestCase):
    def test_first_chunk_measures_with_few_passes(self):
        p = ChunkPlanner(window_s=300, max_passes=8, first_passes=2)
        plan = p.plan(PassStats(), remaining_s=900)
        self.assertEqual((plan.passes, plan.timeout_s, plan.confidence), (2, 300.0, "UNVERIFIED"))

    def test_ups_pass_times_give_one_pass_chunks_with_a_long_enough_window(self):
        st = PassStats(list(UPS_PASSES))
        plan = ChunkPlanner(window_s=300, safety=0.6, max_passes=8).plan(st, remaining_s=900)
        self.assertEqual(plan.passes, 1)
        self.assertGreaterEqual(plan.timeout_s, 184.24 / 0.6)        # the slowest pass fits
        self.assertEqual(plan.confidence, "MEASURED")
        self.assertTrue(plan.bounded)

    def test_fast_board_fills_the_window_up_to_the_cap(self):
        st = PassStats([10.0, 12.0, 11.0, 9.0])
        plan = ChunkPlanner(window_s=300, safety=0.6, max_passes=8).plan(st, remaining_s=900)
        self.assertEqual(plan.passes, 8)
        self.assertEqual(plan.timeout_s, 300.0)

    def test_budget_too_small_for_one_pass_stops(self):
        plan = ChunkPlanner(window_s=300).plan(PassStats([200.0, 210.0, 190.0]), remaining_s=100)
        self.assertEqual(plan.passes, 0)

    def test_unboundable_engine_is_reported_not_planned(self):
        plan = ChunkPlanner(window_s=300, profile=EP.profile_for("v2.1.0")).plan(PassStats(), 900)
        self.assertFalse(plan.bounded)
        self.assertIn("ignores max_passes", plan.reason)

    def test_p95_uses_max_until_three_samples_and_never_ignores_a_recent_slow_pass(self):
        self.assertEqual(PassStats([5.0, 50.0]).p95(), 50.0)
        self.assertEqual(PassStats([1.0] * 19 + [100.0]).p95(), 100.0)      # the last pass was slow: it must fit
        self.assertEqual(PassStats([100.0] + [1.0] * 19).p95(), 1.0)        # an early outlier no longer dominates


class Outcomes(unittest.TestCase):
    def test_names(self):
        self.assertEqual(chunk_outcome(True, 5, False, None, 1, 4, 70, None), "ENGINE_IGNORES_LIMITS")   # UPS attempt 5 with a bounded plan
        self.assertEqual(chunk_outcome(True, 3, False, None, 1, None, 90, None), "CHUNK_TIMEOUT")
        self.assertEqual(chunk_outcome(True, 0, False, None, 1, 2, None, None), "ZERO_PASSES_TIMEOUT")   # UPS attempt 3
        self.assertEqual(chunk_outcome(False, 0, False, None, 1, 2, None, None), "ENGINE_CRASH")
        self.assertEqual(chunk_outcome(False, 4, False, None, 0, 4, 10, None), "SES_NOT_GENERATED")
        self.assertEqual(chunk_outcome(False, 4, True, False, 0, 4, 10, None), "SES_CORRUPTED")
        self.assertEqual(chunk_outcome(False, 4, True, True, 0, 4, 10, False), "SES_NOT_IMPROVED")
        self.assertEqual(chunk_outcome(False, 4, True, True, 0, 4, 7, True), "PARTIAL_ROUTING_SUCCESS")
        self.assertEqual(chunk_outcome(False, 4, True, True, 0, 4, 0, True), "FULL_ROUTING_SUCCESS")
        self.assertEqual(chunk_outcome(False, 4, True, True, 1, 4, 3, True, status="TIMEOUT_PARTIAL"), "ENGINE_TIMEOUT")


class Checkpoint(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_ckpt_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_validate_rejects_truncated_and_empty(self):
        p = os.path.join(self.d, "a.ses")
        ses(p, "(session x (routes (network_out (net N1 (wire (path TopLayer 60 0 0 1 1")
        self.assertFalse(validate_ses(p).valid)
        self.assertIn("unbalanced", validate_ses(p).reason)
        ses(p, "")
        self.assertEqual(validate_ses(p).reason, "empty")
        ses(p, "(session x (routes (network_out)))")
        self.assertIn("no routed wires", validate_ses(p).reason)
        ses(p)
        v = validate_ses(p)
        self.assertTrue(v.valid)
        self.assertEqual((v.tracks, v.vias, v.nets), (1, 1, 1))

    def test_never_discards_best_on_worse_invalid_or_missing(self):
        ck = RoutingCheckpoint(self.d, dsn_sha256="abc")
        good = os.path.join(self.d, "c1.ses")
        ses(good)
        self.assertTrue(ck.offer(good, 70, 1)["accepted"])
        worse = os.path.join(self.d, "c2.ses")
        ses(worse)
        self.assertFalse(ck.offer(worse, 90, 2)["accepted"])
        bad = os.path.join(self.d, "c3.ses")
        ses(bad, "(session (routes (network_out (net N1 (wire (path TopLayer 60 0 0")
        self.assertFalse(ck.offer(bad, 10, 3)["accepted"])
        self.assertFalse(ck.offer(os.path.join(self.d, "missing.ses"), 1, 4)["accepted"])
        self.assertEqual(ck.best_unrouted, 70)
        self.assertTrue(ck.has_best())
        self.assertIn("(via V1", open(ck.best_path).read())
        st = json.load(open(ck.manifest))
        self.assertEqual(len(st["rejected"]), 2)
        self.assertEqual(st["best_from_chunk"], 1)

    def test_dsn_change_archives_and_resets(self):
        ck = RoutingCheckpoint(self.d, dsn_sha256="one")
        p = os.path.join(self.d, "c.ses")
        ses(p)
        ck.offer(p, 5, 1)
        ck2 = RoutingCheckpoint(self.d, dsn_sha256="two")
        self.assertIsNone(ck2.best_unrouted)
        self.assertTrue(any(f.startswith("best_dsn-changed") for f in os.listdir(self.d)))

    def test_observed_best_is_tracked_without_a_ses(self):
        ck = RoutingCheckpoint(self.d)
        for u in (106, 97, 89, 86, 70):
            ck.observe_pass(u)
        self.assertEqual(ck.state.observed_best_unrouted, 70)
        self.assertIsNone(ck.best_unrouted)


def result(ses_path, status, passes, initial, final, write, seconds, history=None, rc=0, version="v2.5.0"):
    if write:
        ses(ses_path)
    return EngineExecutionResult(success=status == "SUCCESS", status=status, engine_name="Freerouting", engine_version=version,
                                 engine_path="x.jar", command=["java"], duration_sec=seconds, returncode=rc, passes_completed=passes,
                                 initial_unrouted=initial, final_unrouted=final, ses_generated=write, ses_path=ses_path if write else None,
                                 ses_size_bytes=os.path.getsize(ses_path) if write else 0, best_unrouted=final,
                                 pass_history=history or [{"pass": i + 1, "seconds": seconds / max(1, passes), "unrouted": final} for i in range(passes)])


class ChunkedRuns(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_chunkrun_")
        self.dsn = os.path.join(self.d, "b.dsn")
        with open(self.dsn, "w") as f:
            f.write("(pcb)")
        self.orch = RoutingEngineOrchestrator(tools_dir=self.d)
        self.out = os.path.join(self.d, "out.ses")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _run(self, script, **kw):
        calls = []

        def fake(**kwargs):
            calls.append(kwargs)
            step = script[min(len(calls) - 1, len(script) - 1)]
            return step(kwargs["ses_path"], kwargs)
        with mock.patch.object(self.orch, "execute_routing", side_effect=fake):
            res = self.orch.execute_routing_chunked(self.dsn, self.out, self.d, engine_version_hint="v2.5.0", budget_sec=3000, **kw)
        return res, calls

    def test_timed_out_chunk_never_discards_the_best_ses(self):
        script = [lambda p, k: result(p, "SUCCESS", 2, 106, 70, True, 220.0, history=[{"pass": 1, "seconds": 184.24, "unrouted": 97}, {"pass": 2, "seconds": 35.67, "unrouted": 70}]),
                  lambda p, k: result(p, "TIMEOUT", 1, 70, 65, False, 420.0, history=[{"pass": 1, "seconds": 300.0, "unrouted": 65}])]
        res, calls = self._run(script, chunk_passes=8, chunk_timeout_sec=300)
        self.assertTrue(res.ses_generated)
        self.assertEqual(res.final_unrouted, 70)                    # checkpoint best, not lost
        self.assertEqual(res.engine_config["observed_best_unrouted"], 65)
        self.assertEqual(res.engine_config["chunk_outcomes"][-1], "CHUNK_TIMEOUT")
        self.assertEqual(res.engine_config["failure_category"], "ROUTER_ENGINE_TIMEOUT")
        self.assertIn("(via V1", open(self.out).read())
        self.assertTrue(calls[1]["input_ses"].endswith("chunk_best.ses"))
        self.assertEqual(calls[1]["max_passes"], 1)                 # planned from 184 s passes: one pass per chunk
        self.assertGreater(calls[1]["timeout_sec"], 300.0)          # with a window long enough for it

    def test_best_unrouted_is_reported_after_a_timeout_without_ses(self):
        script = [lambda p, k: result(p, "TIMEOUT", 5, 106, 70, False, 420.24,
                                      history=[{"pass": i + 1, "seconds": s, "unrouted": u} for i, (s, u) in enumerate(zip(UPS_PASSES, (106, 97, 89, 86, 70)))])]
        res, calls = self._run(script, chunk_passes=4, chunk_timeout_sec=300, first_passes=4)
        self.assertFalse(res.ses_generated)
        self.assertEqual(res.best_unrouted, 70)                     # UPS progress_chunks.json said null
        self.assertEqual(res.engine_config["chunk_outcomes"], ["ENGINE_IGNORES_LIMITS"])   # 5 passes ran for a 4-pass plan
        self.assertEqual(res.engine_config["failure_category"], "EXTERNAL_TOOL_UNSUPPORTED")
        self.assertIn("EXTERNAL_TOOL_UNSUPPORTED", res.error_message)

    def test_zero_passes_in_chunk_is_not_a_plain_timeout(self):
        script = [lambda p, k: result(p, "TIMEOUT", 0, None, None, False, 420.14, history=[])]
        res, _ = self._run(script)
        self.assertEqual(res.engine_config["chunk_outcomes"], ["ZERO_PASSES_TIMEOUT"])
        self.assertEqual(res.engine_config["failure_category"], "ROUTER_ENGINE_CRASH")

    def test_unboundable_engine_is_refused_before_the_first_chunk(self):
        calls = []
        with mock.patch.object(self.orch, "execute_routing", side_effect=lambda **k: calls.append(k)):
            res = self.orch.execute_routing_chunked(self.dsn, self.out, self.d, engine_version_hint="v2.1.0")
        self.assertEqual(calls, [])
        self.assertEqual(res.status, "ENGINE_UNBOUNDABLE")
        self.assertEqual(res.engine_config["failure_category"], "EXTERNAL_TOOL_UNSUPPORTED")
        self.assertIn("2.5", res.error_message)

    def test_corrupt_ses_stops_and_keeps_previous_best(self):
        script = [lambda p, k: result(p, "SUCCESS", 2, 50, 20, True, 40.0),
                  lambda p, k: (ses(p, "(session (routes (network_out (net N1 (wire (path TopLayer 60 0 0") or
                                result(p, "SUCCESS", 2, 20, 10, False, 40.0))]
        # second chunk: the file exists but is truncated; EngineExecutionResult must say ses_generated=True
        def second(p, k):
            ses(p, "(session (routes (network_out (net N1 (wire (path TopLayer 60 0 0")
            r = result(p, "SUCCESS", 2, 20, 10, False, 40.0)
            r.ses_generated, r.ses_path, r.ses_size_bytes = True, p, os.path.getsize(p)
            return r
        res, _ = self._run([script[0], second])
        self.assertEqual(res.engine_config["chunk_outcomes"], ["PARTIAL_ROUTING_SUCCESS", "SES_CORRUPTED"])
        self.assertEqual(res.final_unrouted, 20)
        self.assertEqual(res.engine_config["failure_category"], "ROUTER_SES_INVALID")

    def test_full_success_and_plans_are_recorded(self):
        script = [lambda p, k: result(p, "SUCCESS", 2, 30, 8, True, 20.0), lambda p, k: result(p, "SUCCESS", 6, 8, 0, True, 50.0)]
        res, calls = self._run(script, chunk_passes=6)
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(len(res.engine_config["plans"]), 2)
        self.assertEqual(res.engine_config["plans"][1]["confidence"], "MEASURED")
        prog = json.load(open(os.path.join(self.d, "progress_chunks.json")))
        self.assertEqual(prog["best_unrouted"], 0)
        self.assertEqual(prog["checkpoint"]["best_from_chunk"], 2)


class Profiles(unittest.TestCase):
    def test_lookup_and_boundability(self):
        self.assertIs(EP.profile_for("v2.1.0").boundable, False)
        self.assertIs(EP.profile_for("v2.5.0").boundable, True)
        self.assertIsNone(EP.profile_for("v2.4.1").boundable)       # not measured: say so
        self.assertEqual(EP.profile_for("v9.9").name, "unknown")
        self.assertFalse(EP.profile_for("v2.1.0").can_stop_gracefully("nt"))
        self.assertTrue(EP.profile_for("v2.1.0").probe_blocks_online)
        self.assertEqual(EP.profile_for("v2.5.0").java_min, 25)

    def test_java_major(self):
        self.assertEqual(EP.java_major('openjdk version "25" 2025-09-16'), 25)
        self.assertEqual(EP.java_major('java version "1.8.0_292"'), 8)
        self.assertIsNone(EP.java_major(""))

    def test_every_measured_claim_cites_evidence(self):
        for p in EP.PROFILES:
            if p.verified:
                self.assertTrue(p.evidence, p.name)


class Classification(unittest.TestCase):
    def test_unresolvable_engine_path_is_classified(self):
        cat, _ = FC.classify_exception(RuntimeError("No compatible Freerouting engine found in 'C:\\x'. Install a Java runtime matching the JAR or set FREEROUTING_JAR."))
        self.assertEqual(cat, C.EXTERNAL_TOOL_UNSUPPORTED)
        cat, _ = FC.classify_exception(FileNotFoundError("/c/freerouting.jar"))
        self.assertEqual(cat, C.EXTERNAL_TOOL_UNSUPPORTED)

    def test_engine_results(self):
        self.assertEqual(FC.classify_engine_result("TIMEOUT"), C.ROUTER_ENGINE_TIMEOUT)
        self.assertEqual(FC.classify_engine_result("SUCCESS", ses_generated=True, final_unrouted=0), None)
        self.assertEqual(FC.classify_engine_result("SUCCESS", ses_generated=True, final_unrouted=7), C.ROUTER_STAGNATION)
        self.assertEqual(FC.classify_engine_result("CRASHED", stderr="Exception in thread main java.lang.UnsupportedClassVersionError"), C.JAVA_RUNTIME_INCOMPATIBLE)
        self.assertEqual(FC.classify_engine_result("CRASHED", stdout="java.lang.OutOfMemoryError: Java heap space"), C.ROUTER_RESOURCE_EXHAUSTION)
        self.assertEqual(FC.classify_engine_result("TIMEOUT", {"failure_category": "EXTERNAL_TOOL_UNSUPPORTED"}), C.EXTERNAL_TOOL_UNSUPPORTED)

    def test_invalid_profile_is_classified_not_ignored(self):
        d = tempfile.mkdtemp(prefix="desk_prof_")
        p = os.path.join(d, "design_profile.json")
        from desk.profile import DesignProfile
        prof = DesignProfile(project_id="X").to_dict()
        prof["stackup"][0]["name_note"] = "hand-edited"             # UPS_1000 F-011
        json.dump(prof, open(p, "w"))
        with self.assertRaises(DesignProfileInvalid) as cm:
            DesignProfile.load(p)
        self.assertEqual(cm.exception.context["key"], "name_note")
        self.assertEqual(FC.classify_exception(cm.exception)[0], C.DESIGN_PROFILE_INVALID)
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
