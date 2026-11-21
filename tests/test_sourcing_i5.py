"""Roadmap I-5: in-stock-first sourcing on a fixture catalogue (offline, no network).

All MPNs are synthetic (DESK-FIX-*) so no test claims anything about a real part's availability.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from desk.component_intelligence.procurement.equivalence import (
    Equivalence,
    check_electrical,
    check_footprint,
    normalize_package,
    requirement_from_part,
)
from desk.component_intelligence.procurement.inventory import InventoryState, classify_offer
from desk.component_intelligence.procurement.selection import SourcingPolicy, build_sourcing_report
from desk.component_intelligence.suppliers.evidence import (
    EvidenceStore,
    EvidenceSupplierProvider,
    parse_timestamp,
    validate_record,
)
from desk.component_intelligence.suppliers.models import SupplierOffer
from desk.component_intelligence.suppliers.providers.lcsc.client import LcscApiClient
from desk.component_intelligence.suppliers.providers.lcsc.provider import LcscSupplierProvider
from desk.component_intelligence.suppliers.providers.robu import RobuSupplierProvider
from desk.component_intelligence.suppliers.registry import SupplierRegistry
from desk.manufacturing.jlcpcb.parts_library import JlcpcbPartsProvider

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = parse_timestamp("2026-11-21T12:00:00Z")
SEEN = "2026-11-21T10:00:00Z"


def rec(supplier, mpn, sku, package, stock, price=None, currency="USD", **kw):
    host = {"robu": "https://robu.in/product/", "lcsc": "https://www.lcsc.com/product-detail/",
            "jlcpcb": "https://jlcpcb.com/partdetail/"}[supplier]
    r = {"supplier_id": supplier, "mpn": mpn, "sku": sku, "package": package, "stock": stock,
         "price": price, "currency": currency if price is not None else None,
         "source_url": host + sku.lower(), "verified_at": SEEN, "collected_by": "test"}
    r.update(kw)
    return r


CATALOGUE = [
    # LDO: in stock at Robu (INR) and LCSC (USD)
    rec("robu", "DESK-FIX-LDO", "R-LDO", "SOT-223", 500, 9.0, "INR"),
    rec("lcsc", "DESK-FIX-LDO", "C900001", "SOT-223", 5000, 0.15),
    rec("jlcpcb", "DESK-FIX-LDO", "C900001", "SOT-223", 3000, 0.15, assembly_class="Extended"),
    # BUCK: stock-out at LCSC; one compatible and one wrong-package alternative
    rec("lcsc", "DESK-FIX-BUCK-A", "C900010", "SOT-23-6", 0, 0.9),
    rec("lcsc", "DESK-FIX-BUCK-B", "C900011", "SOT-23-6", 4000, 0.95, alternative_for="DESK-FIX-BUCK-A",
        specs={"vin_max_v": 18, "iout_a": 1.5, "pin_count": 6}),
    rec("robu", "DESK-FIX-BUCK-C", "R-BUCKC", "SOT-23-5", 800, 50.0, "INR", alternative_for="DESK-FIX-BUCK-A",
        specs={"vin_max_v": 18, "iout_a": 1.5, "pin_count": 5}),
    # EOL with residual stock
    rec("lcsc", "DESK-FIX-EOL", "C900020", "SOIC-8", 999, 0.5, lifecycle="Discontinued"),
    # Unknown stock
    rec("robu", "DESK-FIX-UNK", "R-UNK", "0603", None, 1.0, "INR", stock_text="Contact us"),
    # Missing price
    rec("lcsc", "DESK-FIX-NOPRICE", "C900030", "0402", 50000, None),
    # Backordered only
    rec("robu", "DESK-FIX-BO", "R-BO", "QFN-24", 0, 120.0, "INR", backorder=True, lead_time_days=21),
    # Supplier listing contradicts the design package
    rec("lcsc", "DESK-FIX-FPMIS", "C900040", "SOT-23-5", 7000, 0.05),
]

PARTS_GOOD = [
    {"ref": "U1", "mpn": "DESK-FIX-LDO", "package": "SOT-223"},
    {"ref": "U2", "mpn": "DESK-FIX-BUCK-A", "package": "SOT-23-6",
     "specs": {"vin_max_v": 17, "iout_a": 1.2, "pin_count": 6}},
    {"ref": "C1", "mpn": "DESK-FIX-NOPRICE", "package": "0402"},
]
PARTS_BAD = [
    {"ref": "U3", "mpn": "DESK-FIX-EOL", "package": "SOIC-8"},
    {"ref": "R1", "mpn": "DESK-FIX-UNK", "package": "0603"},
    {"ref": "U4", "mpn": "DESK-FIX-BO", "package": "QFN-24"},
    {"ref": "Q1", "mpn": "DESK-FIX-FPMIS", "package": "SOT-23"},
]


def registry(store):
    reg = SupplierRegistry()
    reg.register(RobuSupplierProvider(store))
    reg.register(EvidenceSupplierProvider("lcsc", "LCSC Electronics", store))
    reg.register(JlcpcbPartsProvider(store))
    return reg


def loaded_store():
    store = EvidenceStore()
    rep = store.ingest({"schema": "desk.sourcing.evidence/1", "records": CATALOGUE}, now=NOW)
    assert not rep.rejected, rep.rejected
    return store


def report(parts, **policy):
    store = loaded_store()
    return build_sourcing_report(parts, registry(store), SourcingPolicy(**policy), batch_quantity=10, now=NOW)


def line(rep, mpn):
    return next(ln for ln in rep.lines if ln.request.mpn == mpn)


class TestInventoryClassifier(unittest.TestCase):
    def offer(self, **kw):
        base = dict(supplier_id="lcsc", supplier_name="LCSC", sku="C1", canonical_desk_id="x",
                    manufacturer_name="m", mpn="M", stock=1000, unit_price=0.1,
                    availability_source="agent_evidence", last_checked_ts=NOW - 3600)
        base.update(kw)
        return SupplierOffer(**base)

    def state(self, qty=10, **kw):
        return classify_offer(self.offer(**kw), qty, now=NOW)

    def test_seven_states(self):
        self.assertEqual(self.state().state, InventoryState.IN_STOCK_CONFIRMED)
        self.assertEqual(self.state(stock=15).state, InventoryState.LOW_STOCK)
        self.assertEqual(self.state(stock=0).state, InventoryState.OUT_OF_STOCK)
        self.assertEqual(self.state(stock=0, backorder=True).state, InventoryState.BACKORDERED)
        self.assertEqual(self.state(lifecycle="EOL").state, InventoryState.DISCONTINUED)
        self.assertEqual(self.state(stock_known=False).state, InventoryState.STOCK_UNKNOWN)
        self.assertEqual(self.state(unit_price=0.0).state, InventoryState.PRICE_UNAVAILABLE)

    def test_unverified_is_never_in_stock(self):
        for src in ("fixture", "seed", "unverified", ""):
            a = self.state(availability_source=src, stock=10 ** 6)
            self.assertEqual(a.state, InventoryState.STOCK_UNKNOWN, src)
            self.assertFalse(a.in_stock)
            self.assertIsNone(a.stock)
            self.assertTrue(any("not verified" in x for x in a.limitations))

    def test_stale_future_and_missing_timestamps(self):
        self.assertEqual(self.state(last_checked_ts=NOW - 8 * 86400).state, InventoryState.STOCK_UNKNOWN)
        self.assertEqual(self.state(last_checked_ts=NOW + 3600).state, InventoryState.STOCK_UNKNOWN)
        self.assertEqual(self.state(last_checked_ts=0).state, InventoryState.STOCK_UNKNOWN)

    def test_low_stock_that_does_not_cover_is_not_in_stock(self):
        a = self.state(stock=5)
        self.assertEqual(a.state, InventoryState.LOW_STOCK)
        self.assertFalse(a.in_stock)

    def test_unknown_lifecycle_text_is_not_active(self):
        a = self.state(lifecycle="weird")
        self.assertEqual(a.lifecycle.value, "UNKNOWN")
        self.assertTrue(any("not recognised" in x for x in a.limitations))


class TestEvidence(unittest.TestCase):
    def test_valid_catalogue(self):
        self.assertEqual(len(loaded_store()), len(CATALOGUE))

    def test_rejections(self):
        good = rec("robu", "X", "X", "0402", 1, 1.0, "INR")
        cases = {
            "supplier_id": dict(good, supplier_id="nope"),
            "domain": dict(good, source_url="https://example.com/x"),
            "https": dict(good, source_url="http://robu.in/x"),
            "timezone": dict(good, verified_at="2026-11-21T10:00:00"),
            "future": dict(good, verified_at="2027-01-01T00:00:00Z"),
            "stock": dict(good, stock=-1),
            "bool stock": dict(good, stock=True),
            "price": dict(good, price=0),
            "currency": dict(good, currency=None),
            "mpn": dict(good, mpn=""),
        }
        for name, r in cases.items():
            self.assertTrue(validate_record(r, now=NOW), name)
        store = EvidenceStore()
        rep = store.ingest(list(cases.values()) + [good], now=NOW)
        self.assertEqual(rep.accepted, 1)
        self.assertEqual(len(rep.rejected), len(cases))

    def test_newest_record_wins(self):
        store = EvidenceStore()
        store.ingest([rec("robu", "X", "X", "0402", 1, 1.0, "INR", verified_at="2026-11-20T00:00:00Z"),
                      rec("robu", "X", "X", "0402", 7, 1.0, "INR")], now=NOW)
        self.assertEqual(store.offers("robu")[0].stock, 7)


class TestLcscKeylessDetail(unittest.TestCase):
    """The public detail route answers a wrapped {"code", "result"} object (probed 2026-11-21)."""

    PAYLOAD = {"code": 200, "msg": None, "result": {
        "productCode": "C900050", "productModel": "DESK-FIX-FET", "brandNameEn": "Fixture",
        "encapStandard": "SOT-23", "stockNumber": 1234, "productCycle": "normal", "isPreSale": False,
        "currencyType": "USD",
        "productPriceList": [{"ladder": 50, "productPrice": "0.0157", "usdPrice": 0.0157}],
        "pdfUrl": "https://datasheet.lcsc.com/x.pdf", "productDescEn": "fixture"}}

    def test_detail_parse_marks_live_and_no_network(self):
        resp = mock.MagicMock()
        resp.read.return_value = json.dumps(self.PAYLOAD).encode()
        resp.__enter__.return_value = resp
        client = LcscApiClient(use_offline_fixtures=False, min_interval_s=0)
        with mock.patch("urllib.request.urlopen", return_value=resp) as op:
            offer = LcscSupplierProvider(client=client).get_component("C900050")
            LcscSupplierProvider(client=client).get_component("C900050")  # cached
        self.assertEqual(op.call_count, 1)
        self.assertEqual((offer.mpn, offer.package, offer.stock), ("DESK-FIX-FET", "SOT-23", 1234))
        self.assertEqual(offer.availability_source, "live_api")
        self.assertAlmostEqual(offer.unit_price, 0.0157)
        self.assertEqual(classify_offer(offer, 100).state, InventoryState.IN_STOCK_CONFIRMED)

    def test_keyless_mpn_search_is_a_stated_limitation(self):
        client = LcscApiClient(client_id="", client_secret="", use_offline_fixtures=False, min_interval_s=0)
        client.client_id = client.client_secret = None
        with mock.patch("urllib.request.urlopen") as op:
            self.assertEqual(client.search_products("DESK-FIX-FET"), [])
        op.assert_not_called()
        self.assertTrue(any("no MPN search" in x for x in client.limitations))

    def test_fixture_offers_are_stock_unknown(self):
        offer = LcscSupplierProvider(client=LcscApiClient(use_offline_fixtures=True)).get_component("C11702")
        self.assertEqual(offer.availability_source, "fixture")
        self.assertEqual(classify_offer(offer, 1).state, InventoryState.STOCK_UNKNOWN)


class TestEquivalence(unittest.TestCase):
    def test_package_normalisation(self):
        self.assertEqual(normalize_package("SOT-23-3_L2.9-W1.3-P1.90"), "SOT-23")
        self.assertEqual(normalize_package("R0402"), "0402")
        self.assertNotEqual(normalize_package("SOIC-8"), normalize_package("SOP-8"))

    def test_footprint_checks(self):
        self.assertIs(check_footprint("SOT-23", "SOT-23-3").verdict, Equivalence.COMPATIBLE)
        self.assertIs(check_footprint("SOT-23", "SOT-23-5").verdict, Equivalence.INCOMPATIBLE)
        self.assertIs(check_footprint("", "SOT-23").verdict, Equivalence.UNVERIFIED)
        self.assertIs(check_footprint("QFN-16", "QFN-16", {"body_l_mm": 3.0}, {"body_l_mm": 4.0}).verdict,
                      Equivalence.INCOMPATIBLE)

    def test_electrical_checks(self):
        req = requirement_from_part({"value": "100nF", "rating": "16V X7R 10%"})
        self.assertEqual(req, {"value": "100nF", "voltage_v": 16.0, "tolerance_pct": 10.0, "dielectric": "X7R"})
        ok = {"value": "100nF", "voltage_v": 25, "tolerance_pct": 10, "dielectric": "X7R"}
        self.assertIs(check_electrical(req, ok).verdict, Equivalence.COMPATIBLE)
        self.assertIs(check_electrical(req, dict(ok, voltage_v=10)).verdict, Equivalence.INCOMPATIBLE)
        self.assertIs(check_electrical(req, dict(ok, dielectric="Y5V")).verdict, Equivalence.INCOMPATIBLE)
        self.assertIs(check_electrical(req, {"value": "100nF"}).verdict, Equivalence.UNVERIFIED)
        self.assertIs(check_electrical({}, ok).verdict, Equivalence.UNVERIFIED)


class TestSelection(unittest.TestCase):
    def test_i5_acceptance_on_fixture_bom(self):
        rep = report(PARTS_GOOD)
        acc = rep.acceptance()
        self.assertTrue(acc["i5_acceptance"], acc)
        self.assertEqual(acc["backordered_selections_without_permission"], 0)
        for ln in rep.lines:  # every line carries supplier, source URL, timestamp and stock
            snap = ln.snapshot()
            self.assertTrue(snap["supplier_id"] and snap["source_url"].startswith("https://"))
            self.assertTrue(snap["verified_at"].endswith("Z"))
            self.assertIsNotNone(snap["stock"])
        self.assertEqual(rep.verdict, "INCOMPLETE")  # the NOPRICE line has no price
        self.assertEqual(acc["selected_lines_without_price"], ["DESK-FIX-NOPRICE"])

    def test_preferred_and_price_ranking_is_deterministic(self):
        ldo = line(report(PARTS_GOOD), "DESK-FIX-LDO")
        self.assertEqual(ldo.selected.offer.supplier_id, "lcsc")  # INR not comparable without a rate
        ldo = line(report(PARTS_GOOD, fx_to_base={"INR": 0.012}), "DESK-FIX-LDO")
        self.assertEqual(ldo.selected.offer.supplier_id, "robu")  # 9 INR = 0.108 USD < 0.15 USD
        self.assertEqual(ldo.assembly["assembly_class"], "Extended")
        self.assertEqual(ldo.assembly["class_source"], "jlcpcb_evidence")
        keys = [json.dumps(report(PARTS_GOOD + PARTS_BAD).to_dict(), sort_keys=True) for _ in range(2)]
        self.assertEqual(keys[0], keys[1])

    def test_stock_out_takes_compatible_alternative_only(self):
        buck = line(report(PARTS_GOOD), "DESK-FIX-BUCK-A")
        self.assertEqual(buck.status, "SELECTED_ALTERNATIVE")
        self.assertEqual(buck.selected.offer.mpn, "DESK-FIX-BUCK-B")
        wrong = next(c for c in buck.candidates if c.offer.mpn == "DESK-FIX-BUCK-C")
        self.assertFalse(wrong.selectable)
        self.assertIs(wrong.footprint.verdict, Equivalence.INCOMPATIBLE)

    def test_bad_lines_are_unresolved_with_reasons(self):
        rep = report(PARTS_BAD)
        self.assertTrue(all(ln.selected is None for ln in rep.lines))
        self.assertEqual(line(rep, "DESK-FIX-EOL").candidates[0].assessment.state, InventoryState.DISCONTINUED)
        unk = line(rep, "DESK-FIX-UNK")
        self.assertEqual(unk.snapshot()["state"], "STOCK_UNKNOWN")
        self.assertTrue(any("no stock figure" in x for x in unk.limitations))
        fp = line(rep, "DESK-FIX-FPMIS").candidates[0]
        self.assertTrue(any("contradicts the design package" in x for x in fp.rejected_because))
        acc = rep.acceptance()
        self.assertFalse(acc["i5_acceptance"])
        self.assertEqual(acc["backordered_selections_without_permission"], 0)
        self.assertEqual(sorted(acc["lines_without_stock_or_alternative"]),
                         ["DESK-FIX-BO", "DESK-FIX-EOL", "DESK-FIX-FPMIS", "DESK-FIX-UNK"])

    def test_backorder_only_with_client_flag(self):
        self.assertEqual(line(report(PARTS_BAD), "DESK-FIX-BO").status, "UNRESOLVED")
        bo = line(report(PARTS_BAD, allow_backorder=True), "DESK-FIX-BO")
        self.assertEqual(bo.status, "SELECTED_BACKORDER")

    def test_markdown_states_limitations(self):
        md = report(PARTS_GOOD + PARTS_BAD).to_markdown()
        self.assertIn("Verdict: **INCOMPLETE**", md)
        self.assertIn("DESK-FIX-UNK: no verified in-stock offer", md)
        self.assertIn("| Verified at |", md)


class TestBomToolSourcing(unittest.TestCase):
    def test_tool_writes_report_offline(self):
        tmp = tempfile.mkdtemp()
        try:
            proj = os.path.join(tmp, "FIX")
            os.makedirs(os.path.join(proj, "blocks"))
            os.makedirs(os.path.join(proj, "sourcing", "evidence"))
            with open(os.path.join(proj, "project.json"), "w") as f:
                json.dump({"name": "FIX"}, f)
            block = {"id": "B1", "title": "FIX", "parts": [dict(p, pins={}) for p in PARTS_GOOD]}
            with open(os.path.join(proj, "blocks", "01_FIX.json"), "w") as f:
                json.dump(block, f)
            with open(os.path.join(proj, "sourcing", "evidence", "catalogue.json"), "w") as f:
                json.dump({"records": CATALOGUE}, f)
            env = dict(os.environ, DESK_TELEMETRY="0")
            p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bom.py"), proj, "--sourcing",
                                "--qty", "10"], capture_output=True, text=True, env=env, timeout=120)
            self.assertIn(p.returncode, (0, 2), p.stdout + p.stderr)
            self.assertIn("SOURCING", p.stdout)
            self.assertTrue(os.path.isfile(os.path.join(proj, "bom.csv")))
            with open(os.path.join(proj, "sourcing_report.json")) as f:
                data = json.load(f)
            self.assertEqual(data["acceptance"]["lines_total"], 3)
            self.assertTrue(os.path.isfile(os.path.join(proj, "SOURCING_REPORT.md")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
