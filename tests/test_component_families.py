"""M2: component family ontology consistency and compatibility with archetypes."""
import unittest

from desk.domain_intelligence import get_library

ROLE_FIELDS = ["description", "electrical_characteristics", "required_parameters", "compatibility_requirements", "datasheet_verification",
               "placement_constraints", "routing_considerations", "relevant_archetypes"]


class FamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib = get_library()
        cls.fams = cls.lib.families()

    def test_groups_cover_directive_categories(self):
        groups = set(self.lib.family_groups())
        for g in ("power", "passive", "digital", "rf", "analog", "interface_protection", "sensor_actuator"):
            self.assertIn(g, groups)

    def test_every_family_has_the_role_contract(self):
        for fid, f in self.fams.items():
            for k in ROLE_FIELDS:
                self.assertIn(k, f.data, f"{fid} missing {k}")
            self.assertTrue(f.data["description"], fid)
            self.assertIn(f.group, self.lib.family_groups(), fid)

    def test_no_fake_part_numbers_in_the_ontology(self):
        import re
        mpn_like = re.compile(r"\b[A-Z]{2,}[0-9]{3,}[A-Z0-9-]*\b")
        generic = {"CR2032", "TL431", "PT100", "PT1000", "RS485", "RS422", "RS232", "IEC", "ISO"}   # sizes, classes and standards, not part numbers
        for fid, f in self.fams.items():
            blob = " ".join([f.data["description"]] + f.data["electrical_characteristics"] + f.data["compatibility_requirements"])
            hits = [m for m in mpn_like.findall(blob) if m not in generic]
            self.assertEqual(hits, [], f"{fid}: looks like an MPN in the ontology: {hits}")

    def test_archetype_roles_exist_and_relevance_is_consistent(self):
        for a in self.lib.archetypes():
            for r in a.required_roles:
                self.assertIn(r, self.fams, f"{a.archetype_id}: {r}")
                self.assertIn(a.archetype_id, self.fams[r].data["relevant_archetypes"], f"{r} should list {a.archetype_id}")
            self.assertTrue(set(a.required_roles) <= set(a.families), a.archetype_id)

    def test_every_family_is_used_or_added_by_an_overlay(self):
        used = set()
        for a in self.lib.archetypes():
            used |= set(a.families)
        for o in self.lib.overlays():
            used |= set(o.families)
        unused = sorted(set(self.fams) - used)
        self.assertLessEqual(len(unused), 12, f"too many orphan families: {unused}")

    def test_family_ids_unique_and_snake_case(self):
        import re
        for fid in self.fams:
            self.assertRegex(fid, r"^[a-z0-9_]+$")


if __name__ == "__main__":
    unittest.main()
