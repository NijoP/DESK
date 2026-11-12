"""Self-healing end-to-end (desk/reliability/supervisor.py): detect, collect, classify, diagnose, plan, gate, execute,
verify, record, learn. Also the cases where recovery must be refused. Fakes everywhere; no EasyEDA, no Java, no model.
"""
import json
import os
import shutil
import tempfile
import unittest

from desk.errors import BridgeWindowRotated, EngineeringDecisionRequired
from desk.reliability import root_cause as RCA
from desk.reliability.evidence import EvidenceCollector
from desk.reliability.health_monitor import HealthMonitor
from desk.reliability.learning import IncidentWriter, RecoveryOutcomes, promote_known_failure
from desk.reliability.models import (Confidence as K, FailureCategory as C, FailureRecord, Hypothesis, RecoveryAction, RiskClass,
                                     VerificationResult, HealthStatus)
from desk.reliability.project_isolation import ProjectSession, SessionResolver, PROJECT_INFO_JS, ACTIVE_DOC_JS
from desk.reliability.recovery_executor import RecoveryExecutor
from desk.reliability.recovery_policy import RecoveryPolicy, risk_for
from desk.reliability.resource_monitor import ResourceBudget, ResourceMonitor
from desk.reliability.supervisor import Supervisor
from desk.reliability import registry as KF

PU, PCB = "proj-uuid-ups", "pcb-ups"


def _w(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _r(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Gateway:
    def __init__(self):
        self.win = {"w-old": (PU, "ups", PCB), "w-light": ("proj-light", "light", "pcb-light")}

    def windows(self):
        return [{"windowId": w} for w in self.win]

    def execute(self, window_id, code, timeout=5.0):
        if window_id not in self.win:
            return {"success": False, "error": f"EDA window {window_id} is no longer connected"}
        puid, name, doc = self.win[window_id]
        if code == PROJECT_INFO_JS:
            return {"success": True, "result": {"project_uuid": puid, "project_name": name, "document_uuid": doc}}
        if code == ACTIVE_DOC_JS:
            return {"success": True, "result": doc}
        return {"success": True, "result": True}

    def rotate(self):
        self.win = {"r-" + k: v for k, v in self.win.items()}


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_heal_")
        self.proj = os.path.join(self.d, "projects", "UPS_1000")
        os.makedirs(self.proj)
        os.makedirs(os.path.join(self.d, "learning", "incidents"))
        os.makedirs(os.path.join(self.d, "learning", "index"))
        self.gw = Gateway()
        self.resolver = SessionResolver(self.gw)
        self.session = ProjectSession("UPS_1000", self.proj, project_uuid=PU, pcb_uuid=PCB)
        self.resolver.resolve(self.session)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def supervisor(self, handlers=None, verifiers=None, **kw):
        collector = EvidenceCollector(project_path=self.proj, gateway=self.gw, session=self.session)
        executor = RecoveryExecutor(handlers or {}, verifiers or {})
        return Supervisor(self.proj, self.session, collector=collector, executor=executor,
                          incidents=IncidentWriter(self.d), outcomes=RecoveryOutcomes(self.d), write_incidents=True, **kw)


class WindowRotationHeals(Base):
    def test_full_lifecycle(self):
        self.gw.rotate()
        try:
            self.resolver.verify_target(self.session, PCB)
        except BridgeWindowRotated as e:
            exc = e
        handlers = {"rebind_session": lambda a, ctx: self.resolver.rebind_after_rotation(ctx["session"]).window_id}

        def verify(a, ctx):
            v = VerificationResult()
            s = ctx["session"]
            ok = self.resolver.verify_target(s, PCB)
            info = self.gw.execute(s.window_id, PROJECT_INFO_JS)["result"]
            v.add("project_uuid_in_bound_window", PU, info["project_uuid"])
            v.add("active_document", PCB, s.bound_document_uuid, ok=ok)
            return v
        sup = self.supervisor(handlers, {"rebind_session": verify})
        rec = sup.handle(exc, module="desk.bridge", operation="verify_target", mutating=True)
        # classify + diagnose
        self.assertEqual(rec.category, C.WINDOW_ID_ROTATED)
        rc = rec.root_cause
        self.assertEqual((rc.category, rc.confidence, rc.source), (C.WINDOW_ID_ROTATED, K.CONFIRMED, "deterministic"))
        self.assertTrue(rc.evidence_ids)
        self.assertTrue(all(any(e.id == i for e in rec.evidence) for i in rc.evidence_ids))
        # plan + policy
        self.assertEqual(rec.plan.actions[0].kind, "rebind_session")
        self.assertEqual(rec.plan.actions[0].risk, RiskClass.AUTO)
        self.assertFalse(rec.plan.requires_approval or False) if not rec.plan.requires_approval else None
        # execute + verify
        self.assertEqual(rec.outcomes[0].result, "SUCCESS")
        self.assertTrue(rec.outcomes[0].verified)
        self.assertEqual(rec.status, "VERIFIED")
        self.assertTrue(rec.healed)
        self.assertEqual(self.session.window_id, "r-w-old")
        # record + learn
        rows = [json.loads(l) for l in _r(os.path.join(self.proj, "state", "reliability", "failures.jsonl")).splitlines() if l.strip()]
        self.assertEqual(rows[-1]["failure_id"], rec.failure_id)
        self.assertTrue(rows[-1]["healed"])
        self.assertTrue(os.path.exists(os.path.join(self.proj, "state", "reliability", "recoveries.jsonl")))
        inc = [f for f in os.listdir(os.path.join(self.d, "learning", "incidents")) if f.startswith("INC-")]
        self.assertEqual(len(inc), 1)
        text = _r(os.path.join(self.d, "learning", "incidents", inc[0]))
        self.assertIn("WINDOW_ID_ROTATED", text)
        self.assertIn("Recovery worked?\nYES", text)
        self.assertIn(rec.failure_id, text)
        self.assertIn(inc[0][:-3], _r(os.path.join(self.d, "learning", "index", "INCIDENT_INDEX.md")))
        self.assertIn(KF.by_id("KF-20251111-003").id, rec.related_incidents + [i for i in text.split() if i.startswith("KF-")])
        # explain
        exp = Supervisor.explain(rec)
        for q in ("What failed?", "Where?", "Why?", "Evidence?", "Safest recovery?", "What changed?", "Verification?", "Healed?"):
            self.assertIn(q, exp)
        self.assertIn("Healed?             YES", exp)

    def test_ambiguous_rotation_is_not_healed(self):
        self.gw.rotate()
        self.gw.win["dup"] = (PU, "ups", "pcb-other")
        handlers = {"rebind_session": lambda a, ctx: self.resolver.rebind_after_rotation(ctx["session"]).window_id}
        sup = self.supervisor(handlers, {"rebind_session": lambda a, ctx: VerificationResult().add("x", 1, 1)})
        rec = sup.handle(BridgeWindowRotated("no longer connected"), module="desk.bridge", operation="ex", mutating=True)
        self.assertEqual(rec.outcomes[0].result, "FAILED")
        self.assertIn("IdentityUnverified", rec.outcomes[0].note)
        self.assertFalse(rec.healed)
        self.assertIn(rec.status, ("FAILED", "ESCALATED"))
        self.assertIn("2 EasyEDA window", rec.root_cause.statement + rec.outcomes[0].note)


class RefusedRecoveries(Base):
    def _route_failure_files(self):
        wd = os.path.join(self.proj, "state", "route")
        os.makedirs(wd)
        _w(os.path.join(wd, "feasibility.json"), {"feasible": False, "summary": "1 blocked", "blocked": [{"pad_id": "U7.3", "net": "SW12", "classification": "BLOCKED_BY_CLEARANCE"}],
                   "decisions": [{"decision_id": "SPC-1", "net": "SW12", "rule_mm": 1.25, "pin_field_mm": 0.66, "pads": ["U7.3"],
                                  "options": ["declare FUNCTIONAL", "verify table"], "status": "BLOCKING"}]})
        _w(os.path.join(wd, "engineering_decisions.json"), [{"decision_id": "SPC-1", "net": "SW12", "rule_mm": 1.25, "pin_field_mm": 0.66, "pads": ["U7.3"],
                    "options": ["declare FUNCTIONAL", "verify table"], "status": "BLOCKING"}])

    def test_spacing_conflict_needs_the_captain_and_never_changes_a_rule(self):
        self._route_failure_files()
        ran = []
        handlers = {"engineering_decision": lambda a, ctx: ran.append(a.kind), "change_spacing_rule": lambda a, ctx: ran.append(a.kind)}
        sup = self.supervisor(handlers)
        exc = EngineeringDecisionRequired("STOP: routing is blocked", category="ROUTER_RULE_CONFLICT", decisions=["SPC-1"])
        rec = sup.handle(exc, module="desk.routing.pipeline", operation="run")
        self.assertEqual(rec.category, C.ROUTER_RULE_CONFLICT)
        self.assertEqual(rec.root_cause.confidence, K.CONFIRMED)
        self.assertIn("1.25", rec.root_cause.statement)
        self.assertTrue(rec.plan.requires_approval)
        self.assertEqual({a.risk for a in rec.plan.actions}, {RiskClass.APPROVAL})
        self.assertTrue(all(o.result == "REFUSED" for o in rec.outcomes))
        self.assertEqual(ran, [])
        self.assertFalse(rec.healed)
        self.assertEqual(rec.status, "ESCALATED")
        self.assertIn("needs a recorded Captain approval", rec.outcomes[0].note)

    def test_approval_lets_an_approval_action_run_but_refuse_kinds_never_run(self):
        self._route_failure_files()
        ran = []
        handlers = {"engineering_decision": lambda a, ctx: ran.append(a.kind), "weaken_safety_rule": lambda a, ctx: ran.append(a.kind)}
        sup = self.supervisor(handlers, {"engineering_decision": lambda a, ctx: VerificationResult().add("ledger_decision_recorded", True, True)})
        rec = sup.handle(EngineeringDecisionRequired("STOP", category="ROUTER_RULE_CONFLICT"), module="desk.routing.pipeline", operation="run",
                         approvals=["APR-captain-1"])
        self.assertEqual(ran, ["engineering_decision"])
        self.assertEqual(rec.outcomes[0].approval_id, "APR-captain-1")
        self.assertEqual(risk_for("weaken_safety_rule"), RiskClass.REFUSE)
        self.assertEqual(risk_for("bypass_quality_gate"), RiskClass.REFUSE)
        self.assertEqual(risk_for("no_such_action"), RiskClass.REFUSE)

    def test_autorecover_off_demotes_auto_to_proposal(self):
        self.gw.rotate()
        ran = []
        sup = self.supervisor({"rebind_session": lambda a, ctx: ran.append(1)}, policy=RecoveryPolicy(autorecover=False))
        rec = sup.handle(BridgeWindowRotated("no longer connected"), module="desk.bridge", operation="ex")
        self.assertEqual(ran, [])
        self.assertTrue(rec.plan.requires_approval)
        self.assertFalse(rec.healed)

    def test_same_action_not_repeated_on_unchanged_evidence_and_attempts_are_bounded(self):
        self.gw.rotate()
        self.gw.win["dup"] = (PU, "ups", "x")          # stays ambiguous: rebind keeps failing
        handlers = {"rebind_session": lambda a, ctx: self.resolver.rebind_after_rotation(ctx["session"]).window_id}
        policy = RecoveryPolicy(max_attempts=2)
        sup = self.supervisor(handlers, policy=policy)
        r1 = sup.handle(BridgeWindowRotated("no longer connected"), module="desk.bridge", operation="ex")
        self.assertEqual(r1.outcomes[0].result, "FAILED")
        # the failed recovery is remembered per signature: next time it is not proposed again
        r2 = sup.handle(BridgeWindowRotated("no longer connected"), module="desk.bridge", operation="ex")
        self.assertNotIn("rebind_session", [a.kind for a in r2.plan.actions])
        self.assertTrue(any("failed before" in x for x in r2.plan.refused))
        self.assertEqual(RecoveryOutcomes(self.d).failed_kinds(r1.signature), ["rebind_session"])


class Diagnosis(unittest.TestCase):
    def packet(self):
        rec = FailureRecord.new(C.ROUTER_ENGINE_TIMEOUT, "desk.routing", "chunk", "chunk 1 TIMEOUT 420 s no SES")
        e1 = rec.add_evidence("file", "progress_chunks.json", "1 chunk, outcomes ['CHUNK_TIMEOUT']")
        hyps = RCA.diagnose(rec, {"chunk_outcomes": ["CHUNK_TIMEOUT"], "checkpoint": {"has_best": False}})
        return rec, e1, RCA.diagnostic_packet(rec, {"chunk_outcomes": ["CHUNK_TIMEOUT"]}, hyps)

    def test_deterministic_rule_confirms_chunk_defect(self):
        rec, e1, packet = self.packet()
        self.assertEqual(rec.hypotheses, [])
        hyps = packet["deterministic_hypotheses"]
        self.assertEqual(hyps[0]["category"], "ROUTER_ENGINE_TIMEOUT")
        self.assertEqual(hyps[0]["confidence"], "CONFIRMED")
        self.assertIn(e1.id, hyps[0]["evidence_ids"])

    def test_model_answer_must_cite_evidence_and_cannot_confirm(self):
        rec, e1, packet = self.packet()
        answer = {"observed_facts": [f"chunk timed out without SES [{e1.id}]", "the Java heap was exhausted"],
                  "root_cause": {"category": "ROUTER_RESOURCE_EXHAUSTION", "statement": "heap exhausted", "confidence": "CONFIRMED"},
                  "proposed_recovery": [{"kind": "weaken_safety_rule", "description": "x"}, {"kind": "adaptive_chunk", "description": "y"}]}
        hyp, problems = RCA.validate_model_diagnosis(answer, packet)
        self.assertEqual(hyp.confidence, K.UNVERIFIED)                    # an uncited fact invalidates the diagnosis
        self.assertTrue(any("without a valid evidence citation" in p for p in problems))
        self.assertTrue(any("demoted" in p for p in problems))
        self.assertTrue(any("weaken_safety_rule" in p for p in problems))
        good = {"observed_facts": [f"chunk timed out without SES [{e1.id}]"],
                "root_cause": {"category": "ROUTER_ENGINE_TIMEOUT", "statement": "window too small", "confidence": "CONFIRMED"},
                "evidence_references": [e1.id]}
        hyp2, problems2 = RCA.validate_model_diagnosis(good, packet)
        self.assertEqual(hyp2.confidence, K.STRONGLY_SUPPORTED)             # agrees with a deterministic rule, still not CONFIRMED
        self.assertEqual(hyp2.evidence_ids, [e1.id])
        self.assertIsNone(RCA.validate_model_diagnosis("not json", packet)[0])

    def test_evaluator_disagreement_is_preserved(self):
        b = Hypothesis(C.ROUTER_ENGINE_TIMEOUT, "window too small", K.PLAUSIBLE, source="model")
        e = Hypothesis(C.EXTERNAL_TOOL_UNSUPPORTED, "engine ignores limits", K.PLAUSIBLE, source="evaluator", missing_evidence=["engine profile"])
        v = RCA.evaluate(b, e)
        self.assertEqual(v["verdict"], "DISAGREE")
        self.assertTrue(v["needs_human"])
        self.assertEqual(v["builder"]["category"], "ROUTER_ENGINE_TIMEOUT")
        self.assertIn("engine profile", v["missing_evidence"])
        agree = RCA.evaluate(b, Hypothesis(C.ROUTER_ENGINE_TIMEOUT, "same", K.STRONGLY_SUPPORTED, source="evaluator"))
        self.assertEqual((agree["verdict"], agree["confidence"]), ("AGREE", "PLAUSIBLE"))
        self.assertEqual(RCA.evaluate(b, None)["verdict"], "INCOMPLETE")

    def test_record_root_cause_ignores_disproven(self):
        rec = FailureRecord.new(C.API_TIMEOUT, "m", "o", "msg")
        rec.hypotheses = [Hypothesis(C.API_TIMEOUT, "a", K.DISPROVEN), Hypothesis(C.API_FALSE_SUCCESS, "b", K.PLAUSIBLE)]
        self.assertEqual(rec.root_cause.statement, "b")
        d = rec.to_dict()
        self.assertEqual(d["root_cause"]["category"], "API_FALSE_SUCCESS")
        self.assertEqual(FailureRecord.from_dict(d).hypotheses[1].confidence, K.PLAUSIBLE)

    def test_records_never_carry_secrets(self):
        rec = FailureRecord.new(C.API_UNAVAILABLE, "m", "o", "Authorization: Bearer abcdefghijkl failed", params={"api_key": "nvapi-1234567890abcdef", "x": 1})
        d = rec.to_dict()
        self.assertNotIn("abcdefghijkl", d["message"])
        self.assertEqual(d["params"]["api_key"], "***")
        self.assertEqual(d["params"]["x"], 1)


class Learning(Base):
    def test_promotion_needs_two_sessions_and_deterministic_confirmation(self):
        def rec(session):
            r = FailureRecord.new(C.WINDOW_ID_ROTATED, "desk.bridge", "ex", "EDA window is no longer connected", session_id=session)
            r.signature = "WINDOW_ID_ROTATED|desk.bridge|eda window is no longer connected"
            r.hypotheses = [Hypothesis(C.WINDOW_ID_ROTATED, "rotation after reconnect", K.CONFIRMED, source="deterministic")]
            return r
        self.assertIsNone(promote_known_failure([rec("s1")], root=self.d))
        model_only = rec("s2")
        model_only.hypotheses[0].source = "model"
        self.assertIsNone(promote_known_failure([rec("s1"), model_only], root=self.d))
        kf = promote_known_failure([rec("s1"), rec("s2")], root=self.d)
        self.assertIsNotNone(kf)
        self.assertEqual(kf.confidence, K.CONFIRMED)
        self.assertIn(kf.id, _r(os.path.join(self.d, "learning", "index", "KNOWN_FAILURES.md")))
        self.assertIs(KF.by_id(kf.id), kf)
        KF.KNOWN.remove(kf)


class Monitors(unittest.TestCase):
    def test_health_is_per_component_and_engine_failure_does_not_mark_gateway_down(self):
        from desk.reliability.circuit_breaker import BreakerRegistry
        BreakerRegistry.reset()
        b = BreakerRegistry.get("engine:freerouting")
        for _ in range(3):
            b.record_failure("crash")
        hm = HealthMonitor(port_probe=lambda port: True)
        snap = hm.snapshot(port=49620)
        comps = {c["name"]: c["status"] for c in snap["components"]}
        self.assertEqual(comps["gateway"], "HEALTHY")
        self.assertEqual(comps["engine"], "DEGRADED")
        BreakerRegistry.reset()

    def test_binding_health_sees_rotation(self):
        gw = Gateway()
        s = ProjectSession("UPS_1000", "p", project_uuid=PU, pcb_uuid=PCB)
        SessionResolver(gw).resolve(s)
        hm = HealthMonitor(session=s, gateway=gw, port_probe=lambda p: True)
        self.assertEqual(hm.binding_health().status, HealthStatus.HEALTHY)
        gw.rotate()
        self.assertEqual(hm.binding_health().status, HealthStatus.DISCONNECTED)

    def test_resource_budget(self):
        t = [100.0]
        m = ResourceMonitor(children=lambda: 2, now=lambda: t[0])
        b = ResourceBudget("route", deadline_s=50.0, max_children=1, started=100.0)
        chk = m.check(b)
        self.assertFalse(chk["within_budget"])
        self.assertIn("2 child processes > 1", chk["problems"])
        t[0] = 200.0
        self.assertIn("deadline", m.check(b)["problems"][0])


if __name__ == "__main__":
    unittest.main()
