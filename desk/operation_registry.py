"""
DESK Deterministic Operation Registry.

Defines a machine-readable, schema-validated registry for all authoritative
engineering and runtime operations, with explicit replay safety, resource tiers,
and deterministic execution contracts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class ReplayPolicy(str, enum.Enum):
    """Replay safety classifications for tasks and operations."""
    SAFE_READ = "SAFE_READ"
    SAFE_IDEMPOTENT = "SAFE_IDEMPOTENT"
    UNSAFE_MUTATION = "UNSAFE_MUTATION"
    RECONCILE_BEFORE_RETRY = "RECONCILE_BEFORE_RETRY"


class ResourceClass(str, enum.Enum):
    """Resource consumption class for scheduler admission."""
    LIGHT = "LIGHT"        # Memory < 10MB, CPU < 10ms
    MEDIUM = "MEDIUM"      # Memory < 100MB, CPU < 500ms
    HEAVY = "HEAVY"        # Memory > 100MB, CPU > 500ms


@dataclass
class OperationDescriptor:
    """Descriptor for a registered engineering operation."""
    operation_id: str
    name: str
    description: str
    schema_version: str = "1.0.0"
    deterministic: bool = True
    resource_class: ResourceClass = ResourceClass.LIGHT
    side_effect: bool = False
    replay_policy: ReplayPolicy = ReplayPolicy.SAFE_READ
    pipeline_stage: str = "M0"
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[..., Any]] = None

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        """Validates provided inputs against declared schema keys and types."""
        errors: List[str] = []
        for required_key, expected_type in self.input_schema.items():
            if required_key not in inputs:
                errors.append(f"Missing required input parameter: '{required_key}'")
            elif expected_type and not isinstance(inputs[required_key], expected_type):
                errors.append(
                    f"Parameter '{required_key}' expected type {expected_type.__name__}, "
                    f"got {type(inputs[required_key]).__name__}"
                )
        return errors


def calc_trace_width(current_a: float, temp_rise_c: float = 10.0, copper_oz: float = 1.0,
                     is_inner: bool = False) -> Dict[str, Any]:
    """Authoritative trace width via desk.ipc (IPC-2221 power law). Unknown or non-positive currents are
    refused instead of being sized (fail-closed, roadmap H-02). Returns mils and millimetres."""
    from desk import ipc
    if current_a is None or float(current_a) <= 0.0:
        return {"refused": True, "error": "current_a must be > 0 A; an unknown current is never sized by assumption",
                "current_a": current_a}
    width_mil = ipc.trace_width_mil(float(current_a), is_inner=bool(is_inner), copper_oz=float(copper_oz),
                                    temp_rise_c=float(temp_rise_c))
    return {
        "trace_width_mil": round(width_mil, 2),
        "trace_width_mm": round(width_mil * 0.0254, 4),
        "current_a": current_a,
        "temp_rise_c": temp_rise_c,
        "copper_oz": copper_oz,
        "is_inner": bool(is_inner),
        "reference": "IPC-2221 power law, k=0.048 external / 0.024 internal, b=0.44, c=0.725 (desk.ipc)",
        "verified_against_standard": bool(getattr(ipc, "verified_against_standard", False)),
    }


class OperationRegistry:
    """Registry maintaining all available operations across DESK pipelines."""

    def __init__(self) -> None:
        self._operations: Dict[str, OperationDescriptor] = {}
        self._register_default_operations()

    def register(self, op: OperationDescriptor) -> None:
        """Registers a new operation descriptor."""
        self._operations[op.operation_id] = op

    def get(self, operation_id: str) -> Optional[OperationDescriptor]:
        """Retrieves an operation descriptor by its ID."""
        return self._operations.get(operation_id)

    def list_operations(self, stage: Optional[str] = None) -> List[OperationDescriptor]:
        """Lists operations, optionally filtered by pipeline stage."""
        if stage is None:
            return list(self._operations.values())
        return [op for op in self._operations.values() if op.pipeline_stage == stage]

    def execute(self, operation_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes a registered operation with input validation and execution tracking.
        Raises ValueError if validation fails or handler is missing.
        """
        op = self.get(operation_id)
        if op is None:
            raise KeyError(f"Operation '{operation_id}' not found in registry.")

        validation_errors = op.validate_inputs(inputs)
        if validation_errors:
            raise ValueError(f"Input validation failed for '{operation_id}': {', '.join(validation_errors)}")

        if op.handler is None:
            raise NotImplementedError(f"No executable handler registered for operation '{operation_id}'.")

        result = op.handler(**inputs)
        return {
            "operation_id": operation_id,
            "status": "SUCCESS",
            "replay_policy": op.replay_policy.value,
            "pipeline_stage": op.pipeline_stage,
            "result": result,
        }

    def _register_default_operations(self) -> None:
        """Registers the core standard operations across M1–M6 and Runtime."""
        # 1. Trace Width Calculation (M3) — delegates to desk.ipc, the single authoritative formula module.
        self.register(OperationDescriptor(
            operation_id="calc_trace_width",
            name="Calculate Trace Width",
            description="IPC-2221 power-law trace width (desk.ipc.trace_width_mil) from current, temperature rise, copper weight and layer; refuses unknown (<= 0 A) currents.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M3",
            input_schema={"current_a": (int, float), "temp_rise_c": (int, float)},
            handler=calc_trace_width,
        ))

        # 2. DRC Clearance Check (M5)
        self.register(OperationDescriptor(
            operation_id="verify_clearance",
            name="Verify Clearance",
            description="Checks distance between two coordinate points against min required clearance.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M5",
            input_schema={"p1": (tuple, list), "p2": (tuple, list), "required_mm": (int, float)},
            handler=lambda p1, p2, required_mm: {
                "distance_mm": round(((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5, 4),
                "required_mm": required_mm,
                "passed": (((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5) >= required_mm,
            }
        ))

        # 3. Create Copper Zone (M4)
        self.register(OperationDescriptor(
            operation_id="create_copper_zone",
            name="Create Copper Zone",
            description="Defines a ground or power copper pour polygon with net and layer binding.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.MEDIUM,
            side_effect=True,
            replay_policy=ReplayPolicy.SAFE_IDEMPOTENT,
            pipeline_stage="M4",
            input_schema={"net_name": str, "layer": str, "points": (list, tuple)},
            handler=lambda net_name, layer, points: {
                "zone_id": f"zone_{layer}_{net_name}_{len(points)}",
                "net_name": net_name,
                "layer": layer,
                "vertex_count": len(points),
                "status": "CREATED",
            }
        ))

        # 4. Checkpoint Creation (Runtime)
        self.register(OperationDescriptor(
            operation_id="create_checkpoint",
            name="Create Checkpoint",
            description="Takes an immutable snapshot checkpoint of the current design state.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.MEDIUM,
            side_effect=True,
            replay_policy=ReplayPolicy.SAFE_IDEMPOTENT,
            pipeline_stage="RUNTIME",
            input_schema={"stage": str, "snapshot_data": dict},
            handler=lambda stage, snapshot_data: {
                "checkpoint_id": f"chk_{stage}_{len(str(snapshot_data))}",
                "stage": stage,
                "status": "RECORDED",
            }
        ))

        # 5. Component Discovery (M1)
        self.register(OperationDescriptor(
            operation_id="find_component",
            name="Find Component",
            description="Discovers electronic components across local canonical database and active suppliers.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M1",
            input_schema={"query": str},
            handler=lambda query, limit=10: __import__("desk.component_intelligence.api", fromlist=["find_component"]).find_component(query, limit=limit)
        ))

        # 6. Component Verification (M1)
        self.register(OperationDescriptor(
            operation_id="verify_component",
            name="Verify Component",
            description="Executes fail-closed V1-V4 verification (Identity, Electrical, Physical, Procurement).",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M1",
            input_schema={"desk_id": str},
            handler=lambda desk_id, operating_rail_v=0.0, operating_current_a=0.0: __import__("desk.component_intelligence.api", fromlist=["verify_component"]).verify_component(
                desk_id, operating_rail_v=operating_rail_v, operating_current_a=operating_current_a
            )
        ))

        # 7. Procurement BOM Optimization (M1)
        self.register(OperationDescriptor(
            operation_id="build_procurement_bom",
            name="Build Procurement BOM",
            description="Optimizes BOM sourcing, pricing tiers, and stock availability across suppliers.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.MEDIUM,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M1",
            input_schema={"parts": list},
            handler=lambda parts, batch_quantity=1: __import__("desk.component_intelligence.api", fromlist=["build_procurement_bom"]).build_procurement_bom(
                parts, batch_quantity=batch_quantity
            )
        ))

        # 8. Multi-Supplier Catalog Search (M1)
        self.register(OperationDescriptor(
            operation_id="supplier_search",
            name="Search Supplier Catalogs",
            description="Queries configured commercial distributor catalogs (LCSC, Mouser) for matching components.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M1",
            input_schema={"query": str},
            handler=lambda query, limit=10: [
                o.to_dict() for o in __import__("desk.component_intelligence.api", fromlist=["get_supplier_registry"]).get_supplier_registry().search_all(query, limit_per_supplier=limit)
            ]
        ))

        # 9. Manufacturing & PCBA Quotation (M6)
        self.register(OperationDescriptor(
            operation_id="manufacturing_quote",
            name="Calculate Manufacturing Quote",
            description="Calculates realistic JLCPCB PCB fabrication and PCBA SMT assembly costs with DFM verification.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M6",
            input_schema={"width_mm": (int, float), "height_mm": (int, float)},
            handler=lambda width_mm, height_mm, layer_count=2, quantity=5, bom_components=None: __import__("desk.manufacturing.jlcpcb", fromlist=["JLCPCBClient"]).JLCPCBClient(use_mock=True).get_quote(
                width_mm=width_mm,
                height_mm=height_mm,
                layer_count=layer_count,
                quantity=quantity,
                bom_components=bom_components,
            )
        ))

        # 10. EDA Project Offline Inspection (M2)
        self.register(OperationDescriptor(
            operation_id="eda_inspect_project",
            name="Inspect EDA Project",
            description="Safely inspects project files, safety locks, and structure without mutating state.",
            schema_version="1.0.0",
            deterministic=True,
            resource_class=ResourceClass.LIGHT,
            side_effect=False,
            replay_policy=ReplayPolicy.SAFE_READ,
            pipeline_stage="M2",
            input_schema={"project_path": str},
            handler=lambda project_path: __import__("desk.eda.easyeda_pro", fromlist=["get_easyeda_manager"]).get_easyeda_manager().inspect_project_offline(project_path)
        ))


# Global singleton registry instance
_GLOBAL_REGISTRY: Optional[OperationRegistry] = None


def get_operation_registry() -> OperationRegistry:
    """Returns or initializes the singleton operation registry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = OperationRegistry()
    return _GLOBAL_REGISTRY
