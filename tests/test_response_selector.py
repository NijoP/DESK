"""B5: deterministic seven-response selector (desk/reliability/response_selector.py): table, ladder, termination."""
import random
import shutil
import tempfile
import unittest

from desk import tasks as T
from desk.reliability.models import ExecutionState as X, FailureCategory as C
from desk.reliability.response_selector import (RANK, TERMINAL, FailureContext as F, LadderState, Response as R,
                                                candidates, select, select_for_task)


class Table(unittest.TestCase):
    def first(self, ctx):
        return select(ctx, LadderState())

    def test_every_response_is_reachable_from_the_table(self):
        cases = {
            R.RETRY_SAME: F(C.TRANSIENT_NETWORK, "s", X.NOT_EXECUTED, layer="OPERATIONAL"),
            R.CHANGE_STRATEGY: F(C.ROUTER_STAGNATION, "s"),
            R.RECALCULATE: F(C.DRC_FAILURE, "s", root_cause_kinds=("calculated_value",)),
            R.ALTERNATIVE_PARTS: F(C.UNKNOWN_FAILURE, "s", root_cause_kinds=("component",)),
            R.RETURN_UPSTREAM: F(C.ROUTER_NO_LEGAL_ESCAPE, "s", root_cause_kinds=("upstream",)),
            R.REQUEST_CLARIFICATION: F(C.REQUIREMENT_CONFLICT, "s"),
            R.REQUEST_APPROVAL: F(C.ROUTER_RULE_CONFLICT, "s", approval_class=True),
        }
        for want, ctx in cases.items():
            self.assertEqual(self.first(ctx), want, ctx)

    def test_table_per_category(self):
        for cat in C:
            r = self.first(F(cat, "s"))
            if cat == C.REQUIREMENT_CONFLICT:
                self.assertEqual(r, R.REQUEST_CLARIFICATION)
            elif cat in (C.ROUTER_STAGNATION, C.ROUTER_ENGINE_TIMEOUT, C.ROUTER_SES_MISSING):
                self.assertEqual(r, R.CHANGE_STRATEGY)
            elif cat in (C.DRC_FAILURE, C.ERC_FAILURE, C.CONNECTIVITY_VERIFICATION_FAILURE, C.UNKNOWN_FAILURE,
                         C.PARTIAL_MUTATION, C.UNKNOWN_MUTATION_OUTCOME):
                self.assertEqual(r, R.REQUEST_APPROVAL)        # no established cause: never guess a fix
            self.assertIn(r, list(R))

    def test_no_retry_for_unknown_or_partial_outcomes(self):
        for st in (X.UNKNOWN, X.PARTIAL, X.EXECUTED_RESPONSE_LOST, X.FALSE_SUCCESS):
            self.assertNotEqual(self.first(F(C.API_TIMEOUT, "s", st, layer="OPERATIONAL")), R.RETRY_SAME)
        self.assertNotEqual(self.first(F(C.TRANSIENT_NETWORK, "s", X.NOT_EXECUTED, layer="ENGINEERING")), R.RETRY_SAME)

    def test_same_signature_twice_escalates(self):
        s = LadderState()
        ctx = F(C.TRANSIENT_NETWORK, "same", X.NOT_EXECUTED, layer="OPERATIONAL")
        r1 = select(ctx, s)
        s.record(r1, ctx.signature)
        self.assertEqual(r1, R.RETRY_SAME)
        self.assertEqual(select(ctx, s), R.REQUEST_APPROVAL)
        s2 = LadderState()
        s2.record(R.RECALCULATE, "req")
        self.assertEqual(select(F(C.REQUIREMENT_CONFLICT, "req"), s2), R.REQUEST_CLARIFICATION)

    def test_ladder_is_monotone_and_hops_are_capped(self):
        s = LadderState(max_executions=5)
        s.record(R.RECALCULATE, "a")
        self.assertEqual(select(F(C.TRANSIENT_NETWORK, "b", X.NOT_EXECUTED, layer="OPERATIONAL"), s), R.REQUEST_APPROVAL)
        s = LadderState(max_executions=5)
        up = lambda sig: F(C.ROUTER_NO_LEGAL_ESCAPE, sig, root_cause_kinds=("upstream",))
        for sig in ("h1", "h2"):
            r = select(up(sig), s)
            self.assertEqual(r, R.RETURN_UPSTREAM)
            s.record(r, sig)
        self.assertEqual(select(up("h3"), s), R.REQUEST_APPROVAL)

    def test_model_ranking_only_reorders_allowed_candidates(self):
        ctx = F(C.DRC_FAILURE, "s", root_cause_kinds=("calculated_value", "upstream"))
        self.assertEqual(candidates(ctx, LadderState()), [R.RECALCULATE, R.RETURN_UPSTREAM])
        self.assertEqual(select(ctx, LadderState(), ranking=["RETURN_UPSTREAM"]), R.RETURN_UPSTREAM)
        self.assertEqual(select(ctx, LadderState(), ranking=["RETRY_SAME", "weaken_safety_rule"]), R.RECALCULATE)
        self.assertEqual(select(F(C.ROUTER_RULE_CONFLICT, "s", approval_class=True), LadderState(),
                                ranking=["CHANGE_STRATEGY"]), R.REQUEST_APPROVAL)


class Termination(unittest.TestCase):
    def test_any_failure_sequence_terminates_at_6_or_7(self):
        rng = random.Random(20261121)
        cats, states = list(C), list(X)
        kinds = ["calculated_value", "component", "upstream", "requirement"]
        for max_exec in (1, 2, 3):
            bound = max_exec + 1
            for _ in range(3000):
                s = LadderState(max_executions=max_exec)
                executed, steps = [], 0
                while True:
                    ctx = F(rng.choice(cats), f"sig{rng.randrange(4)}", rng.choice(states),
                            layer=rng.choice(["OPERATIONAL", "ENGINEERING"]), idempotent=rng.random() < 0.5,
                            root_cause_kinds=tuple(k for k in kinds if rng.random() < 0.2), approval_class=rng.random() < 0.1)
                    prev_rank = s.rank
                    r = select(ctx, s, ranking=[x.value for x in rng.sample(list(R), 3)])
                    self.assertGreaterEqual(RANK[r], prev_rank)                       # monotone
                    s.record(r, ctx.signature)
                    steps += 1
                    if r in TERMINAL:
                        break
                    self.assertNotIn((r, ctx.signature), executed)                   # never twice per signature
                    executed.append((r, ctx.signature))
                    self.assertLessEqual(steps, bound)
                self.assertLessEqual(steps, bound)
                self.assertIn(s.terminal, (R.REQUEST_CLARIFICATION, R.REQUEST_APPROVAL))
                self.assertLessEqual(s.executions, max_exec)


class Persisted(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="desk_ladder_")
        self.store = T.TaskStore(self.d)
        self.tid = self.store.create("routing", "pcb", [{"kind": "artifact", "ref": "pcb"}],
                                     [{"kind": "gate", "ref": "routing:pcb", "acceptance": "connectivity FULL"}])["task_id"]

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_ladder_state_survives_reload_and_terminates(self):
        r1 = select_for_task(T.TaskStore(self.d), self.tid, F(C.ROUTER_STAGNATION, "e1"))
        r2 = select_for_task(T.TaskStore(self.d), self.tid, F(C.ROUTER_NO_LEGAL_ESCAPE, "e2", root_cause_kinds=("upstream",)))
        r3 = select_for_task(T.TaskStore(self.d), self.tid, F(C.ROUTER_STAGNATION, "e3"))
        self.assertEqual([r1["response"], r2["response"], r3["response"]], ["CHANGE_STRATEGY", "RETURN_UPSTREAM", "REQUEST_APPROVAL"])
        self.assertTrue(r3["terminal"])
        rec = T.validate(self.store.get(self.tid))
        self.assertEqual([e["response"] for e in rec["recovery"]], ["CHANGE_STRATEGY", "RETURN_UPSTREAM", "REQUEST_APPROVAL"])

    def test_clarification_blocks_the_task(self):
        select_for_task(self.store, self.tid, F(C.REQUIREMENT_CONFLICT, "r"))
        self.assertEqual(T.validate(self.store.get(self.tid))["execution_status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
