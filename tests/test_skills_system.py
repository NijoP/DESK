"""
Unit tests for the DESK Conditional Skill System & Loader.
"""

import unittest
from pathlib import Path

from desk.skills import Skill, SkillRegistry, get_skill_registry, parse_frontmatter


class TestSkillSystem(unittest.TestCase):
    def setUp(self):
        self.registry = get_skill_registry()

    def test_parse_frontmatter_basic(self):
        sample = """---
name: test-skill
description: A test engineering skill.
triggers:
  - "routing"
  - "traces"
inputs:
  net_names: list
outputs:
  routed: boolean
authoritative_pipeline: M3
replay_safety: SAFE_IDEMPOTENT
---
# Skill Body
Execute step 1.
"""
        meta, body = parse_frontmatter(sample)
        self.assertEqual(meta["name"], "test-skill")
        self.assertEqual(meta["description"], "A test engineering skill.")
        self.assertIn("routing", meta["triggers"])
        self.assertIn("traces", meta["triggers"])
        self.assertEqual(meta["authoritative_pipeline"], "M3")
        self.assertEqual(meta["replay_safety"], "SAFE_IDEMPOTENT")
        self.assertIn("# Skill Body", body)

    def test_all_15_skills_discovered(self):
        skills = self.registry.skills
        # Expect at least 15 registered skills
        self.assertGreaterEqual(len(skills), 15)

        expected_skills = [
            "skill-index",
            "schematic-engineering",
            "component-selection",
            "placement-engineering",
            "pcb-routing",
            "differential-pair-engineering",
            "high-current-design",
            "copper-ground-engineering",
            "engineering-diagnostics",
            "manufacturing-verification",
            "quality-gate-supervision",
            "ship-task-intake",
            "scout-task-intake",
            "execution-recovery",
            "benchmark-performance",
        ]
        for name in expected_skills:
            self.assertIn(name, skills, f"Skill '{name}' was not discovered.")

    def test_match_skills_routing(self):
        matches = self.registry.match_skills("Please route the high speed USB trace on layer 1")
        self.assertTrue(len(matches) > 0)
        top_skill, score = matches[0]
        self.assertIn(top_skill.name, ["pcb-routing", "differential-pair-engineering"])
        self.assertGreater(score, 0)

    def test_match_skills_copper(self):
        matches = self.registry.match_skills("Pour ground copper plane on bottom layer with thermal reliefs")
        self.assertTrue(len(matches) > 0)
        top_skill, score = matches[0]
        self.assertEqual(top_skill.name, "copper-ground-engineering")

    def test_get_skill_context(self):
        ctx = self.registry.get_skill_context("differential pair skew check")
        self.assertIn("differential-pair-engineering", ctx)
        self.assertIn("M3", ctx)
        self.assertIn("Checklist", ctx)


if __name__ == "__main__":
    unittest.main()
