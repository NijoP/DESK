"""DESK simulation (optional plugin): simulator interface, SPICE netlist generation, result checks.

DESK core never depends on a simulator. This package imports no engine at load time. The ngspice adapter
(desk.simulation.ngspice) is imported only when the "ngspice" engine is requested, and with ngspice absent
every module here still imports and every non-run feature works: netlist generation, model store, parsing
recorded output, verification and export.

    from desk.simulation import base, netlist, verify
    circuit = netlist.build_circuit(block, sim_spec, models.ModelStore(path))
    result = base.get("ngspice").run(circuit)
    report = verify.verify(result, expectations, circuit.node_map)

CLI: python tools/desk.py sim engines|netlist|run|models  (docs/simulation/README.md).

Simulation alone does not prove a PCB is electrically or thermally safe (base.SAFETY_NOTICE).
"""
from desk.simulation.base import SAFETY_NOTICE  # noqa: F401
