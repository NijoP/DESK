"""
Resilient LCSC API Client.
Features:
- Standard library implementation (urllib.request)
- Configurable connection and read timeouts
- Bounded retries with exponential backoff
- Credential redaction in logs
- Offline fixture fallback for deterministic testing and air-gapped environments

Keyless public route (probed 2026-11-21, no account, one request each):
- ``GET {base_url}/detail?productCode=C8545`` answers ``{"code": 200, "result": {...}}`` with
  productCode, productModel, brandNameEn, encapStandard, stockNumber, productPriceList (usdPrice),
  productCycle, isPreSale and pdfUrl. ``get_product_detail`` reads that shape.
- ``POST {base_url}/search`` answers ``{"code": 404, "msg": "The static resource is unavailable..."}``:
  there is no keyless MPN search. Without credentials, ``search_products`` resolves only LCSC
  C-numbers; MPN discovery comes from browser-agent evidence (``suppliers.evidence``).
- www.lcsc.com/robots.txt does not restrict product pages or this host; DESK still spaces requests
  by ``min_interval_s`` and caches each detail read for the life of the client.

Every item records where it came from (``source``: "fixture" or "live_api") and when
(``fetched_at``), so fixture data can never be reported as verified stock.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from desk.component_intelligence.suppliers.providers.lcsc.models import LcscProductItem

logger = logging.getLogger("desk.component_intelligence.lcsc")

# Realistic offline fixture catalog for testing without live API credentials
OFFLINE_FIXTURE_CATALOG: List[Dict[str, Any]] = [
    {
        "productCode": "C11702",
        "productModel": "0402WGF1001TCE",
        "brandNameEn": "Uni-Royal",
        "catalogName": "Chip Resistor - Surface Mount",
        "parentCatalogName": "Resistors",
        "packageDetail": "0402",
        "stockNumber": 482000,
        "productPriceList": [
            {"ladder": 1, "productPrice": 0.0031, "currency": "USD"},
            {"ladder": 100, "productPrice": 0.0022, "currency": "USD"},
            {"ladder": 1000, "productPrice": 0.0016, "currency": "USD"},
        ],
        "minPacketNumber": 100,
        "pdfUrl": "https://datasheet.lcsc.com/lcsc/1811151441_UNI-ROYAL-Uniroyal-Elec-0402WGF1001TCE_C11702.pdf",
        "productDescEn": "1kΩ ±1% 1/16W 0402 Chip Resistor",
    },
    {
        "productCode": "C347222",
        "productModel": "TPS62840DLCR",
        "brandNameEn": "Texas Instruments",
        "catalogName": "DC-DC Converters",
        "parentCatalogName": "Power Management ICs",
        "packageDetail": "VSON-8",
        "stockNumber": 12500,
        "productPriceList": [
            {"ladder": 1, "productPrice": 1.45, "currency": "USD"},
            {"ladder": 10, "productPrice": 1.15, "currency": "USD"},
            {"ladder": 100, "productPrice": 0.88, "currency": "USD"},
        ],
        "minPacketNumber": 1,
        "pdfUrl": "https://datasheet.lcsc.com/lcsc/2001151605_Texas-Instruments-TPS62840DLCR_C347222.pdf",
        "productDescEn": "1.8V to 6.5V, 750mA, 60nA ultra-low-IQ step-down converter",
    },
    {
        "productCode": "C1525",
        "productModel": "CL05B104KO5NNNC",
        "brandNameEn": "Samsung Electro-Mechanics",
        "catalogName": "Multilayer Ceramic Capacitors MLCC - SMD/SMT",
        "parentCatalogName": "Capacitors",
        "packageDetail": "0402",
        "stockNumber": 890000,
        "productPriceList": [
            {"ladder": 1, "productPrice": 0.005, "currency": "USD"},
            {"ladder": 100, "productPrice": 0.0035, "currency": "USD"},
            {"ladder": 1000, "productPrice": 0.0024, "currency": "USD"},
        ],
        "minPacketNumber": 100,
        "pdfUrl": "https://datasheet.lcsc.com/lcsc/1811081512_Samsung-Electro-Mechanics-CL05B104KO5NNNC_C1525.pdf",
        "productDescEn": "100nF (0.1uF) 16V X7R ±10% 0402 MLCC",
    },
    {
        "productCode": "C8405",
        "productModel": "BSS138",
        "brandNameEn": "onsemi",
        "catalogName": "MOSFETs",
        "parentCatalogName": "Transistors",
        "packageDetail": "SOT-23",
        "stockNumber": 45000,
        "productPriceList": [
            {"ladder": 1, "productPrice": 0.08, "currency": "USD"},
            {"ladder": 50, "productPrice": 0.055, "currency": "USD"},
            {"ladder": 500, "productPrice": 0.038, "currency": "USD"},
        ],
        "minPacketNumber": 1,
        "pdfUrl": "https://datasheet.lcsc.com/lcsc/1810311210_ON-Semiconductor-BSS138_C8405.pdf",
        "productDescEn": "50V 220mA 3.5Ω N-Channel SOT-23 MOSFET",
    },
    {
        "productCode": "C52994",
        "productModel": "STM32F401CCU6",
        "brandNameEn": "STMicroelectronics",
        "catalogName": "Microcontroller Units (MCUs/MPUs/SOCs)",
        "parentCatalogName": "Embedded Processors & Controllers",
        "packageDetail": "UFQFPN-48",
        "stockNumber": 8200,
        "productPriceList": [
            {"ladder": 1, "productPrice": 3.85, "currency": "USD"},
            {"ladder": 10, "productPrice": 3.20, "currency": "USD"},
            {"ladder": 100, "productPrice": 2.75, "currency": "USD"},
        ],
        "minPacketNumber": 1,
        "pdfUrl": "https://datasheet.lcsc.com/lcsc/1811131510_STMicroelectronics-STM32F401CCU6_C52994.pdf",
        "productDescEn": "ARM Cortex-M4 84MHz 256KB Flash 64KB SRAM UFQFPN-48 MCU",
    },
]


class LcscApiClient:
    """Client for LCSC catalog queries with offline fixture fallback."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: str = "https://wmsc.lcsc.com/ftps/wm/product",
        connection_timeout_s: float = 5.0,
        read_timeout_s: float = 10.0,
        max_retries: int = 3,
        use_offline_fixtures: Optional[bool] = None,
        min_interval_s: float = 1.0,
    ) -> None:
        from desk import config as deskcfg
        self.client_id = client_id or deskcfg.get("LCSC_CLIENT_ID")
        self.client_secret = client_secret or deskcfg.get("LCSC_CLIENT_SECRET")
        self.base_url = base_url.rstrip("/")
        self.conn_timeout = connection_timeout_s
        self.read_timeout = read_timeout_s
        self.max_retries = max_retries
        self.min_interval_s = min_interval_s
        self._last_request_at = 0.0
        self._detail_cache: Dict[str, Optional[LcscProductItem]] = {}
        self.limitations: List[str] = []

        # Automatically use offline fixtures if credentials are missing
        if use_offline_fixtures is not None:
            self.use_offline_fixtures = use_offline_fixtures
        else:
            self.use_offline_fixtures = not bool(self.client_id and self.client_secret)

    def search_products(self, query: str, limit: int = 20) -> List[LcscProductItem]:
        """Searches products by keyword, MPN, or LCSC product code."""
        if self.use_offline_fixtures:
            return self._search_fixtures(query, limit=limit)

        q = query.strip().upper()
        if re.fullmatch(r"C\d+", q):
            item = self.get_product_detail(q)
            return [item] if item else []
        if not self.has_credentials:
            msg = (f"LCSC keyless access has no MPN search (the public search route answers 404); "
                   f"'{query}' needs an LCSC C-number or browser-agent evidence.")
            if msg not in self.limitations:
                self.limitations.append(msg)
            return []

        url = f"{self.base_url}/search"
        payload = {"searchKey": query, "pageSize": limit}
        data = self._request("POST", url, body=payload)
        items = data.get("resultList", [])
        return [self._stamp(LcscProductItem.from_dict(item), "live_api") for item in items]

    def get_product_detail(self, product_code: str) -> Optional[LcscProductItem]:
        """Retrieves single product details by LCSC product code (e.g., C11702)."""
        clean_code = product_code.strip().upper()
        if self.use_offline_fixtures:
            for item in OFFLINE_FIXTURE_CATALOG:
                if item["productCode"].upper() == clean_code:
                    return self._stamp(LcscProductItem.from_dict(item), "fixture")
            return None
        if clean_code in self._detail_cache:
            return self._detail_cache[clean_code]

        url = f"{self.base_url}/detail?productCode={urllib.parse.quote(clean_code)}"
        try:
            data = self._request("GET", url)
        except Exception as e:
            logger.warning("Failed to fetch LCSC detail for %s: %s", clean_code, e)
            self.limitations.append(f"LCSC {clean_code}: detail read failed ({e}); stock not verified.")
            return None
        item = None
        record = self.unwrap_detail(data)
        if record is not None:
            item = self._stamp(LcscProductItem.from_dict(record), "live_api")
        else:
            self.limitations.append(f"LCSC {clean_code}: no product record in the detail response.")
        self._detail_cache[clean_code] = item
        return item

    @property
    def has_credentials(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @staticmethod
    def unwrap_detail(data: Any) -> Optional[Dict[str, Any]]:
        """Return the product record from a detail response (wrapped ``result`` or bare)."""
        if not isinstance(data, dict):
            return None
        if "productCode" in data:
            return data
        inner = data.get("result")
        if isinstance(inner, dict) and inner.get("productCode"):
            return inner
        return None

    @staticmethod
    def _stamp(item: LcscProductItem, source: str) -> LcscProductItem:
        item.source = source
        item.fetched_at = time.time()
        return item

    def _search_fixtures(self, query: str, limit: int = 20) -> List[LcscProductItem]:
        """Performs case-insensitive substring search across offline fixtures."""
        q_upper = query.strip().upper()
        matches = []
        for raw in OFFLINE_FIXTURE_CATALOG:
            code = raw.get("productCode", "").upper()
            model = raw.get("productModel", "").upper()
            desc = raw.get("productDescEn", "").upper()
            brand = raw.get("brandNameEn", "").upper()

            if q_upper in code or q_upper in model or q_upper in desc or q_upper in brand:
                matches.append(self._stamp(LcscProductItem.from_dict(raw), "fixture"))
                if len(matches) >= limit:
                    break
        return matches

    def _request(self, method: str, url: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes an HTTP request with bounded retries and exponential backoff."""
        headers = {
            "User-Agent": "DESK-Component-Intelligence/1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.client_id and self.client_secret:
            headers["X-Client-Id"] = self.client_id
            headers["X-Client-Secret"] = self.client_secret

        encoded_data = json.dumps(body).encode("utf-8") if body else None

        for attempt in range(1, self.max_retries + 1):
            wait = self.min_interval_s - (time.time() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.time()
            req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.read_timeout) as resp:
                    raw_text = resp.read().decode("utf-8", errors="replace")
                    return json.loads(raw_text)
            except urllib.error.HTTPError as e:
                # Fatal auth or client error: do not retry
                if e.code in (400, 401, 403, 404):
                    raise RuntimeError(f"LCSC API client error {e.code}: {e.reason}") from e
                if attempt == self.max_retries:
                    raise
                time.sleep(0.5 * (2 ** (attempt - 1)))
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == self.max_retries:
                    raise
                time.sleep(0.5 * (2 ** (attempt - 1)))

        return {}
