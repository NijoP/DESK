"""The Linux validation package (integrations/weft/linux): what can be proven without Linux, Docker or Weft.

The scripts themselves run only on the separate Linux machine. Here: the fixture passes the DESK stages the run
expects to pass, the trace checker gives the right verdicts on real DESK records, every node the scripts name
exists, and no script prints a secret.
"""
import glob
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from desk.weft import contracts as C, nodes
from desk.weft.store import RecordStore

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINUX = os.path.join(REPO, "integrations", "weft", "linux")
sys.path.insert(0, LINUX)
import check_trace  # noqa: E402

with open(os.path.join(LINUX, "fixtures", "weftval_requirements.json"), encoding="utf-8") as _f:
    FIXTURE = _f.read()
SCRIPTS = sorted(glob.glob(os.path.join(LINUX, "*.sh")))


class FixtureTests(unittest.TestCase):
    """40_run_requirement_to_profile.sh expects these six DESK calls to pass for the fixture."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="desk_weft_linux_")
        os.makedirs(os.path.join(self.root, "WEFTVAL01"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def call(self, node, run="run-a", **inputs):
        status, env = nodes.execute(node, dict(projectId="WEFTVAL01", runId=run, **inputs), projects_root=self.root)
        return status, env

    def understand(self, run):
        s, intake = self.call("DeskRequirementIntake", run, requirements=FIXTURE)
        self.assertEqual(s, 200)
        h = intake["outputs"]["requirementsHash"]
        self.assertTrue(self.call("DeskRequirementValidator", run, requirementsHash=h)[1]["passed"])
        self.assertTrue(self.call("DeskDomainClassifier", run, requirementsHash=h)[1]["passed"])
        ph = self.call("DeskDesignProfileCompiler", run, requirementsHash=h)[1]["outputs"]["profileHash"]
        self.assertTrue(self.call("DeskComponentFamilyResolver", run, profileHash=ph)[1]["passed"])
        self.assertTrue(self.call("DeskPowerDistributionAnalyzer", run, profileHash=ph)[1]["passed"])
        return ph

    def check(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = check_trace.main(["--projects-root", self.root, "--project", "WEFTVAL01"] + list(argv))
        return code, json.loads(out.getvalue())

    def test_the_fixture_passes_understand_and_engineering(self):
        self.understand("run-a")
        six = ["DeskRequirementIntake", "DeskRequirementValidator", "DeskDomainClassifier", "DeskDesignProfileCompiler",
               "DeskComponentFamilyResolver", "DeskPowerDistributionAnalyzer"]
        code, doc = self.check("--run", "run-a", "--called", *six, "--not-called", "DeskApprovalRecorder", "--no-approval", "--all-passed")
        self.assertEqual(code, 0, doc)

    def test_approval_and_replay_are_read_from_desk_records(self):
        ph = self.understand("run-a")
        self.call("DeskApprovalRecorder", "run-a", stage="profile", decision="approved", subjectHash=ph)
        self.assertEqual(self.check("--run", "run-a", "--approval", "profile=approved", "--all-passed")[0], 0)
        self.assertEqual(self.check("--run", "run-a", "--approval", "profile=rejected")[0], 1)
        self.assertEqual(self.check("--run", "run-a", "--no-approval")[0], 1)
        self.understand("run-b")                                             # same requirements, a second run
        self.assertEqual(self.check("--run", "run-b", "--replayed", "DeskRequirementIntake", "DeskPowerDistributionAnalyzer")[0], 0)
        self.assertEqual(self.check("--run", "run-a", "--replayed", "DeskRequirementIntake")[0], 1)   # run-a executed it

    def test_hardware_design_stops_where_the_script_expects(self):
        self.understand("run-h")
        # exactly what nodes/desk_stages/components.weft sends it: projectId and runId
        status, env = self.call("DeskComponentSearch", "run-h")
        self.assertEqual(status, 501)
        self.assertNotIn("outputs", env)
        code, doc = self.check("--run", "run-h", "--failed", "DeskComponentSearch=NODE_UNAVAILABLE",
                               "--not-called", "DeskBOMGenerator", "DeskReleaseGate", "--no-approval")
        self.assertEqual(code, 0, doc)

    def test_a_run_desk_never_saw_passes_no_check(self):
        code, doc = self.check("--run", "never-ran", "--not-called", "DeskReleaseGate", "--no-approval")
        self.assertEqual(code, 1)
        self.assertEqual([c["result"] for c in doc["checks"]], ["FAIL", "FAIL", "FAIL"])


class ScriptTests(unittest.TestCase):
    def text(self, path):
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()

    def test_the_package_is_complete(self):
        names = [os.path.basename(p) for p in SCRIPTS]
        for n in ("common.sh", "00_preflight.sh", "10_install_prereqs.sh", "20_install_weft.sh", "30_prepare_desk.sh",
                  "40_run_requirement_to_profile.sh", "50_run_hardware_design.sh", "60_full_suite.sh", "90_collect.sh", "99_cleanup.sh"):
            self.assertIn(n, names)

    def test_every_node_a_script_names_exists(self):
        ids = {c.node_id for c in C.CONTRACTS}
        for path in SCRIPTS:
            used = set(re.findall(r"\bDesk[A-Z][A-Za-z]+\b", self.text(path)))
            self.assertEqual(used - ids, set(), os.path.basename(path))

    def test_scripts_that_change_the_machine_need_yes(self):
        for n in ("10_install_prereqs.sh", "20_install_weft.sh"):
            self.assertIn('require_yes "$@"', self.text(os.path.join(LINUX, n)))

    def test_secrets_are_only_ever_read_into_an_environment_variable(self):
        for path in SCRIPTS:
            for line in self.text(path).splitlines():
                for m in re.finditer(r'\$\(cat "\$\{?(tokfile|keyfile)\}?"\)', line):
                    before = line[:m.start()]
                    self.assertRegex(before, r'[A-Z_]+="[^"]*$', f"{os.path.basename(path)}: {line.strip()}")
            self.assertNotRegex(self.text(path), r"echo[^\n]*(DESK_WEFT_SIGNAL_TOKEN|DESK_WEFT_BEARER|CREDENTIAL_ENCRYPTION_KEY)")

    def test_the_weft_install_is_pinned_and_never_the_one_line_installer(self):
        install = self.text(os.path.join(LINUX, "20_install_weft.sh"))
        self.assertIn('checkout --quiet --detach "${PIN}"', install)
        self.assertNotIn("weft.weavemind.ai/install.sh", install.replace("Upstream's one-line installer", ""))
        self.assertIn("export WEFT_INSTALL=default", self.text(os.path.join(LINUX, "common.sh")))

    def test_line_endings_stay_lf_on_checkout(self):
        with open(os.path.join(LINUX, ".gitattributes"), encoding="utf-8") as f:
            self.assertIn("*.sh text eol=lf", f.read())


if __name__ == "__main__":
    unittest.main()
