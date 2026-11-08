# Supplier Provider Interface & Registry Contract

## 1. Abstract Supplier Contract

Every commercial distributor adapter must subclass `SupplierProvider` (`desk/component_intelligence/suppliers/base.py`) and declare its explicit `SupplierCapabilities`:

```python
class SupplierProvider(abc.ABC):
    supplier_id: str
    name: str
    capabilities: SupplierCapabilities

    @abc.abstractmethod
    def search_components(self, query: str, filters: Optional[Dict[str, Any]] = None, limit: int = 20) -> List[SupplierOffer]:
        pass

    @abc.abstractmethod
    def get_component(self, supplier_part_number: str) -> Optional[SupplierOffer]:
        pass

    @abc.abstractmethod
    def get_offers(self, mpn: str) -> List[SupplierOffer]:
        pass
```

---

## 2. Capability Declarations

Suppliers vary in API feature sets. Capabilities are declared via typed booleans:

- `search`: Keyword and parametric catalog search.
- `product_details`: Complete single-SKU metadata lookup.
- `pricing`: Volume tier price breaks.
- `inventory`: Real-time stock counts.
- `datasheet_links`: Direct PDF datasheet URLs.
- `ordering`: Automated cart/order submission (intentionally `False` in initial phases).

---

## 3. Supplier Registry & Fault Isolation

The `SupplierRegistry` (`desk/component_intelligence/suppliers/registry.py`) provides:
- **Unique Registration**: Rejects duplicate provider IDs.
- **Dynamic Toggling**: Providers can be enabled or disabled at runtime.
- **Fault Isolation**: When querying `search_all()`, a network timeout or API error from one provider (e.g. failing distributor) is safely logged and isolated, allowing other suppliers to return valid offers without aborting the engineering session.
