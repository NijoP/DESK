# Component Specification & SI Normalization Engine

## 1. Unit Normalization

Raw component specifications come in disparate notation (e.g. `"10uF"`, `"0.1µF"`, `"100nF"`, `"10k"`, `"1MEG"`, `"1/16W"`). The `SpecificationParser` (`desk/component_intelligence/specifications/engine.py`) standardizes these into base SI units:

- **Capacitance**: Converted to Farads ($\text{F}$).
- **Resistance**: Converted to Ohms ($\Omega$).
- **Voltage**: Converted to Volts ($\text{V}$).
- **Current**: Converted to Amperes ($\text{A}$).
- **Power**: Converted to Watts ($\text{W}$), correctly handling fractions (e.g. $1/16\,\text{W} = 0.0625\,\text{W}$).

---

## 2. Specification Provenance & Extraction Methods

Every extracted specification maintains its original string and an explicit `ExtractionMethod`:
1. `DATASHEET_EXTRACTED`: Extracted directly from manufacturer PDF tables.
2. `SUPPLIER_CATALOG`: Parsed from distributor catalog parametric fields.
3. `AI_EXTRACTED`: Suggested by AI reasoning models (must be independently verified).
4. `CALCULATED`: Derived from circuit formulas (e.g. $P = I^2 R$).
5. `ASSUMED`: Default engineering rule of thumb.
