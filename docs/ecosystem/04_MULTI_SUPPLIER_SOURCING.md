# Domain B: Multi-Supplier Sourcing & Specialized BOM Generation

**Author:** Principal Component Intelligence & Sourcing Lead  
**Scope:** Distributor Abstraction, Mouser Provider, JLCPCB PCBA BOM & CPL Exports  
**Repository:** https://github.com/NijoP/DESK  
**Status:** Canonical Reference

---

## 1. Architectural Philosophy: Canonical vs. Commercial Separation

A central tenet of DESK's architecture is the strict separation between:
1. **Canonical Component Identity**: The intrinsic electrical, physical, and functional attributes of a component (MPN, Manufacturer, Normalized Package, Voltage, Current, Tolerance).
2. **Supplier Offers**: Commercial distributor listings (LCSC, Mouser, DigiKey) that fluctuate over time (SKU, Stock, Tiered Pricing, MOQ, Packaging).
3. **Manufacturing SMT Part**: The assembly profile specific to an assembly house (e.g. JLCPCB Basic vs. Extended parts, Feeder Setup fees).

Neither the PCB schematic nor the layout binds directly to ephemeral distributor data.

---

## 2. Supported Supplier Adapters

DESK features an extensible provider registry:
- **LCSC (`LcscSupplierProvider`)**: Primary commercial distributor adapter. Provides direct mapping to LCSC part numbers (`Cxxxxx`), real-time stock verification, and volume pricing.
- **Mouser Electronics (`MouserSupplierProvider`)**: Extensible secondary provider. Offers access to Mouser's extensive semiconductor and passive portfolio with volume price breaks and stock tracking.
- **Offline Mock Fallbacks**: Guaranteed determinism during offline builds and tests without requiring external internet or API tokens.

---

## 3. Specialized BOM & CPL Pick-and-Place Generation

In `desk.component_intelligence.procurement.bom_export`:

### 3.1 JLCPCB PCBA BOM (`export_jlcpcb_bom`)
Generates the exact 4-column CSV expected by the JLCPCB SMT upload portal:
```csv
Comment,Designator,Footprint,LCSC Part #
GRM155R71C104KA88D,"C1,C2",0402,C15849
STM32F405RGT6,U1,LQFP-64,
```

### 3.2 JLCPCB Pick and Place / CPL (`export_jlcpcb_cpl`)
Generates Centroid data with automatic rotation alignment via `JLCPCBPCBACatalog.normalize_rotation()`:
```csv
Designator,Val,Package,Mid X,Mid Y,Rotation,Layer
U1,AMS1117,SOT-223,12.5,25.0,180.0,Top
D1,1N4148,SOD-123,15.0,30.0,270.0,Top
C1,100nF,0402,5.0,10.0,0.0,Bottom
```

### 3.3 Direct LCSC Cart BOM (`export_lcsc_bom`)
Generates direct cart upload CSV for bulk order placement at LCSC:
```csv
Item,Quantity,LCSC Part Number,Manufacturer Part,Customer Reference
1,20,C15849,GRM155R71C104KA88D,C1 C2
```
