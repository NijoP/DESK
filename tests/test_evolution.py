"""Comprehensive Automated Test Suite for DESK Evolution.
Covers all 12 realistic PCB scenarios required by MASTER PROMPT Part 11:
1. FPC connector with fine-pitch pads
2. Screw-terminal power input
3. Microcontroller with decoupling capacitors
4. Sensor circuit with RC filters
5. High-current power stage
6. Differential interface
7. Multi-terminal power net
8. Congested four-layer board
9. PCB with orphan vias
10. PCB with disconnected pads
11. PCB with blocked connector escape / mating paths
12. Board with incorrect footprint mapping

Verifies:
- Hard mechanical and footprint constraints are never violated during placement
- Multi-terminal connectivity is correctly represented
- DRC convergence engine detects genuine errors and prevents false passes
"""
import unittest
import math
from desk.models import (
    ComponentRequirement,
    FootprintInvariant,
    PadGeometry,
    PlacementIntent,
    NetEndpoint,
    DRCViolation
)
from desk.component_intel import (
    ComponentClassifier,
    FootprintIntegrityEngine,
    ComponentIntelligenceExtractor
)
from desk.placement_intel import (
    MechanicalEnvelope,
    FunctionalClusterBuilder,
    TopologicalPassiveSnapper,
    PlacementIntelligenceEngine
)
from desk.routability import (
    RoutabilityEvaluator,
    PlacementAcceptanceGate
)
from desk.router import (
    StackupManager,
    RoutingPriorityScheduler,
    TraceWidthCalculator,
    DSNTuningEngine,
    RoutingPlanGenerator
)
from desk.drc_engine import (
    DRCParser,
    FailureDiagnoser,
    RecoveryPlanner,
    DRCConvergenceLoop
)

MIL = 39.37007874

class TestDESKEvolution(unittest.TestCase):

    def setUp(self):
        self.board_dims = (60.0, 40.0)

    # -------------------------------------------------------------------------
    # 1. FPC Connector with fine-pitch pads
    # -------------------------------------------------------------------------
    def test_01_fpc_connector_fine_pitch(self):
        pads = []
        for i in range(16):
            pads.append({
                "num": str(i + 1),
                "dx": (i * 0.5 - 3.75) * MIL,
                "dy": 0.0,
                "shape": ["RECT", 0.3 * MIL, 1.2 * MIL],
                "net": f"FPC_S{i}",
                "layer": 1
            })
        dump_fpc = {
            "x": 30.0 * MIL, "y": 3.0 * MIL, "rot": 0, "layer": 1,
            "fp": "FH34SRJ-16S-0.5SH", "bbox": [-5.0 * MIL, 5.0 * MIL, -2.0 * MIL, 2.0 * MIL],
            "pads": pads
        }
        cls = ComponentClassifier.classify("J1", footprint="FH34SRJ-16S-0.5SH", pad_count=16)
        self.assertEqual(cls, "mechanical_anchor")

        invariant = FootprintIntegrityEngine.extract_invariant("J1", dump_fpc)
        self.assertEqual(invariant.pad_count, 16)
        self.assertAlmostEqual(invariant.pad_pitch_mm, 0.5, places=2)

    # -------------------------------------------------------------------------
    # 2. Screw-terminal power input
    # -------------------------------------------------------------------------
    def test_02_screw_terminal_power_input(self):
        tb_body = (10.0, 25.0, 2.0, 12.0)  # minX, maxX, minY, maxY
        corridors = MechanicalEnvelope.get_screw_terminal_access_corridor(
            tb_body, wire_entry_side="B", screwdriver_side="T", screwdriver_depth_mm=10.0
        )
        sd_box = corridors["screwdriver_access"]
        self.assertTrue(sd_box[2] >= 12.0)  # Starts at top of body

        # Test collision: place blocking capacitor inside screwdriver corridor
        target = {
            "TB1": [17.5, 7.0, 0, "T"],
            "C1_BLOCK": [17.5, 15.0, 0, "T"]  # inside screwdriver zone!
        }
        reqs = {
            "TB1": ComponentRequirement(ref="TB1", mpn="TB002", width_mm=15.0, height_mm=10.0, electrical_role="screw_terminal"),
            "C1_BLOCK": ComponentRequirement(ref="C1_BLOCK", mpn="C0402", width_mm=1.0, height_mm=0.5, electrical_role="passive")
        }
        errs = RoutabilityEvaluator.verify_mechanical_access({"TB1": {}, "C1_BLOCK": {}}, target, reqs, self.board_dims)
        self.assertTrue(any("screwdriver access corridor" in e for e in errs))

    # -------------------------------------------------------------------------
    # 3. Microcontroller with decoupling capacitors
    # -------------------------------------------------------------------------
    def test_03_mcu_with_decoupling_capacitors(self):
        reqs = {
            "U1": ComponentRequirement(ref="U1", mpn="STM32F4", width_mm=10.0, height_mm=10.0, electrical_role="primary_ic",
                                       pads=[PadGeometry(num="5", net="3V3")]),
            "C1": ComponentRequirement(ref="C1", mpn="0402CAP", width_mm=1.0, height_mm=0.5, electrical_role="decoupling_capacitor",
                                       pad_to_net={"1": "3V3", "2": "GND"})
        }
        intents = {"U1": PlacementIntent(ref="U1", target_x_mm=30.0, target_y_mm=20.0, side="T", reason="MCU")}
        blocks = [{"id": "01_MCU", "parts": [{"ref": "C1", "role": "decoupling U1 pin 5"}]}]
        snaps = TopologicalPassiveSnapper.snap_passives(intents, reqs, blocks)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0][0], "C1")
        self.assertEqual(snaps[0][1], "U1")

    # -------------------------------------------------------------------------
    # 4. Sensor circuit with RC filters
    # -------------------------------------------------------------------------
    def test_04_sensor_circuit_with_rc_filters(self):
        reqs = {
            "U2": ComponentRequirement(ref="U2", mpn="SHT45", width_mm=2.0, height_mm=2.0, electrical_role="primary_ic",
                                       pad_to_net={"1": "SDA_FILT", "2": "GND"}),
            "R1": ComponentRequirement(ref="R1", mpn="R0402", width_mm=1.0, height_mm=0.5, electrical_role="resistor",
                                       pad_to_net={"1": "SDA", "2": "SDA_FILT"}),
            "C5": ComponentRequirement(ref="C5", mpn="C0402", width_mm=1.0, height_mm=0.5, electrical_role="capacitor",
                                       pad_to_net={"1": "SDA_FILT", "2": "GND"})
        }
        blocks = [{"id": "04_SENSOR", "title": "Sensor Acquisition", "parts": [{"ref": "U2"}, {"ref": "R1"}, {"ref": "C5"}]}]
        clusters = FunctionalClusterBuilder.build_clusters(reqs, blocks)
        self.assertIn("04_SENSOR", clusters)
        self.assertEqual(clusters["04_SENSOR"].electrical_role, "sensor_acquisition")
        self.assertIn("U2", clusters["04_SENSOR"].primary_refs)
        self.assertIn("R1", clusters["04_SENSOR"].passive_refs)

    # -------------------------------------------------------------------------
    # 5. High-current power stage
    # -------------------------------------------------------------------------
    def test_05_high_current_power_stage(self):
        w_sig = TraceWidthCalculator.get_width_mil("SENSOR_SDA", current_A=0.01)
        w_pwr = TraceWidthCalculator.get_width_mil("VBUS_BOOST", current_A=2.0)
        self.assertGreaterEqual(w_pwr, 12.0)
        self.assertLessEqual(w_sig, 6.0)

        nets = {
            "VBUS_BOOST": [NetEndpoint(ref="U3", pad_num="1", net="VBUS_BOOST", x_mil=0, y_mil=0, layer=1),
                           NetEndpoint(ref="C6", pad_num="1", net="VBUS_BOOST", x_mil=100, y_mil=0, layer=1)]
        }
        stages = RoutingPriorityScheduler.schedule_nets(nets, high_current={"VBUS_BOOST": 2.0})
        self.assertIn("VBUS_BOOST", stages[5])  # Stage 5 = Power distribution

    # -------------------------------------------------------------------------
    # 6. Differential interface
    # -------------------------------------------------------------------------
    def test_06_differential_interface(self):
        nets = {
            "USB_D_P": [NetEndpoint(ref="J1", pad_num="2", net="USB_D_P", x_mil=0, y_mil=0, layer=1),
                        NetEndpoint(ref="U1", pad_num="10", net="USB_D_P", x_mil=500, y_mil=0, layer=1)],
            "USB_D_N": [NetEndpoint(ref="J1", pad_num="3", net="USB_D_N", x_mil=0, y_mil=50, layer=1),
                        NetEndpoint(ref="U1", pad_num="11", net="USB_D_N", x_mil=500, y_mil=50, layer=1)]
        }
        diff_pairs = {"USB_HS": ("USB_D_P", "USB_D_N")}
        stages = RoutingPriorityScheduler.schedule_nets(nets, diff_pairs=diff_pairs)
        self.assertIn("USB_D_P", stages[3])  # Stage 3 = Critical
        self.assertIn("USB_D_N", stages[3])

    # -------------------------------------------------------------------------
    # 7. Multi-terminal power net
    # -------------------------------------------------------------------------
    def test_07_multi_terminal_power_net(self):
        dump = {
            "U1": {"pads": [{"num": "1", "dx": 0, "dy": 0, "net": "3V3"}], "x": 0, "y": 0, "rot": 0},
            "U2": {"pads": [{"num": "1", "dx": 0, "dy": 0, "net": "3V3"}], "x": 1000, "y": 0, "rot": 0},
            "U3": {"pads": [{"num": "1", "dx": 0, "dy": 0, "net": "3V3"}], "x": 1000, "y": 1000, "rot": 0},
            "C1": {"pads": [{"num": "1", "dx": 0, "dy": 0, "net": "3V3"}], "x": 0, "y": 1000, "rot": 0}
        }
        graph = RoutabilityEvaluator.build_connectivity_graph(dump)
        self.assertIn("3V3", graph.multi_terminal_trees)
        edges = graph.multi_terminal_trees["3V3"]
        self.assertEqual(len(edges), 3)  # MST of 4 nodes has exactly 3 edges
        self.assertGreater(graph.mst_wirelength_mil, 0.0)

    # -------------------------------------------------------------------------
    # 8. Congested four-layer board
    # -------------------------------------------------------------------------
    def test_08_congested_four_layer_board(self):
        dump = {"U1": {"pads": [{"layer": 15, "net": "GND"}]}}  # Layer 15 = inner layer
        stackup = StackupManager.detect_stackup(dump, {"layers": 4})
        self.assertEqual(len(stackup), 4)
        self.assertIn("Inner1_GND", stackup)

    # -------------------------------------------------------------------------
    # 9. PCB with orphan vias
    # -------------------------------------------------------------------------
    def test_09_pcb_with_orphan_vias(self):
        raw_drc = [
            {"ruleName": "Unconnected Via", "errorType": "Orphan Via", "layer": "Top",
             "obj1": {"primitiveType": "VIA", "primitiveId": "V1", "net": ""}, "pos": [500, 500]}
        ]
        violations = DRCParser.parse(raw_drc)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].error_type, "Orphan Via")

        readiness = DRCConvergenceLoop.evaluate_readiness("TEST", violations, [])
        self.assertFalse(readiness.approved)

    # -------------------------------------------------------------------------
    # 10. PCB with disconnected pads
    # -------------------------------------------------------------------------
    def test_10_pcb_with_disconnected_pads(self):
        raw_drc = [
            {"ruleName": "Unconnected Net", "errorType": "Open Net", "layer": "Top",
             "obj1": {"primitiveType": "PAD", "primitiveId": "P1", "net": "SPI_MOSI"}, "pos": [300, 400]}
        ]
        violations = DRCParser.parse(raw_drc)
        failed = FailureDiagnoser.identify_failed_nets(violations)
        self.assertIn("SPI_MOSI", failed)

        rec = RecoveryPlanner.plan_recovery(1, violations)
        self.assertIn("SPI_MOSI", rec.failed_nets)
        self.assertEqual(len(rec.inserted_escape_vias), 1)

    # -------------------------------------------------------------------------
    # 11. Blocked connector escape / mating paths
    # -------------------------------------------------------------------------
    def test_11_blocked_connector_mating_envelope(self):
        conn_body = (20.0, 40.0, 1.0, 8.0)  # near bottom edge
        mating_box = MechanicalEnvelope.get_connector_mating_envelope(conn_body, self.board_dims)
        self.assertTrue(mating_box[2] <= 0.0)  # Faces bottom edge

        target = {
            "J1": [30.0, 4.5, 0, "T"],
            "C_STRAY": [30.0, 0.5, 0, "T"]  # Placed in the plug mating envelope!
        }
        reqs = {
            "J1": ComponentRequirement(ref="J1", mpn="USB-C", footprint_id="CONN_USB", width_mm=20.0, height_mm=7.0, electrical_role="mechanical_anchor"),
            "C_STRAY": ComponentRequirement(ref="C_STRAY", mpn="C0402", width_mm=1.0, height_mm=0.5, electrical_role="passive")
        }
        errs = RoutabilityEvaluator.verify_mechanical_access({"J1": {}, "C_STRAY": {}}, target, reqs, self.board_dims)
        self.assertTrue(any("blocks connector mating plug envelope" in e for e in errs))

    # -------------------------------------------------------------------------
    # 12. Incorrect footprint mapping
    # -------------------------------------------------------------------------
    def test_12_incorrect_footprint_mapping(self):
        orig_invariant = FootprintInvariant(
            ref="U4",
            footprint_name="QFN-16",
            pad_count=16,
            pad_numbers=[str(i) for i in range(1, 17)],
            pad_positions={str(i): (float(i * 20), 0.0) for i in range(1, 17)}
        )
        # Mutated current part: only 14 pads!
        mutated_part = {
            "pads": [{"num": str(i), "dx": float(i * 20), "dy": 0.0} for i in range(1, 15)]
        }
        inv_errs = FootprintIntegrityEngine.verify(orig_invariant, mutated_part)
        self.assertTrue(len(inv_errs) > 0)
        self.assertTrue(any("pad count changed from 16 to 14" in e for e in inv_errs))


if __name__ == "__main__":
    unittest.main()
