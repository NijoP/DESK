"""desk.simulation: optional ngspice plugin. Synthetic circuits only; recorded ngspice-42 output, so CI needs no
ngspice. The single live test runs real ngspice only when it is installed and skips otherwise."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from desk.simulation import base as B, models as M, netlist as N, verify as V, export as X  # noqa: E402
from desk.simulation import ngspice as NG  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "simulation")


def case(name):
    with open(os.path.join(FIX, name, "case.json"), encoding="utf-8") as f:
        c = json.load(f)
    circ = N.build_circuit(c["block"], c["sim"], M.ModelStore(models=c.get("models")))
    return c, circ


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def recorded(name, circ):
    d = os.path.join(FIX, name)
    raws = {}
    for a in circ.analyses:
        p = os.path.join(d, a["id"] + ".raw")
        raws[a["id"]] = _read(p) if os.path.exists(p) else None
    return NG.parse_run(circ, _read(os.path.join(d, "desk.log")), raws, returncode=0, engine_version="42")


def cats(res):
    return [d.category for d in res.diagnostics]


class OptionalDependency(unittest.TestCase):
    def test_package_imports_without_loading_the_engine_adapter(self):
        code = ("import sys; import desk.simulation, desk.simulation.netlist, desk.simulation.verify, "
                "desk.simulation.export, desk.simulation.models, desk.simulation.cli, desk.doctor; "
                "print('desk.simulation.ngspice' in sys.modules)")
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "False")

    def test_absent_engine_is_reported_not_raised(self):
        sim = NG.NgspiceSimulator(executable=os.path.join(tempfile.gettempdir(), "no-such-ngspice-xyz"))
        self.assertFalse(sim.probe().available)
        _, circ = case("divider")
        res = sim.run(circ)
        self.assertEqual(res.status, B.FAILED)
        self.assertEqual(cats(res), [B.ENGINE_NOT_FOUND])
        self.assertEqual(V.verify(res, [])["verdict"], V.NOT_RUN)

    def test_not_on_path_and_doctor_warns(self):
        from desk import doctor
        with mock.patch.dict(os.environ, {"DESK_NGSPICE": ""}), mock.patch("shutil.which", return_value=None):
            exe, why = NG.NgspiceSimulator().executable()
            self.assertIsNone(exe)
            self.assertIn("optional", why)
            chk = doctor.check_ngspice()
        self.assertEqual(chk.status, doctor.WARN)
        self.assertIn("optional", chk.name)

    def test_registry(self):
        self.assertIn("ngspice", B.names())
        with self.assertRaises(SystemExit):
            B.get("no-such-engine")
        B.register("fake_unit", lambda: NG.NgspiceSimulator(executable="/nonexistent"))
        try:
            self.assertIn("fake_unit", [e.name for e in B.engines()])
        finally:
            B._REGISTRY.pop("fake_unit", None)


class Netlist(unittest.TestCase):
    def test_divider_elements_exclusions_and_ground(self):
        _, c = case("divider")
        self.assertEqual(c.elements, ["R1 vin vout 10000", "R2 vout 0 10000", "VIN vin 0 DC 10"])
        self.assertEqual(c.excluded, [{"ref": "J1", "reason": "input pad, no electrical model"}])
        self.assertEqual(c.node_map["GND"], "0")
        c.require_complete()

    def test_rendered_deck_matches_recorded_fixture(self):
        for name in ("divider", "rc_step", "buck", "measure_fail", "nonconv", "model_error"):
            _, c = case(name)
            self.assertEqual(NG.render_deck(c), _read(os.path.join(FIX, name, "desk.cir")), name)

    def test_buck_binds_transistor_and_diode_by_explicit_terminals(self):
        _, c = case("buck")
        self.assertIn("MQ1 vin g sw sw NSW", c.elements)
        self.assertIn("D1 0 sw DSCH", c.elements)
        self.assertEqual({m["name"]: m["status"] for m in c.models}, {"NSW": M.UNVERIFIED, "DSCH": M.UNVERIFIED})

    def test_unsupported_parts_are_reported_never_dropped(self):
        block = {"parts": [
            {"ref": "R1", "value": "4k7", "pins": {"1": "A", "2": "GND"}},
            {"ref": "U1", "mpn": "SOME-IC", "pins": {"1": "A", "2": "GND"}},
            {"ref": "D1", "pins": {"1": "A", "2": "GND"}},
            {"ref": "LED1", "pins": {"1": "A", "2": "GND"}},
            {"ref": "C1", "value": "n/a", "pins": {"1": "A", "2": "GND"}},
            {"ref": "Q1", "pins": {"1": "A", "2": "GND", "3": "B"}}]}
        spec = {"parts": {"D1": {"element": "D", "model": "DX"}, "Q1": {"element": "M", "model": "NOPE"}},
                "models": {"DX": {"kind": "D", "card": ".model DX D(IS=1e-14)"}},
                "sources": [{"name": "V1", "pos": "A", "dc": 1}], "analyses": [{"type": "op"}]}
        c = N.build_circuit(block, spec)
        self.assertIn("R1 a 0 4700", c.elements)
        reasons = {u["ref"]: u["reason"] for u in c.unsupported}
        self.assertEqual(set(reasons), {"U1", "D1", "LED1", "C1", "Q1"})
        self.assertIn("never guessed", reasons["D1"])
        self.assertIn("not in the model store", reasons["Q1"])
        with self.assertRaises(N.NetlistError):
            c.require_complete()

    def test_bad_specs_are_refused(self):
        r = {"parts": [{"ref": "R1", "value": "1k", "pins": {"1": "VOUT", "2": "GND"}},
                       {"ref": "R2", "value": "1k", "pins": {"1": "Vout", "2": "GND"}}]}
        with self.assertRaises(N.NetlistError):        # SPICE folds case: two nets would merge silently
            N.build_circuit(r, {"analyses": [{"type": "op"}]})
        floating = {"parts": [{"ref": "R1", "value": "1k", "pins": {"1": "A", "2": "B"}}]}
        with self.assertRaises(N.NetlistError):
            N.build_circuit(floating, {"analyses": [{"type": "op"}]})
        ok = {"parts": [{"ref": "R1", "value": "1k", "pins": {"1": "A", "2": "GND"}}]}
        for spec in ({"analyses": [{"type": "tran", "step": 1, "stop": 2}],
                      "measures": [{"name": "x", "analysis": "tran", "expr": "AVG v(a)\nshell rm -rf /"}]},
                     {"analyses": [{"type": "tran", "step": 1, "stop": 2}],
                      "measures": [{"name": "x", "analysis": "tran", "expr": "AVG v({NOPE})"}]},
                     {"analyses": [{"type": "noise"}]},
                     {"analyses": [{"type": "tran", "step": 2, "stop": 1}]},
                     {"analyses": [{"type": "tran", "stop": 1}]},
                     {"sources": [{"name": "V1", "pos": "A", "dc": "nan"}], "analyses": [{"type": "op"}]}):
            with self.assertRaises(N.NetlistError, msg=json.dumps(spec)):
                N.build_circuit(ok, spec)


class ModelStoreTests(unittest.TestCase):
    def test_provenance_and_card_safety(self):
        s = M.ModelStore(models={
            "DSHEET": {"kind": "D", "card": ".model DSHEET D(IS=2e-9)", "mpn": "X",
                       "source": {"type": "datasheet", "reference": "Example diode datasheet rev A p.3"}},
            "DGEN": {"kind": "D", "card": ".model DGEN D(IS=1e-14)", "source": {"type": "generic", "reference": "x"}},
            "DNOREF": {"kind": "D", "card": ".model DNOREF D", "source": {"type": "datasheet", "reference": ""}}})
        self.assertEqual({r["name"]: r["status"] for r in s.rows()},
                         {"DSHEET": M.TRACEABLE, "DGEN": M.UNVERIFIED, "DNOREF": M.UNVERIFIED})
        s.add_inline("DIN", "D", ".model DIN D", "test")
        self.assertEqual(s.get("din")["status"], M.UNVERIFIED)
        for name, kind, card in (("DA", "D", ".model DA D\n.control\nshell echo pwned\n.endc"),
                                 ("DB", "D", ".include /etc/passwd"), ("DC", "D", ".model OTHER D"),
                                 ("XS", "SUBCKT", ".subckt XS a b\nR1 a b 1"), ("DD", "TRIODE", ".model DD D")):
            with self.assertRaises(M.ModelError, msg=name):
                M.validate_card(name, kind, card)

    def test_store_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "models.json")
            s = M.ModelStore(p)
            s.add("DSHEET", {"kind": "D", "card": ".model DSHEET D(IS=2e-9)",
                             "source": {"type": "vendor_model", "reference": "vendor library v1"}})
            s.save()
            self.assertEqual(M.ModelStore(p).get("DSHEET")["status"], M.TRACEABLE)
            self.assertNotIn("status", json.loads(_read(p))["models"]["DSHEET"])


class RecordedResults(unittest.TestCase):
    def test_divider_op(self):
        c, circ = case("divider")
        res = recorded("divider", circ)
        self.assertEqual(res.status, B.COMPLETED, res.diagnostics)
        self.assertAlmostEqual(res.analyses["op1"].vectors["v(vout)"][0], 5.0, places=6)
        rep = V.verify(res, c["expect"], circ.node_map)
        self.assertEqual(rep["verdict"], V.PASS_WITH_CAVEATS)     # J1 was excluded: a caveat, not a silent pass
        self.assertTrue(any("J1" in x for x in rep["caveats"]))

    def test_divider_against_block_qa_calculation(self):
        c, circ = case("divider")
        res = recorded("divider", circ)
        exps = V.expectations_from_qa(c["block"])
        self.assertEqual(exps[0]["calc_value"], 5.0)
        self.assertIn("calc: 10*R2/(R1+R2)", exps[0]["source"])
        self.assertEqual(V.verify(res, exps, circ.node_map)["checks"][0]["status"], V.PASS)
        res.analyses["op1"].vectors["v(vout)"] = [5.08]              # in range but 1.6 % off the calculation
        chk = V.verify(res, exps, circ.node_map)["checks"][0]
        self.assertEqual(chk["status"], V.FAIL)
        self.assertIn("exceeds tolerance", chk["detail"])

    def test_rc_step_tran_and_ac(self):
        c, circ = case("rc_step")
        res = recorded("rc_step", circ)
        self.assertEqual(res.status, B.COMPLETED, res.diagnostics)
        self.assertAlmostEqual(res.measurements["t_tau"].value, 1e-3, delta=2e-5)
        self.assertAlmostEqual(res.measurements["f3db"].value, 159.15, delta=0.5)
        tran, ac = res.analyses["tran1"], res.analyses["ac1"]
        self.assertEqual((tran.scale, tran.points), ("time", 101))
        self.assertEqual(ac.scale, "frequency")
        self.assertIsInstance(ac.vectors["v(vout)"][0], complex)
        self.assertEqual(V.verify(res, c["expect"], circ.node_map)["verdict"], V.PASS)

    def test_buck_stage(self):
        c, circ = case("buck")
        res = recorded("buck", circ)
        self.assertEqual(res.status, B.COMPLETED, res.diagnostics)
        self.assertAlmostEqual(res.measurements["vout_avg"].value, 4.81, delta=0.05)
        rep = V.verify(res, c["expect"], circ.node_map)
        self.assertEqual(rep["verdict"], V.PASS_WITH_CAVEATS)      # generic models are UNVERIFIED
        self.assertTrue(any("NSW is UNVERIFIED" in x for x in rep["caveats"]))
        self.assertIn("not prove", rep["notice"])

    def test_convergence_failure_is_classified_even_with_exit_code_zero(self):
        _, circ = case("nonconv")
        res = recorded("nonconv", circ)
        self.assertEqual(res.status, B.FAILED)
        self.assertIn(B.CONVERGENCE, cats(res))
        self.assertEqual(res.analyses["tran1"].status, B.FAILED)
        self.assertEqual(V.verify(res, [{"quantity": "x", "max": 1, "source": "s"}])["verdict"], V.NOT_RUN)

    def test_model_error(self):
        _, circ = case("model_error")
        res = recorded("model_error", circ)
        self.assertEqual(cats(res), [B.MODEL_ERROR])
        self.assertIn("dbad", res.diagnostics[0].message)

    def test_failed_measure_fails_verification(self):
        c, circ = case("measure_fail")
        res = recorded("measure_fail", circ)
        self.assertEqual(cats(res), [B.MEASURE_FAILED])
        self.assertFalse(res.measurements["t_cross"].ok)
        rep = V.verify(res, c["expect"], circ.node_map)
        self.assertEqual(rep["verdict"], V.FAIL)
        self.assertIn("MISSING", rep["checks"][0]["detail"])
        self.assertEqual(V.verify(res, [])["verdict"], V.FAIL)

    def test_ignored_netlist_line_and_unexplained_exit_are_errors(self):
        _, circ = case("divider")
        raw = _read(os.path.join(FIX, "divider", "op1.raw"))
        log = ("Circuit: * x\nWarning: 'r1 in 1k' is not a valid resistor instance line, ignored!\n"
               "DESK_BEGIN op1\nDESK_END op1\nDESK_DONE\n")
        self.assertIn(B.NETLIST_ERROR, cats(NG.parse_run(circ, log, {"op1": raw})))
        titled = "Circuit: * desk syntax error demo\nDESK_BEGIN op1\nDESK_END op1\nDESK_DONE\n"
        self.assertEqual(cats(NG.parse_run(circ, titled, {"op1": raw})), [])
        ok_log = "DESK_BEGIN op1\nDESK_END op1\nDESK_DONE\n"
        self.assertEqual(cats(NG.parse_run(circ, ok_log, {"op1": raw}, returncode=3)), [B.ENGINE_CRASH])
        self.assertEqual(cats(NG.parse_run(circ, "DESK_BEGIN op1\n", {"op1": raw})), [B.ENGINE_CRASH])
        sing = ("DESK_BEGIN op1\nWarning: singular matrix:  check node b\nNote: Transient op finished successfully\n"
                "DESK_END op1\nDESK_DONE\n")
        res = NG.parse_run(circ, sing, {"op1": raw})
        self.assertEqual(res.status, B.COMPLETED)
        self.assertEqual(cats(res), [B.CONVERGENCE_ASSISTED])
        self.assertEqual(V.verify(res, [{"quantity": "op1:v(vout)", "min": 4, "max": 6, "source": "s"}])["verdict"],
                         V.PASS_WITH_CAVEATS)

    def test_stale_plot_is_not_accepted_as_this_analysis(self):
        _, circ = case("rc_step")
        tran = _read(os.path.join(FIX, "rc_step", "tran1.raw"))
        res = NG.parse_run(circ, _read(os.path.join(FIX, "rc_step", "desk.log")), {"tran1": tran, "ac1": tran})
        self.assertIn(B.NO_OUTPUT, cats(res))
        self.assertEqual(res.analyses["ac1"].status, B.FAILED)


class Export(unittest.TestCase):
    def test_csv_and_json(self):
        _, circ = case("rc_step")
        res = recorded("rc_step", circ)
        tran = X.analysis_csv(res.analyses["tran1"]).splitlines()
        self.assertTrue(tran[0].startswith("# Simulation alone does not prove"))
        self.assertEqual(tran[1], "time,v(vin),v(vout)")
        self.assertEqual(len(tran), 2 + 101)
        ac = X.analysis_csv(res.analyses["ac1"]).splitlines()
        self.assertIn("v(vout).mag", ac[1])
        self.assertIn("v(vout).phase_deg", ac[1])
        with tempfile.TemporaryDirectory() as d:
            paths = X.write_exports(res, d)
            self.assertEqual(sorted(os.path.basename(p) for p in paths), ["ac1.csv", "result.json", "tran1.csv"])
            doc = json.loads(_read(os.path.join(d, "result.json")))
            self.assertIn("not prove", doc["notice"])
            self.assertEqual(len(doc["analyses"]["ac1"]["vectors"]["v(vout)"][0]), 2)


class AdapterProcess(unittest.TestCase):
    """The subprocess path with ngspice faked: files are copied from the recorded fixture into the run dir."""

    def _fake_run(self, name):
        def run(cmd, cwd=None, **kw):
            self.assertEqual(cmd[1:4], ["-b", "-n", "-o"])
            self.assertIs(kw.get("stdin"), subprocess.DEVNULL)
            for f in os.listdir(os.path.join(FIX, name)):
                if f == "desk.log" or f.endswith(".raw"):
                    shutil.copy(os.path.join(FIX, name, f), os.path.join(cwd, f))
            return subprocess.CompletedProcess(cmd, 0)
        return run

    def _sim(self):
        sim = NG.NgspiceSimulator(executable="ngspice-fake")
        sim.probe = lambda: B.EngineInfo("ngspice", True, "42", "/fake/ngspice", "test")
        return sim

    def test_full_run_path(self):
        c, circ = case("rc_step")
        with mock.patch.object(NG.subprocess, "run", side_effect=self._fake_run("rc_step")):
            with tempfile.TemporaryDirectory() as d:
                res = self._sim().run(circ, work_dir=d)
                self.assertEqual(_read(os.path.join(d, "desk.cir")), _read(os.path.join(FIX, "rc_step", "desk.cir")))
        self.assertEqual(res.status, B.COMPLETED, res.diagnostics)
        self.assertEqual(V.verify(res, c["expect"], circ.node_map)["verdict"], V.PASS)

    def test_timeout_kills_and_classifies(self):
        _, circ = case("rc_step")
        with mock.patch.object(NG.subprocess, "run", side_effect=subprocess.TimeoutExpired("ngspice", 1)):
            res = self._sim().run(circ, timeout_s=1)
        self.assertEqual(res.status, B.FAILED)
        self.assertEqual(res.diagnostics[0].category, B.TIMEOUT)
        self.assertNotIn(B.ENGINE_CRASH, cats(res))

    def test_oversize_result_is_refused(self):
        _, circ = case("rc_step")
        with mock.patch.dict(os.environ, {"DESK_SIM_MAX_OUTPUT_MB": "0.001"}), \
                mock.patch.object(NG.subprocess, "run", side_effect=self._fake_run("rc_step")):
            res = self._sim().run(circ)
        self.assertEqual(res.status, B.FAILED)
        self.assertIn(B.OUTPUT_TOO_LARGE, cats(res))

    def test_incomplete_circuit_never_reaches_the_engine(self):
        c = N.build_circuit({"parts": [{"ref": "U1", "pins": {"1": "A"}}]},
                            {"sources": [{"name": "V1", "pos": "A", "dc": 1}], "analyses": [{"type": "op"}]})
        with mock.patch.object(NG.subprocess, "run") as run:
            with self.assertRaises(N.NetlistError):
                self._sim().run(c)
        run.assert_not_called()


class Cli(unittest.TestCase):
    def _spec_file(self, d, name):
        c = json.loads(_read(os.path.join(FIX, name, "case.json")))
        spec = dict(c["sim"], block=c["block"], models=c.get("models") or {})
        p, e = os.path.join(d, "sim.json"), os.path.join(d, "expect.json")
        with open(p, "w") as f:
            json.dump(spec, f)
        with open(e, "w") as f:
            json.dump(c.get("expect", []), f)
        return p, e

    def _main(self, argv):
        from desk.simulation.cli import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(argv)
        return rc, buf.getvalue()

    def test_netlist_and_models(self):
        with tempfile.TemporaryDirectory() as d:
            none = os.path.join(d, "none.json")
            p, _ = self._spec_file(d, "buck")
            rc, out = self._main(["netlist", p, "--models", none])
            self.assertEqual(rc, 0, out)
            self.assertIn("MQ1 vin g sw sw NSW", out)
            self.assertIn("model       NSW [UNVERIFIED]", out)
            c = json.loads(_read(p))
            c["block"]["parts"].append({"ref": "U9", "mpn": "SOME-IC", "pins": {"1": "VIN"}})
            with open(p, "w") as f:
                json.dump(c, f)
            rc, out = self._main(["netlist", p, "--models", none])
            self.assertEqual(rc, 1)
            self.assertIn("UNSUPPORTED U9", out)
            store = os.path.join(d, "store.json")
            with open(store, "w") as f:
                json.dump({"version": 1, "models": {"DG": {"kind": "D", "card": ".model DG D"}}}, f)
            rc, out = self._main(["models", "check", "--models", store])
            self.assertEqual(rc, 1)
            self.assertIn("1 UNVERIFIED", out)

    def test_run_with_fake_engine(self):
        class Fake(B.Simulator):
            name = "fake_rc"

            def probe(self):
                return B.EngineInfo("fake_rc", True, "0")

            def run(self, circuit, timeout_s=None, work_dir=None):
                return recorded("rc_step", circuit)

        B.register("fake_rc", Fake)
        try:
            with tempfile.TemporaryDirectory() as d:
                none = os.path.join(d, "none.json")
                p, e = self._spec_file(d, "rc_step")
                out_dir = os.path.join(d, "out")
                rc, out = self._main(["run", p, "--engine", "fake_rc", "--expect", e, "--out", out_dir, "--models", none])
                self.assertEqual(rc, 0, out)
                self.assertIn("SIMULATION VERIFICATION: PASS", out)
                self.assertIn("NOTE: Simulation alone does not prove", out)
                self.assertTrue(os.path.exists(os.path.join(out_dir, "tran1.csv")))
                self.assertEqual(json.loads(_read(os.path.join(out_dir, "result.json")))["verification"]["verdict"], "PASS")
                with open(e, "w") as f:
                    json.dump([{"quantity": "f3db", "min": 1000, "max": 2000, "source": "wrong on purpose"}], f)
                rc, out = self._main(["run", p, "--engine", "fake_rc", "--expect", e, "--models", none])
                self.assertEqual(rc, 1)
                self.assertIn("OUT OF RANGE", out)
        finally:
            B._REGISTRY.pop("fake_rc", None)

    def test_desk_py_dispatches_sim(self):
        import importlib.util
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        spec = importlib.util.spec_from_file_location("desk_tool_for_sim_test", os.path.join(ROOT, "tools", "desk.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with mock.patch("desk.simulation.cli.main", return_value=7) as m:
            self.assertEqual(mod.main(["sim", "engines"]), 7)
        m.assert_called_once_with(["engines"])


@unittest.skipUnless(NG.NgspiceSimulator().probe().available, "ngspice not installed (optional)")
class LiveNgspice(unittest.TestCase):
    def test_rc_step_runs_on_installed_ngspice(self):
        c, circ = case("rc_step")
        res = NG.NgspiceSimulator().run(circ, timeout_s=60)
        self.assertEqual(res.status, B.COMPLETED, res.diagnostics)
        self.assertEqual(V.verify(res, c["expect"], circ.node_map)["verdict"], V.PASS)


if __name__ == "__main__":
    unittest.main()
