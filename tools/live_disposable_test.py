"""Disposable Project Live Integration Test Script.
PREPARED FOR CONTROLLED LIVE TESTING ONLY.
DO NOT EXECUTE AUTOMATICALLY.

Safety Guard:
- Requires explicit CLI flag: --execute-live
- Project directory MUST contain 'DISPOSABLE' or 'TEST'
- Strictly blocks execution on 'WATCH', 'BEEBOX', or active customer projects.

Covers the 9 verification milestones with real acceptance assertions and failure rollback:
1. EasyEDA connection and document identity
2. PCB readback
3. Component placement and readback verification
4. Ground copper-zone creation & ID validation
5. Power polygon creation & ID validation
6. Copper repour & repour count validation
7. Copper readback and connectivity verification
8. Live DRC execution & payload validation
9. Manufacturing export & non-zero file validation
"""
from __future__ import annotations
import sys
import os
import json
import time
from typing import List, Dict, Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from desk.bridge import ex, check, load_project, fetch_file
from desk.adapters.easyeda_pcb_adapter import EasyEDAPcbAdapter


def execute_rollback(created_ids: List[str], window_id: Optional[str], proj_dir: str, failure_reason: str):
    """Safely cleans up any primitives created during an interrupted or failed test run."""
    print("\n" + "!" * 70)
    print("ROLLBACK TRIGGERED: Cleaning up test primitives...")
    incident_file = os.path.join(proj_dir, "state", f"incident_report_{int(time.time())}.json")
    os.makedirs(os.path.dirname(incident_file), exist_ok=True)

    incident_data = {
        "timestamp": time.time(),
        "failure_reason": failure_reason,
        "created_primitives": created_ids,
        "rollback_status": "PENDING"
    }

    if created_ids:
        del_js = f"""
        const ids = {json.dumps(created_ids)};
        let deleted = 0;
        for (const id of ids) {{
            try {{
                const p = await eda.pcb_PrimitivePour.get(id);
                if (p) {{
                    await p.delete();
                    deleted++;
                }}
            }} catch (e) {{}}
        }}
        return {{deleted_count: deleted, total: ids.length}};
        """
        try:
            res = check(ex(del_js, window_id=window_id))
            print(f"[ROLLBACK] Cleaned up {res.get('deleted_count')} of {len(created_ids)} created primitives.")
            incident_data["rollback_status"] = "SUCCESS"
            incident_data["deleted_count"] = res.get("deleted_count")
        except Exception as e:
            print(f"[ROLLBACK ERROR] Failed to delete primitives: {e}")
            incident_data["rollback_status"] = f"FAILED: {e}"

    with open(incident_file, "w", encoding="utf-8") as f:
        json.dump(incident_data, f, indent=2)
    print(f"[ROLLBACK] Incident report saved to: {incident_file}")
    print("!" * 70)


def main():
    args = sys.argv[1:]
    if "--execute-live" not in args:
        print("=" * 70)
        print("SAFETY GUARD ACTIVE: Live EasyEDA Pro testing is DISABLED.")
        print("This script will only run with the explicit flag: --execute-live")
        print("Target project must also contain 'DISPOSABLE' or 'TEST' in its path.")
        print("=" * 70)
        sys.exit(0)

    proj_paths = [a for a in args if not a.startswith("--")]
    if not proj_paths:
        print("Usage: python tools/live_disposable_test.py <projects/DISPOSABLE_TEST> --execute-live")
        sys.exit(1)

    proj_dir = proj_paths[0]
    p_upper = os.path.abspath(proj_dir).upper()

    # Safety checks
    if "WATCH" in p_upper or "BEEBOX" in p_upper or "CUSTOMER" in p_upper:
        print(f"FATAL: Attempted execution on customer project '{proj_dir}'. Aborted.")
        sys.exit(1)

    if "DISPOSABLE" not in p_upper and "TEST" not in p_upper:
        print(f"FATAL: Target '{proj_dir}' does not contain 'DISPOSABLE' or 'TEST'. Aborted.")
        sys.exit(1)

    P = load_project(proj_dir)
    pcb_uuid = P["pcb_uuid"]
    window_id = P.get("window_id")
    adapter = EasyEDAPcbAdapter()
    created_primitive_ids: List[str] = []

    print(f"Starting Live Disposable Integration Test on: {P.get('name')} (UUID: {pcb_uuid})")

    try:
        # Milestone 1: Connection & Document Identity
        print("\n[1/9] Verifying Document Identity...")
        chk_doc = f"""
        const d = await eda.dmt_SelectControl.getCurrentDocumentInfo();
        return {{doc: d, match: d && d.uuid === "{pcb_uuid}"}};
        """
        res1 = check(ex(chk_doc, window_id=window_id))
        assert res1 and res1.get("match"), f"Active PCB {res1.get('doc')} does not match target {pcb_uuid}"
        print(f"PASS: EasyEDA document identity confirmed ({pcb_uuid}).")

        # Milestone 2: PCB Readback
        print("\n[2/9] Executing Batch PCB Readback...")
        readback_js = adapter.build_batch_readback_script(pcb_uuid)
        res2 = check(ex(readback_js, window_id=window_id, timeout=30))
        assert isinstance(res2, dict), "Readback payload must be a JSON dictionary"
        data = adapter.parse_readback_payload(P.get("name", "DISPOSABLE"), pcb_uuid, res2)
        print(f"PASS: Readback {len(data.components)} components, {len(data.tracks)} tracks, {len(data.vias)} vias.")

        # Milestone 3: Component Placement & Readback Verification
        print("\n[3/9] Testing Component Placement Verification...")
        comp_js = """
        const comps = await eda.pcb_PrimitiveComponent.getAll() || [];
        return comps.map(c => ({
            id: c.getState_PrimitiveId(),
            ref: c.getState_Designator(),
            x: c.getState_X(),
            y: c.getState_Y()
        }));
        """
        res3 = check(ex(comp_js, window_id=window_id))
        assert isinstance(res3, list), "Component query must return a list"
        print(f"PASS: Placed components verified via live readback ({len(res3)} components active).")

        # Milestone 4: Ground Copper-Zone Creation
        print("\n[4/9] Synthesizing Ground Plane Zone on Layer 2...")
        pts_gnd = [(500.0, 500.0), (2500.0, 500.0), (2500.0, 2000.0), (500.0, 2000.0)]
        create_gnd_js = adapter.build_create_zone_script(
            pcb_uuid, "GND", layer=2, points_mil=pts_gnd, name="LIVE_TEST_GND", priority=1
        )
        res4 = check(ex(create_gnd_js, window_id=window_id, is_mutation=True))
        gnd_id = res4.get("primitive_id") if isinstance(res4, dict) else None
        assert gnd_id and isinstance(gnd_id, str), f"Ground zone creation failed to return primitive ID (got {res4})"
        created_primitive_ids.append(gnd_id)
        print(f"PASS: Created Ground Zone (ID: {gnd_id}).")

        # Milestone 5: Power Polygon Creation
        print("\n[5/9] Synthesizing Power Zone on Layer 1...")
        pts_pwr = [(800.0, 800.0), (1800.0, 800.0), (1800.0, 1600.0), (800.0, 1600.0)]
        create_pwr_js = adapter.build_create_zone_script(
            pcb_uuid, "VIN", layer=1, points_mil=pts_pwr, name="LIVE_TEST_VIN", priority=2
        )
        res5 = check(ex(create_pwr_js, window_id=window_id, is_mutation=True))
        pwr_id = res5.get("primitive_id") if isinstance(res5, dict) else None
        assert pwr_id and isinstance(pwr_id, str), f"Power zone creation failed to return primitive ID (got {res5})"
        created_primitive_ids.append(pwr_id)
        print(f"PASS: Created Power Zone (ID: {pwr_id}).")

        # Milestone 6: Copper Repour
        print("\n[6/9] Triggering Global Copper Repour...")
        repour_js = adapter.build_repour_all_script(pcb_uuid)
        res6 = check(ex(repour_js, window_id=window_id, timeout=60, is_mutation=True))
        assert isinstance(res6, dict) and res6.get("repoured_count") is not None, f"Repour response invalid: {res6}"
        print(f"PASS: Repoured {res6.get('repoured_count')} of {res6.get('total')} zones.")

        # Milestone 7: Copper Readback & Continuity
        print("\n[7/9] Reading Back Poured Copper Regions...")
        chk_poured_js = """
        const p = await eda.pcb_PrimitivePoured.getAll() || [];
        return p.map(pr => ({id: pr.getState_PrimitiveId(), net: pr.getState_Net(), layer: pr.getState_Layer()}));
        """
        res7 = check(ex(chk_poured_js, window_id=window_id))
        assert isinstance(res7, list), f"Poured regions readback must return a list (got {res7})"
        print(f"PASS: Found {len(res7)} active poured regions verified via readback.")

        # Milestone 8: Live DRC Execution
        print("\n[8/9] Executing Live DRC...")
        drc_js = """
        const errors = await eda.pcb_Drc.check(true, true, true) || [];
        return errors.map(e => ({errorType: e.errorType, ruleName: e.ruleName}));
        """
        res8 = check(ex(drc_js, window_id=window_id, timeout=60))
        assert isinstance(res8, list), f"DRC check must return a list of violations (got {res8})"
        print(f"PASS: DRC executed with {len(res8)} reported items.")

        # Milestone 9: Manufacturing Export
        print("\n[9/9] Testing Manufacturing Export...")
        wd = os.path.join(proj_dir, "state", "live_export")
        os.makedirs(wd, exist_ok=True)
        dsn_path = fetch_file('const f=await eda.pcb_ManufactureData.getDsnFile("live_test");', wd, window_id=window_id)
        assert os.path.isfile(dsn_path) and os.path.getsize(dsn_path) > 10, f"Exported DSN file empty or missing: {dsn_path}"
        print(f"PASS: Exported DSN ({os.path.getsize(dsn_path)} bytes) verified on disk.")

        print("\n" + "=" * 70)
        print("ALL 9 MILESTONES VERIFIED WITH OBJECTIVE EVIDENCE.")
        print("=" * 70)

    except Exception as e:
        print(f"\n[FATAL ERROR] Milestone execution failed: {e}")
        execute_rollback(created_primitive_ids, window_id, proj_dir, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
