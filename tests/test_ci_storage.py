"""
Unit tests for SQLite Database, Migrations, Foreign Keys, and Repository.
"""

import shutil
import tempfile
import unittest

from desk.component_intelligence.identity.models import CanonicalComponent, DatasheetReference
from desk.component_intelligence.storage.database import DatabaseManager
from desk.component_intelligence.storage.repository import ComponentRepository
from desk.component_intelligence.suppliers.models import PriceBreak, SupplierOffer


class TestComponentStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="desk_test_ci_db_")
        db_file = f"{self.temp_dir}/test_canonical.db"
        self.db = DatabaseManager(db_file)
        self.repo = ComponentRepository(self.db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_schema_migration_v1(self):
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT MAX(version) FROM schema_version;").fetchone()
            self.assertEqual(row[0], 1)

    def test_component_crud_and_datasheets(self):
        comp = CanonicalComponent(
            desk_id="comp_test_123",
            manufacturer_name="Texas Instruments",
            normalized_manufacturer="Texas Instruments",
            mpn="TPS62840DLCR",
            normalized_mpn="TPS62840DLCR",
            category="Power Management",
            description="Buck converter",
            package="VSON-8",
            datasheets=[
                DatasheetReference(id="ds_1", url="https://ti.com/ds1.pdf", title="TPS62840 Datasheet")
            ],
        )
        self.repo.upsert_component(comp)

        fetched = self.repo.get_component("comp_test_123")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.mpn, "TPS62840DLCR")
        self.assertEqual(len(fetched.datasheets), 1)
        self.assertEqual(fetched.datasheets[0].url, "https://ti.com/ds1.pdf")

    def test_search_and_find_by_mpn(self):
        comp = CanonicalComponent(
            desk_id="comp_stm32",
            manufacturer_name="STMicroelectronics",
            normalized_manufacturer="STMicroelectronics",
            mpn="STM32F401CCU6",
            normalized_mpn="STM32F401CCU6",
            category="Microcontrollers",
            description="32-bit ARM MCU",
            package="UFQFPN-48",
        )
        self.repo.upsert_component(comp)

        by_mpn = self.repo.find_by_mpn("stm32f401ccu6")
        self.assertEqual(len(by_mpn), 1)
        self.assertEqual(by_mpn[0].desk_id, "comp_stm32")

        search_res = self.repo.search("ARM MCU")
        self.assertEqual(len(search_res), 1)

    def test_supplier_offers_and_pricing_tiers(self):
        # Insert parent component first (foreign key integrity)
        comp = CanonicalComponent(
            desk_id="comp_c1",
            manufacturer_name="Uni-Royal",
            normalized_manufacturer="Uni-Royal",
            mpn="0402WGF1001TCE",
            normalized_mpn="0402WGF1001TCE",
            category="Resistors",
            description="1k resistor",
            package="0402",
        )
        self.repo.upsert_component(comp)

        offer = SupplierOffer(
            supplier_id="lcsc",
            supplier_name="LCSC Electronics",
            sku="C11702",
            canonical_desk_id="comp_c1",
            manufacturer_name="Uni-Royal",
            mpn="0402WGF1001TCE",
            stock=10000,
            unit_price=0.003,
            price_breaks=[
                PriceBreak(quantity=1, unit_price=0.003),
                PriceBreak(quantity=100, unit_price=0.002),
            ],
        )
        self.repo.upsert_supplier_offer(offer)

        offers = self.repo.get_offers_for_component("comp_c1")
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].sku, "C11702")
        self.assertEqual(len(offers[0].price_breaks), 2)
        self.assertEqual(offers[0].get_price_for_quantity(150), 0.002)


if __name__ == "__main__":
    unittest.main()
