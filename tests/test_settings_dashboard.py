"""Tests for Ecosystem Settings and Dashboard."""

import unittest
from desk.ui.settings import EcosystemDashboard


class TestSettingsDashboard(unittest.TestCase):
    def setUp(self):
        self.dash = EcosystemDashboard()

    def test_vault_status(self):
        v = self.dash.get_vault_status()
        self.assertIn("backend", v)
        self.assertEqual(v["status"], "HEALTHY")

    def test_eda_status(self):
        eda = self.dash.get_eda_status()
        self.assertIn("easyeda_cli", eda)
        self.assertIn("easyeda_bridge", eda)
        self.assertIn("kicad", eda)

    def test_suppliers_status(self):
        supps = self.dash.get_suppliers_status()
        services = [s["service"] for s in supps]
        self.assertIn("lcsc", services)
        self.assertIn("mouser", services)
        self.assertIn("digikey", services)

    def test_render_dashboard(self):
        rendered = self.dash.render_dashboard()
        self.assertIn("DESK ECOSYSTEM READINESS DASHBOARD", rendered)
        self.assertIn("OS CREDENTIAL SECURITY VAULT", rendered)
        self.assertIn("ELECTRONICS DESIGN AUTOMATION", rendered)
        self.assertIn("COMPONENT INTELLIGENCE & SOURCING", rendered)
        self.assertIn("PCB & PCBA MANUFACTURING", rendered)


if __name__ == "__main__":
    unittest.main()
