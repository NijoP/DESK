"""Specialized BOM and CPL Export Adapters for JLCPCB and LCSC.

Generates production-ready fabrication files:
- JLCPCB PCBA BOM (Comment, Designator, Footprint, LCSC Part #)
- JLCPCB Pick and Place / Centroid CPL (Designator, Val, Package, Mid X, Mid Y, Rotation, Layer)
  with automated rotation offset alignment.
- LCSC Sourcing BOM (Quantity, LCSC Part Number, MPN, Customer Reference).
"""

from __future__ import annotations
import csv
from typing import List, Dict, Any, Optional
from desk.component_intelligence.procurement.engine import ProcurementBOMReport
from desk.manufacturing.jlcpcb.pcba_catalog import JLCPCBPCBACatalog


def export_jlcpcb_bom(report: Any, file_path: str) -> None:
    """Exports BOM formatted for JLCPCB SMT Assembly upload."""
    line_items = report.get("line_items", []) if isinstance(report, dict) else getattr(report, "line_items", [])
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for item in line_items:
            if isinstance(item, dict):
                selected_supp = item.get("supplier") or item.get("selected_supplier", "")
                lcsc_sku = item.get("sku") or item.get("selected_sku", "") if selected_supp.lower() == "lcsc" else ""
                comment = item.get("mpn", "")
                des = item.get("designators", "")
                if isinstance(des, list):
                    designators = ",".join(sorted(des))
                else:
                    designators = str(des).replace(" ", ",")
                footprint = item.get("package", "")
            else:
                lcsc_sku = item.selected_sku if item.selected_supplier.lower() == "lcsc" else ""
                comment = item.mpn
                designators = ",".join(sorted(item.designators))
                footprint = item.package
            writer.writerow([comment, designators, footprint, lcsc_sku])


def export_jlcpcb_cpl(placements: List[Dict[str, Any]], file_path: str) -> None:
    """Exports Pick and Place (Centroid / CPL) file formatted for JLCPCB SMT machines.
    
    Automatically aligns CAD rotation angles to JLCPCB feeder standards.
    """
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"])
        for p in placements:
            des = p.get("designator") or p.get("id") or ""
            val = p.get("val") or p.get("value") or p.get("mpn") or ""
            pkg = p.get("package") or p.get("footprint") or ""
            x = round(float(p.get("x") or p.get("mid_x") or 0.0), 3)
            y = round(float(p.get("y") or p.get("mid_y") or 0.0), 3)
            cad_rot = float(p.get("rotation") or 0.0)
            layer = p.get("layer") or "Top"
            if isinstance(layer, int):
                layer = "Top" if layer == 1 else "Bottom"

            # Apply deterministic JLCPCB rotation correction
            norm_rot = JLCPCBPCBACatalog.normalize_rotation(cad_rot, pkg)

            writer.writerow([des, val, pkg, x, y, norm_rot, layer])


def export_lcsc_bom(report: Any, file_path: str) -> None:
    """Exports direct cart upload BOM for LCSC distributor order."""
    line_items = report.get("line_items", []) if isinstance(report, dict) else getattr(report, "line_items", [])
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Item", "Quantity", "LCSC Part Number", "Manufacturer Part", "Customer Reference"])
        for idx, item in enumerate(line_items, start=1):
            if isinstance(item, dict):
                selected_supp = item.get("supplier") or item.get("selected_supplier", "")
                lcsc_pn = item.get("sku") or item.get("selected_sku", "") if selected_supp.lower() == "lcsc" else ""
                qty = item.get("quantity") or item.get("required_quantity", 1)
                mpn = item.get("mpn", "")
                des = item.get("designators", "")
                refs = " ".join(sorted(des)) if isinstance(des, list) else str(des)
            else:
                lcsc_pn = item.selected_sku if item.selected_supplier.lower() == "lcsc" else ""
                qty = item.required_quantity
                mpn = item.mpn
                refs = " ".join(sorted(item.designators))
            writer.writerow([idx, qty, lcsc_pn, mpn, refs])
