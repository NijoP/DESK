"""Tool-calling agent loop + deterministic schematic tools (no network, no EasyEDA)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from desk.schematic_io import plan_net_wires, wiring_js, parse_pin_ref, pin_exit, find_pin
from desk.orchestrator import tools_manifest as tm
from desk.orchestrator.agent_loop import run_agent, SYSTEM_PROMPT

DUMP = {"parts": [
    {"ref": "U1", "uuid": "u1", "dev": "ESP32-S3", "x": 100, "y": 100, "rot": 0,
     "pins": [{"num": "1", "name": "3V3", "x": 90, "y": 110, "rot": 180, "net": "+3V3", "nc": False},
              {"num": "2", "name": "EN", "x": 90, "y": 120, "rot": 180, "net": None, "nc": False},
              {"num": "3", "name": "IO0", "x": 110, "y": 110, "rot": 0, "net": None, "nc": False},
              {"num": "4", "name": "NC", "x": 110, "y": 120, "rot": 0, "net": None, "nc": True}]},
    {"ref": "C1", "uuid": "c1", "dev": "100nF", "x": 200, "y": 100, "rot": 0,
     "pins": [{"num": "1", "name": "1", "x": 200, "y": 90, "rot": 270, "net": None, "nc": False},
              {"num": "2", "name": "2", "x": 200, "y": 110, "rot": 90, "net": "GND", "nc": False}]}]}


class PlanTests(unittest.TestCase):
    def test_parse_pin_ref(self):
        self.assertEqual(parse_pin_ref("U1.3"), ("U1", "3"))
        self.assertEqual(parse_pin_ref(" C2-1 "), ("C2", "1"))
        with self.assertRaises(ValueError):
            parse_pin_ref("U1")

    def test_pin_exit_follows_rotation(self):
        self.assertEqual(pin_exit(100, 50, 0, 40), (140, 50, 0))
        self.assertEqual(pin_exit(100, 50, 180, 40), (60, 50, 0))
        self.assertEqual(pin_exit(100, 50, 270, 40), (100, 40, 90))
        self.assertEqual(pin_exit(100, 50, 90, 40), (100, 60, 90))

    def test_find_pin_by_number_or_name(self):
        self.assertEqual(find_pin(DUMP, "U1", "EN")["num"], "2")
        self.assertIsNone(find_pin(DUMP, "U9", "1"))

    def test_plan_resolves_coordinates_and_refuses_bad_pins(self):
        plan = plan_net_wires(DUMP, "EN", ["U1.2", "C1.1", "U1.4", "U1.1", "U1.99", "R7.1"])
        self.assertFalse(plan["ok"])
        self.assertEqual([w["pin"] for w in plan["wires"]], ["U1.2", "C1.1"])
        self.assertEqual(plan["wires"][0]["from"], [90, 120])
        self.assertEqual(plan["wires"][0]["to"], [50, 120])          # rot 180, stub 40 -> left
        self.assertEqual(plan["wires"][1]["to"], [200, 60])          # rot 270, stub 60 -> up by 30
        joined = " | ".join(plan["errors"])
        self.assertIn("U1.4: marked no-connect", joined)
        self.assertIn("already on net +3V3", joined)
        self.assertIn("no such pin", joined)
        self.assertIn("component not on sheet", joined)

    def test_plan_skips_pins_already_on_net(self):
        plan = plan_net_wires(DUMP, "GND", ["C1.2", "U1.3"])
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["skipped"], ["C1.2 already on GND"])
        self.assertEqual(len(plan["wires"]), 1)

    def test_bad_net_name(self):
        with self.assertRaises(ValueError):
            plan_net_wires(DUMP, "bad net!", ["U1.2"])

    def test_wiring_js_uses_verified_api(self):
        plan = plan_net_wires(DUMP, "EN", ["U1.2", "C1.1"])
        js = wiring_js(plan)
        self.assertEqual(js.count("eda.sch_PrimitiveWire.create("), 2)
        self.assertEqual(js.count("eda.sch_PrimitiveAttribute.createNetLabel("), 2)
        self.assertIn('[90,120,50,120],"EN"', js)
        self.assertIn("return {wired:2}", js)


class ManifestTests(unittest.TestCase):
    def test_mutation_tools_hidden_unless_allowed(self):
        names = {t["function"]["name"] for t in tm.tool_schemas(False)}
        self.assertIn("read_schematic", names)
        self.assertNotIn("wire_net", names)
        self.assertIn("wire_net", {t["function"]["name"] for t in tm.tool_schemas(True)})
        for t in tm.TOOLS:
            self.assertEqual(t["type"], "function")
            self.assertEqual(t["function"]["parameters"]["type"], "object")

    def test_dispatch_unknown_and_bad_json(self):
        self.assertIn("unknown tool", tm.dispatch("nope", "{}", {})["error"])
        self.assertIn("not valid JSON", tm.dispatch("read_pcb", "{", {})["error"])

    def test_wire_net_refused_without_mutation(self):
        r = tm.dispatch("wire_net", {"project": "p", "net": "EN", "pins": ["U1.2"]}, {"allow_mutation": False})
        self.assertIn("mutation not allowed", r["error"])

    def test_list_nets_from_saved_dump_without_bridge(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "state"))
            with open(os.path.join(d, "state", "sch_dump.json"), "w", encoding="utf-8") as f:
                json.dump(DUMP, f)
            r = tm.dispatch("list_schematic_nets", {"project": d}, {})
            self.assertEqual(r["nets"]["GND"], ["C1.2"])
            self.assertEqual(r["unconnected_pins"], ["U1.2", "U1.3", "C1.1"])

    def test_handler_exceptions_become_errors(self):
        def boom(a, c):
            raise SystemExit("bridge down")
        with mock.patch.dict(tm.HANDLERS, {"boom": boom}):
            self.assertEqual(tm.dispatch("boom", {}, {})["error"], "SystemExit: bridge down")


class FakeAdapter:
    """Scripted provider: returns tool calls then a final answer, records requests."""
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def chat_completion(self, messages, **kw):
        self.requests.append({"messages": list(messages), **kw})
        return self.script.pop(0)


def _call(name, args, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class LoopTests(unittest.TestCase):
    def test_loop_executes_tools_then_finishes(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "state"))
            with open(os.path.join(d, "state", "sch_dump.json"), "w", encoding="utf-8") as f:
                json.dump(DUMP, f)
            fake = FakeAdapter([
                {"message": {"content": "", "tool_calls": [_call("list_schematic_nets", {"project": d})]}, "usage": {"total_tokens": 10}},
                {"message": {"content": "", "tool_calls": [_call("wire_net", {"project": d, "net": "EN", "pins": ["U1.2"]}, "c2")]}, "usage": {"total_tokens": 20}},
                {"message": {"content": '{"nets_wired": [], "refused": ["mutation not allowed"]}'}, "usage": {"total_tokens": 5}},
            ])
            run = run_agent("wire EN", project=d, adapter=fake, model="nvidia/nemotron-3-ultra-550b-a55b")
            self.assertEqual(run.stopped_reason, "final")
            self.assertEqual(run.tool_calls, 2)
            self.assertEqual(run.turns, 3)
            self.assertEqual(run.usage["total_tokens"], 35)
            self.assertEqual(run.final_json["refused"], ["mutation not allowed"])
            for r in fake.requests:
                self.assertEqual(r["thinking"], "off")
                self.assertNotIn("wire_net", [t["function"]["name"] for t in r["tools"]])
            msgs = fake.requests[2]["messages"]
            self.assertEqual(msgs[0]["role"], "system")
            self.assertIn("SUPPORTS READS", msgs[0]["content"])
            tool_msgs = [m for m in msgs if m["role"] == "tool"]
            self.assertEqual([m["tool_call_id"] for m in tool_msgs], ["c1", "c2"])
            self.assertIn("mutation not allowed", tool_msgs[1]["content"])
            self.assertIn('"GND": ["C1.2"]', tool_msgs[0]["content"])
            with open(run.trace_path, encoding="utf-8") as f:
                lines = [json.loads(l) for l in f]
            self.assertEqual(lines[-1]["run"]["stopped_reason"], "final")

    def test_provider_error_stops_loop(self):
        fake = FakeAdapter([{"error": "HTTP 401: bad key"}])
        run = run_agent("x", project=None, adapter=fake)
        self.assertTrue(run.stopped_reason.startswith("provider_error"))
        self.assertEqual(run.tool_calls, 0)

    def test_max_turns_bound(self):
        fake = FakeAdapter([{"message": {"content": "", "tool_calls": [_call("doctor", {})]}}] * 3)
        with mock.patch.dict(tm.HANDLERS, {"doctor": lambda a, c: {"checks": []}}):
            run = run_agent("x", project=None, adapter=fake, max_turns=2)
        self.assertEqual(run.stopped_reason, "max_turns")
        self.assertEqual(run.tool_calls, 2)

    def test_trace_redacts_keys(self):
        fake = FakeAdapter([{"message": {"content": "key nvapi-abcdef123456 leaked"}}])
        with tempfile.TemporaryDirectory() as d:
            run = run_agent("x", project=d, adapter=fake)
            with open(run.trace_path, encoding="utf-8") as f:
                txt = f.read()
        self.assertNotIn("nvapi-abcdef123456", txt)
        self.assertIn("[REDACTED]", txt)

    def test_system_prompt_forbids_browser_and_js(self):
        self.assertIn("Browser automation", SYSTEM_PROMPT)
        self.assertIn("never write EasyEDA JavaScript", SYSTEM_PROMPT)


class HttpAdapterBodyTests(unittest.TestCase):
    def test_chat_completion_body_has_tools_and_thinking_off(self):
        from desk.orchestrator import http_adapter as ha
        captured = {}

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "", "tool_calls": [_call("read_schematic", {"project": "p"})]},
                                                "finish_reason": "tool_calls"}], "usage": {"total_tokens": 3}}).encode()

        def fake_open(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            captured["timeout"] = timeout
            return R()

        ad = ha.OpenAICompatAdapter("nvidia", api_key="nvapi-test")
        with mock.patch.object(ha.urllib.request, "urlopen", fake_open):
            out = ad.chat_completion([{"role": "user", "content": "hi"}], tools=tm.tool_schemas(), thinking="off", timeout=33)
        b = captured["body"]
        self.assertEqual(b["model"], "nvidia/nemotron-3-ultra-550b-a55b")
        self.assertEqual(b["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(b["reasoning_effort"], "none")
        self.assertEqual(b["tool_choice"], "auto")
        self.assertEqual(len(b["tools"]), len(tm.tool_schemas()))
        self.assertEqual(out["finish_reason"], "tool_calls")
        self.assertEqual(out["message"]["tool_calls"][0]["function"]["name"], "read_schematic")
        self.assertEqual(captured["timeout"], 33)


if __name__ == "__main__":
    unittest.main()
