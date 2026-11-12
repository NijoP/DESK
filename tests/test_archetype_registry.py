"""Registry: lazy loading, indexed lookup, mtime invalidation, performance with the full library."""
import json
import os
import shutil
import tempfile
import time
import unittest

from desk.domain_intelligence.registry import DomainLibrary, get_library, _DEFAULT_ROOT


class RegistryTests(unittest.TestCase):
    def test_lazy_load_reads_only_the_index_first(self):
        lib = DomainLibrary(_DEFAULT_ROOT)
        lib.taxonomy()
        self.assertEqual(len(lib._cache), 1)
        lib.archetype("buck_converter")
        self.assertEqual(len(lib._cache), 2)

    def test_unknown_archetype_raises(self):
        with self.assertRaises(KeyError):
            get_library().archetype("no_such_board")

    def test_mtime_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "lib")
            shutil.copytree(_DEFAULT_ROOT, root)
            lib = DomainLibrary(root)
            a = lib.archetype("buck_converter")
            self.assertEqual(a.name, "Buck (step-down) converter")
            p = os.path.join(root, "archetypes", "buck_converter.json")
            data = json.load(open(p, encoding="utf-8"))
            data["name"] = "Buck (edited)"
            time.sleep(0.02)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.utime(p, None)
            self.assertEqual(lib.archetype("buck_converter").name, "Buck (edited)")

    def test_rules_cache_rebuilds_when_a_rule_set_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "lib")
            shutil.copytree(_DEFAULT_ROOT, root)
            lib = DomainLibrary(root)
            n = len(lib.rules())
            p = os.path.join(root, "rule_sets", "core.json")
            data = json.load(open(p, encoding="utf-8"))
            extra = dict(data["rules"][0]); extra["rule_id"] = "TEST-NEW-999"
            data["rules"].append(extra)
            time.sleep(0.02)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f)
            self.assertEqual(len(lib.rules()), n + 1)
            self.assertIn("TEST-NEW-999", lib.rules())

    def test_duplicate_rule_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "lib")
            shutil.copytree(_DEFAULT_ROOT, root)
            lib = DomainLibrary(root)
            p = os.path.join(root, "rule_sets", "core.json")
            data = json.load(open(p, encoding="utf-8"))
            data["rules"].append(dict(data["rules"][0]))
            time.sleep(0.02)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f)
            with self.assertRaises(ValueError):
                lib.rules()

    def test_full_library_load_is_fast(self):
        lib = DomainLibrary(_DEFAULT_ROOT)
        t0 = time.perf_counter()
        n = sum(1 for _ in lib.archetypes())
        lib.rules(); lib.families(); lib.overlays(); lib.references()
        dt = time.perf_counter() - t0
        self.assertEqual(n, 100)
        self.assertLess(dt, 2.0, f"cold load took {dt:.2f}s")
        t1 = time.perf_counter()
        sum(1 for _ in lib.archetypes())
        self.assertLess(time.perf_counter() - t1, 0.2)


if __name__ == "__main__":
    unittest.main()
