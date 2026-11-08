# EDA Library Provider Layer Integration

## 1. Domain Decoupling

The EDA Library Provider Layer (`desk/component_intelligence/eda/`) guarantees that CAD assets (symbols, footprints, 3D models) remain completely independent of commercial suppliers. A component can be sourced from LCSC, Mouser, or DigiKey while utilizing the same verified KiCad or EasyEDA footprint.

---

## 2. Supported EDA Providers

### 1. Local Offline Provider (`desk/component_intelligence/eda/providers/local.py`)
- Reads and indexes existing `library/devices.json` and `library/pins/*.json`.
- Operates 100% offline with zero network or bridge dependencies.
- Serves verified symbol pinouts and package footprints.

### 2. EasyEDA Safe Adapter (`desk/component_intelligence/eda/providers/easyeda.py`)
- Reuses existing `desk.bridge` architecture.
- Enforces non-negotiable safety rules: **NO live board mutations, document switching, or unapproved bridge operations**.

### 3. KiCad Library Provider (Extensible)
- Formats and exports `.kicad_sym` and `.kicad_mod` assets for open-source EDA workflows.
