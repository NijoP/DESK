"""The DESK node service over HTTP, the Weft runtime adapter with a fake `weft`, and the workflows themselves.

The workflow compile test runs the real Weft compiler when one is available (a Weft install, or the compiler
harness named by DESK_WEFT_VALIDATOR + DESK_WEFT_CHECKOUT) and is skipped otherwise.
"""
import io
import json
import os
import re
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout

from desk.weft import cli, contracts as C, runtime as rt, service, staging

REQ = json.dumps({"text": "12 V input, 5 V 3 A synchronous buck converter module, 500 kHz switching",
                  "voltage_rails": {"VIN": 12.0, "VOUT": 5.0}, "current_limits_A": {"VIN": 1.5, "VOUT": 3.0}})


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="desk_weft_svc_")
        os.makedirs(os.path.join(cls.root, "DEMO"))
        cls.server = service.make_server("secret-token", port=0, projects_root=cls.root)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        service.serve_in_thread(cls.server)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def request(self, method, path, body=None, token="secret-token", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        req = urllib.request.Request(self.url + path, data=data, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def node(self, node_id, **inputs):
        return self.request("POST", "/v1/nodes/" + node_id, dict(projectId="DEMO", runId="run-http", **inputs))

    def test_health_needs_no_token_and_tells_no_secret(self):
        status, doc = self.request("GET", "/health", token=None)
        self.assertEqual(status, 200)
        self.assertEqual(doc["weftPin"], staging.pin()["commit"])
        self.assertNotIn("secret-token", json.dumps(doc))

    def test_calls_without_the_token_are_refused(self):
        for token in (None, "wrong"):
            self.assertEqual(self.request("GET", "/v1/nodes", token=token)[0], 401)
            status, e = self.request("POST", "/v1/nodes/DeskRequirementIntake", {"projectId": "DEMO", "runId": "r", "requirements": "x"}, token=token)
            self.assertEqual((status, e["error"]["code"]), (401, "UNAUTHORIZED"))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "DEMO", "state")))

    def test_service_does_not_start_without_a_token(self):
        with self.assertRaises(ValueError):
            service.make_server("", port=0)

    def test_contract_listing(self):
        status, doc = self.request("GET", "/v1/nodes")
        self.assertEqual(status, 200)
        self.assertEqual(len(doc["nodes"]), len(C.CONTRACTS))

    def test_bad_bodies(self):
        self.assertEqual(self.request("POST", "/v1/nodes/DeskRequirementIntake", raw=b"not json")[1]["error"]["code"], "INVALID_INPUT")
        big = json.dumps({"projectId": "DEMO", "runId": "r", "requirements": "x" * (service.MAX_BODY + 10)}).encode("utf-8")
        self.assertEqual(self.request("POST", "/v1/nodes/DeskRequirementIntake", raw=big)[0], 400)
        self.assertEqual(self.request("POST", "/v1/other", {})[0], 404)

    def test_error_status_never_carries_outputs(self):
        status, e = self.node("DeskRoutingExecutor")
        self.assertEqual(status, 501)
        self.assertNotIn("outputs", e)

    def test_requirement_to_release_end_to_end_over_http(self):
        """The calls hardware_design.weft makes for the stages DESK backs today, in graph order."""
        status, intake = self.node("DeskRequirementIntake", requirements=REQ)
        self.assertEqual(status, 200)
        h = intake["outputs"]["requirementsHash"]
        self.assertTrue(self.node("DeskRequirementValidator", requirementsHash=h)[1]["passed"])
        cls = self.node("DeskDomainClassifier", requirementsHash=h)[1]
        self.assertEqual(cls["outputs"]["primaryArchetype"], "buck_converter")
        ph = self.node("DeskDesignProfileCompiler", requirementsHash=h)[1]["outputs"]["profileHash"]
        self.assertTrue(self.node("DeskComponentFamilyResolver", profileHash=ph)[1]["passed"])
        self.assertTrue(self.node("DeskPowerDistributionAnalyzer", profileHash=ph)[1]["passed"])
        self.assertEqual(self.node("DeskBOMGenerator")[0], 501)                      # the graph stops here today
        from desk.weft.store import RecordStore
        RecordStore("DEMO", self.root).put_evidence("board", {"profile_hash": ph, "board_revision": "r1", "evidence_revision": "r1", "drc_violations": [],
                                                               "unconnected_nets": [], "critical_nets": [], "routability_score": 1.0, "discontinuities_count": 0})
        self.assertTrue(self.node("DeskQualityGate", profileHash=ph, evidenceRef="board")[1]["outputs"]["approved"])
        self.assertEqual(self.node("DeskReleaseGate", profileHash=ph, evidenceRef="board", approvalRef="manufacturing-x")[0], 403)
        ref = self.node("DeskApprovalRecorder", stage="manufacturing", decision="approved", subjectHash=ph)[1]["outputs"]["approvalRef"]
        self.assertTrue(self.node("DeskReleaseGate", profileHash=ph, evidenceRef="board", approvalRef=ref)[1]["outputs"]["releaseAllowed"])
        self.assertEqual(self.node("DeskReleaseGenerator")[0], 501)


class FakeWeft:
    """Stands in for the `weft` command line. Records every argv it is given."""

    def __init__(self, installed="native", commit=None, wait_exit=0, run_id="0193aaaa-run"):
        self.installed, self.commit, self.wait_exit, self.run_id = installed, commit or staging.pin()["commit"], wait_exit, run_id
        self.calls = []

    def which(self, name):
        if name == "weft":
            return "/usr/bin/weft" if self.installed == "native" else None
        if name == "wsl.exe":
            return "C:/Windows/System32/wsl.exe" if self.installed in ("wsl", "wsl-empty") else None
        return None

    def __call__(self, argv, cwd, stdin, timeout):
        self.calls.append((argv, cwd, stdin))
        text = " ".join(argv)
        if "command -v weft" in text:
            return (0, "/home/u/.local/bin/weft\n", "") if self.installed == "wsl" else (1, "", "")
        if "rev-parse" in text:
            return 0, self.commit + "\n", ""
        if "--version" in text:
            return 0, "weft 0.2.0\n", ""
        if "daemon" in text and "status" in text:
            return 0, "weft: running at http://127.0.0.1:14111 (install 'default'); 1 project(s)\n", ""
        if "catalog" in text and "update" in text:
            return 0, "", ""
        if "wslpath" in text:
            return 0, "/home/u/.desk-weft/requirement_to_profile\n", ""
        if "validate" in text:
            return 0, json.dumps({"diagnostics": []}), ""
        if " run " in " " + text + " ":
            return 0, json.dumps({"phase": "build", "detail": "compiling"}) + "\n" + json.dumps({"phase": "started", "detail": {"runId": self.run_id, "projectId": "p"}}) + "\n", ""
        if " runs " in " " + text + " ":
            return 0, json.dumps([{"id": self.run_id, "status": "completed"}]), ""
        if " wait " in " " + text + " ":
            return self.wait_exit, "", ""
        return 0, "", ""

    def runtime(self, platform="linux"):
        return rt.WeftRuntime(runner=self, platform=platform, which=self.which)


class RuntimeTests(unittest.TestCase):
    def test_missing_weft_is_reported_and_never_replaced(self):
        r = FakeWeft(installed=None).runtime()
        self.assertFalse(r.available())
        self.assertFalse(r.status()["available"])
        with self.assertRaises(rt.WeftUnavailable) as cm:
            r.require()
        self.assertIn("does not fall back", str(cm.exception))

    def test_run_command_refuses_without_weft_and_calls_no_engine(self):
        fake = FakeWeft(installed=None)
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["run", "requirement_to_profile", "--project", "projects/X", "--requirements", __file__], runtime=fake.runtime())
        self.assertEqual(code, 3)
        self.assertIn("cannot proceed", out.getvalue())
        self.assertEqual([c for c in fake.calls if "run" in c[0]], [])

    def test_wsl_with_no_weft_inside_is_unavailable(self):
        self.assertFalse(FakeWeft(installed="wsl-empty").runtime(platform="win32").available())

    def test_native_detection_version_and_pin_match(self):
        st = FakeWeft().runtime().status()
        self.assertEqual((st["kind"], st["version"], st["pinMatch"]), ("native", "weft 0.2.0", True))
        self.assertTrue(st["daemon"]["running"])

    def test_pin_mismatch_is_detected(self):
        st = FakeWeft(commit="f" * 40).runtime().status()
        self.assertIs(st["pinMatch"], False)

    def test_wsl_detection_runs_weft_through_wsl(self):
        fake = FakeWeft(installed="wsl")
        r = fake.runtime(platform="win32")
        self.assertEqual(r.kind(), "wsl")
        r.status()
        self.assertTrue(all(c[0][0] == "wsl.exe" for c in fake.calls))

    def test_run_is_durable_and_passes_inputs_as_node_values(self):
        fake = FakeWeft()
        staged = staging.stage("requirement_to_profile", build_dir=tempfile.mkdtemp(prefix="desk_weft_stage_"))
        r = fake.runtime().run(staged, "requirement_to_profile", {"projectId": "DEMO", "requirements": "5 V"})
        self.assertEqual((r["ok"], r["runId"]), (True, "0193aaaa-run"))
        argv = [c[0] for c in fake.calls if "run" in c[0]][-1]
        self.assertIn("--durable", argv)
        self.assertIn("--detach", argv)
        self.assertIn('projectId={"value": "DEMO"}', argv)
        shutil.rmtree(os.path.dirname(os.path.dirname(staged)), ignore_errors=True)

    def test_run_without_a_run_id_is_a_failure(self):
        fake = FakeWeft(run_id=None)
        staged = staging.stage("requirement_to_profile", build_dir=tempfile.mkdtemp(prefix="desk_weft_stage_"))
        self.assertFalse(fake.runtime().run(staged, "requirement_to_profile", {})["ok"])
        shutil.rmtree(os.path.dirname(os.path.dirname(staged)), ignore_errors=True)

    def test_run_state_maps_weft_wait_exit_codes(self):
        for code, state in ((0, "completed"), (10, "failed_or_cancelled"), (11, "waiting_for_input"), (12, "still_running"), (1, "unknown")):
            self.assertEqual(FakeWeft(wait_exit=code).runtime().run_state("r1")["state"], state)

    def test_resume_of_a_waiting_run_tells_the_operator_weft_resumes_it(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["resume", "r1"], runtime=FakeWeft(wait_exit=11).runtime())
        self.assertEqual(code, 0)
        self.assertIn("paused on a human approval", out.getvalue())

    def test_resume_of_a_failed_run_does_not_restart_it_silently(self):
        fake = FakeWeft(wait_exit=10)
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["resume", "r1"], runtime=fake.runtime())
        self.assertEqual(code, 1)
        self.assertIn("never rolled back", out.getvalue())
        self.assertFalse(any("--seed=r1" in c[0] for c in fake.calls))

    def test_diagnostics_split_errors_from_warnings(self):
        doc = {"diagnostics": [{"severity": "error", "code": "type-mismatch", "message": "m"}, {"severity": "warning", "code": "w", "message": "m"}]}
        r = rt._diagnostics("compiler-harness", 1, json.dumps(doc), "")
        self.assertFalse(r["ok"])
        self.assertEqual((len(r["errors"]), len(r["warnings"])), (1, 1))
        self.assertFalse(rt._diagnostics("compiler-harness", 2, "not json", "boom")["ok"])
        self.assertTrue(rt._diagnostics("weft-cli", 0, json.dumps({"diagnostics": []}), "")["ok"])

    def test_history_reads_the_desk_trace_without_weft(self):
        root = tempfile.mkdtemp(prefix="desk_weft_hist_")
        os.makedirs(os.path.join(root, "DEMO"))
        from desk.weft import nodes
        nodes.execute("DeskRequirementIntake", {"projectId": "DEMO", "runId": "run-9", "requirements": "5 V 1 A buck"}, projects_root=root)
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["history", "--project", os.path.join(root, "DEMO"), "--json"], runtime=FakeWeft(installed=None).runtime())
        doc = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(doc["deskTrace"][0]["runId"], "run-9")
        self.assertIsNone(doc["weft"])
        shutil.rmtree(root, ignore_errors=True)


class WorkflowTests(unittest.TestCase):
    def sources(self, name):
        out = {}
        for base in (os.path.join(staging.workflow_dir(name), "src"), os.path.join(staging.NODES_SRC, "desk_stages")):
            for fn in os.listdir(base):
                if fn.endswith(".weft"):
                    with open(os.path.join(base, fn), encoding="utf-8") as f:
                        out[fn] = f.read()
        return out

    def test_workflows_are_listed(self):
        self.assertEqual([w["name"] for w in staging.workflows()], ["hardware_design", "requirement_to_profile"])

    def test_every_include_names_an_existing_node_file(self):
        for wf in ("hardware_design", "requirement_to_profile"):
            for fn, text in self.sources(wf).items():
                for pkg, name in re.findall(r'@include\("__catalog/(desk|desk_stages)/([a-z_]+\.weft)"\)', text):
                    self.assertTrue(os.path.isfile(os.path.join(staging.NODES_SRC, pkg, name)), f"{fn}: {pkg}/{name}")

    def test_hardware_design_has_the_three_human_approvals_and_a_release_gate_after_the_last(self):
        text = "\n".join(self.sources("hardware_design").values())
        for stage in ('stage = "bom"', 'stage = "schematic"', 'stage = "manufacturing"'):
            self.assertIn(stage, text)
        release = self.sources("hardware_design")["release.weft"]
        self.assertLess(release.index("quality_gate.weft"), release.index('stage = "manufacturing"'))
        self.assertLess(release.index('stage = "manufacturing"'), release.index("release_gate.weft"))
        self.assertLess(release.index("release_gate.weft"), release.index("release_generator.weft"))
        self.assertIn("gate._should_flow = approval.approved", release)
        self.assertIn("generate._should_flow = gate.passed", release)

    def test_every_stage_is_gated_on_the_one_before(self):
        main = self.sources("hardware_design")["main.weft"]
        for line in ("schematic.ready = bom.approved", "schematicApproval._should_flow = schematic.passed",
                     "layout.ready = schematicApproval.approved", "verification.ready = layout.passed", "release.ready = verified.yes"):
            self.assertIn(line, main)

    def test_workflows_carry_no_credential_and_no_shell_or_code_node(self):
        for wf in ("hardware_design", "requirement_to_profile"):
            text = "\n".join(self.sources(wf).values())
            for word in ("ExecPython", "RunCommand", "Bearer", "api_key"):
                self.assertNotIn(word, text)

    def test_staging_assembles_workflow_and_node_library(self):
        build = tempfile.mkdtemp(prefix="desk_weft_stage_")
        staged = staging.stage("hardware_design", build_dir=build)
        for rel in ("weft.toml", "src/main.weft", "nodes/desk/quality_gate.weft", "nodes/desk_stages/approve.weft"):
            self.assertTrue(os.path.isfile(os.path.join(staged, rel)), rel)
        shutil.rmtree(build, ignore_errors=True)

    def test_workflows_compile_under_the_weft_compiler(self):
        runtime = rt.WeftRuntime()
        if not runtime.available() and rt.harness() is None:
            self.skipTest("no Weft compiler on this machine (install Weft or build the compiler harness)")
        for wf in ("requirement_to_profile", "hardware_design"):
            r = cli.validate_workflow(wf, runtime)
            self.assertTrue(r["ok"], r["errors"])
            self.assertEqual(r["warnings"], [], wf)

    def test_weft_compiler_rejects_a_mistyped_wire_into_a_desk_node(self):
        h = rt.harness()
        if h is None:
            self.skipTest("compiler harness not built")
        build = tempfile.mkdtemp(prefix="desk_weft_neg_")
        staged = staging.stage("requirement_to_profile", build_dir=build)
        path = os.path.join(staged, "src", "main.weft")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for broken, code in ((text.replace("families.profileHash = understand.profileHash", "families.profileHash = understand.missingInformation"), "type-mismatch"),
                             (text.replace("power.profileHash = understand.profileHash\n", ""), None),
                             (text.replace("understand.profileHash", "understand.noSuchPort", 1), None)):
            self.assertNotEqual(broken, text)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(broken)
            r = rt.harness_validate(staged, h)
            self.assertFalse(r["ok"], "the compiler accepted a broken graph")
            if code:
                self.assertIn(code, [d.get("code") for d in r["errors"]])
        shutil.rmtree(build, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
