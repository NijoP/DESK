"""Priority-Based Autonomous PCB Routing & Recovery Engine V2.
Usage: python tools/route.py projects/<product> [--mode BALANCED] [--passes 30] [--recovery] [--dry] [--force]

--force   Launch the engine even when the pre-flight pin-escape congestion veto (> 1.0) trips.

Supported Modes:
  FAST      - Fast execution, 12 passes, bounded optimization
  BALANCED  - Production default, 30 passes, full escape and congestion planning
  PRECISION - Demanding boards, 60 passes, extensive optimization

Order of Execution:
1. Priority Scheduling: Stages 1 (GND) through 6 (Remaining) with dynamic constrainedness
2. Recovery Rip-up: If --recovery, selectively deletes conflicting primitives from state/recovery_plan.json
3. DSN Export & Tuning: AST-based tuning of boundaries, grid resolution, and fine-pitch clearances
4. Autorouting: Supervised Freerouting execution with headless watchdog and stagnation detection
5. SES Import: Imports routed copper tracks and vias back into EasyEDA Pro
6. Post-Routing Power Widening: Clearance-safe widening of heavy copper power trunks (VBAT, VSYS)
7. Physical Connectivity Verification: Pad-to-pad physical continuity check across all populated nets
8. Routing Audit: Logs attempt metrics to state/route/routing_attempt.json and LEDGER.jsonl
"""
import sys
from _common import S  # noqa: F401  (telemetry hook: records this run in .desk_learn/runs.jsonl)
from desk.routing.pipeline import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
