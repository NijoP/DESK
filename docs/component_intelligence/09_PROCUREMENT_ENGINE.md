# Procurement Engine & Multi-Supplier BOM Optimization

## 1. Multi-Supplier Sourcing Strategy

The Procurement Engine (`desk/component_intelligence/procurement/engine.py`) takes raw schematic components and batch production quantities, evaluates commercial distributor offers, and produces optimized procurement BOMs:

1. **Volume Tier Optimization**: Evaluates `offer.get_price_for_quantity(total_required)` across all price ladders.
2. **Stock Shortage Detection**: Evaluates whether active warehouse stock meets the production batch requirement.
3. **Currency Standardization**: Normalizes line item pricing to standard currency.
4. **BOM Export**: Outputs standard CSV format for contract manufacturers and purchasing teams.

---

## 2. Alternatives & Substitution Invariants

When primary components face shortages or extended lead times:
- The `ComponentAlternativesEngine` evaluates candidate replacements.
- **Safety Invariant**: Replacement components must satisfy absolute maximum ratings ($V_{\text{rating}} \ge V_{\text{orig}}$, $I_{\text{rating}} \ge I_{\text{orig}}$) and footprint compatibility.
- Substitutions are never applied automatically; they are presented as scored recommendations to the engineer.
