"""desk.config: precedence env > user file > repo file > default, validation, masking, schema coverage."""
import json
import os
import re
import tempfile
import unittest

from desk import config as cfgmod
from desk.config import Config, SCHEMA, setting_for


class ConfigPrecedence(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.repo = os.path.join(self.d, "desk.config.json")
        self.user = os.path.join(self.d, "user.json")

    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_default_then_repo_then_user_then_env(self):
        c = Config(repo_file=self.repo, user_file=self.user, env={})
        self.assertEqual(c.get("DESK_HTTP_MAX_TOKENS"), "2048")
        self.assertEqual(c.source("DESK_HTTP_MAX_TOKENS"), "default")
        self._write(self.repo, {"DESK_HTTP_MAX_TOKENS": 1000})
        self.assertEqual(c.get_int("DESK_HTTP_MAX_TOKENS"), 1000)
        self.assertEqual(c.source("DESK_HTTP_MAX_TOKENS"), "repo")
        self._write(self.user, {"DESK_HTTP_MAX_TOKENS": 1500})
        self.assertEqual(c.get_int("DESK_HTTP_MAX_TOKENS"), 1500)
        self.assertEqual(c.source("DESK_HTTP_MAX_TOKENS"), "user")
        c = Config(repo_file=self.repo, user_file=self.user, env={"DESK_HTTP_MAX_TOKENS": "3000"})
        self.assertEqual(c.get_int("DESK_HTTP_MAX_TOKENS"), 3000)
        self.assertEqual(c.source("DESK_HTTP_MAX_TOKENS"), "env")

    def test_empty_env_string_counts_as_unset(self):
        self._write(self.repo, {"DESK_JAVA": "C:/jdk/bin/java.exe"})
        c = Config(repo_file=self.repo, user_file=self.user, env={"DESK_JAVA": "   "})
        self.assertEqual(c.get("DESK_JAVA"), "C:/jdk/bin/java.exe")
        self.assertIsNone(Config(repo_file=self.repo + ".none", user_file=self.user, env={}).get("DESK_JAVA"))

    def test_env_is_read_live_after_construction(self):
        env = {}
        c = Config(repo_file=self.repo, user_file=self.user, env=env)
        self.assertIsNone(c.get("DESK_L1_TIMEOUT"))
        env["DESK_L1_TIMEOUT"] = "12.5"
        self.assertEqual(c.get_float("DESK_L1_TIMEOUT"), 12.5)

    def test_file_edits_are_picked_up_by_mtime(self):
        self._write(self.repo, {"DESK_PROVIDER_ORDER": "nvidia,pi"})
        c = Config(repo_file=self.repo, user_file=self.user, env={})
        self.assertEqual(c.get("DESK_PROVIDER_ORDER"), "nvidia,pi")
        self._write(self.repo, {"DESK_PROVIDER_ORDER": "pi"})
        os.utime(self.repo, (1, 1))          # force a distinct mtime even inside one filesystem tick
        self.assertEqual(c.get("DESK_PROVIDER_ORDER"), "pi")

    def test_bool_parsing(self):
        c = Config(repo_file=self.repo, user_file=self.user, env={"DESK_TELEMETRY": "0", "DESK_MOCK_SUPPLIERS": "true"})
        self.assertFalse(c.get_bool("DESK_TELEMETRY", True))
        self.assertTrue(c.get_bool("DESK_MOCK_SUPPLIERS"))
        self.assertTrue(Config(repo_file=self.repo, user_file=self.user, env={}).get_bool("DESK_TELEMETRY", True))


class ConfigValidation(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.repo = os.path.join(self.d, "desk.config.json")
        self.user = os.path.join(self.d, "user.json")

    def _write(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_unknown_key_bad_type_secret_in_repo_are_reported(self):
        self._write(self.repo, {"NVIDIA_API_KEY": "nvapi-xyz", "DESK_L2_TIMEOUT": "ninety", "DESK_NOPE": 1,
                                "DESK_L1_THINKING": "max"})
        c = Config(repo_file=self.repo, user_file=self.user, env={"DESK_HTTP_MAX_TOKENS": "lots"})
        probs = "\n".join(c.validate())
        self.assertIn("NVIDIA_API_KEY is a secret", probs)
        self.assertIn("DESK_L2_TIMEOUT='ninety' invalid", probs)
        self.assertIn("unknown key DESK_NOPE", probs)
        self.assertIn("DESK_L1_THINKING", probs)
        self.assertIn("DESK_HTTP_MAX_TOKENS='lots' invalid", probs)

    def test_malformed_file_is_one_problem_not_a_crash(self):
        with open(self.repo, "w", encoding="utf-8") as f:
            f.write("{not json")
        c = Config(repo_file=self.repo, user_file=self.user, env={})
        self.assertTrue(any("repo file" in p for p in c.validate()))
        self.assertEqual(c.get("DESK_HTTP_MAX_TOKENS"), "2048")

    def test_secrets_are_masked_in_rows_and_render(self):
        c = Config(repo_file=self.repo, user_file=self.user, env={"NVIDIA_API_KEY": "nvapi-abcdefghijklmnop"})
        row = [r for r in c.as_rows() if r["key"] == "NVIDIA_API_KEY"][0]
        self.assertNotIn("abcdefgh", row["value"])
        self.assertTrue(row["value"].startswith("***"))
        self.assertNotIn("nvapi-abcdefghijklmnop", c.render())
        self.assertIn("valid", c.render())

    def test_dynamic_tier_keys_match_schema(self):
        self.assertIsNotNone(setting_for("DESK_L3_MODEL_NVIDIA"))
        self.assertIsNotNone(setting_for("DESK_L4_TIMEOUT"))
        self.assertIsNotNone(setting_for("DESK_L2_THINKING"))
        self.assertIsNone(setting_for("DESK_L9_TIMEOUT"))
        self.assertIsNone(setting_for("DESK_L1_MODEL_OPENAI"))


class SchemaCoversEveryEnvironmentRead(unittest.TestCase):
    """Every `os.environ` read of a DESK/EDA/engine variable in desk/ and tools/ is routed through
    desk.config, except the files listed in ALLOWED (owned by an in-progress change elsewhere)."""
    ALLOWED = {"desk/orchestrator/pi_adapter.py", "desk/config.py", "desk/learn/engine.py"}
    PATTERN = re.compile(r"environ(?:\.get)?\(\s*['\"](DESK_[A-Z_0-9]+|EDA_[A-Z_]+|NVIDIA_API_KEY|LCSC_[A-Z_]+|"
                         r"FREEROUTING_[A-Z]+|EASYEDA_API_REF)['\"]|environ\[['\"](DESK_[A-Z_0-9]+|EDA_[A-Z_]+)['\"]\]")

    def test_no_direct_reads_outside_allowed(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offenders = []
        for sub in ("desk", "tools"):
            for dp, _, files in os.walk(os.path.join(root, sub)):
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    rel = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
                    if rel in self.ALLOWED:
                        continue
                    with open(os.path.join(dp, fn), encoding="utf-8", errors="replace") as f:
                        for n, line in enumerate(f, 1):
                            m = self.PATTERN.search(line)
                            if m and "deskcfg" not in line:
                                offenders.append(f"{rel}:{n}: {line.strip()[:90]}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_every_schema_key_has_description_and_group(self):
        for s in SCHEMA:
            self.assertTrue(s.description and s.group, s.key)

    def test_module_shortcuts(self):
        self.assertEqual(cfgmod.get("DESK_HTTP_API_KEY_ENV"), os.environ.get("DESK_HTTP_API_KEY_ENV") or "NVIDIA_API_KEY")
        self.assertIsInstance(cfgmod.get_int("DESK_HTTP_MAX_TOKENS", 1), int)


if __name__ == "__main__":
    unittest.main()
