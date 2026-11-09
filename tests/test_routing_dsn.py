"""Automated Verification Suite for Specctra DSN S-Expression Parser and Transformer.
Tests AST parsing, formatting, round-trip invariance, and rule updates.
"""
import unittest
import os
from desk.routing.dsn import SExprParser, DSNTree, DSNInvariantViolationError


SAMPLE_DSN = """(PCB "TEST_BOARD"
  (parser
    (host_cad "EasyEDA Pro")
    (host_version "3.2.149")
  )
  (resolution mil 1000)
  (structure
    (boundary
      (path signal 0 0 0 0 1000.00 1000.00 1000.00 1000.00 0 0 0)
    )
    (grid wire 0.25)
    (grid via 0.25)
    (rule (width 6.0))
    (rule (clear 6.0))
    (layer Top (type signal))
    (layer Bottom (type signal))
  )
  (placement
    (component "U1"
      (place "U1" 100 200 front 0)
    )
    (component "R1"
      (place "R1" 300 400 front 90)
    )
  )
  (library
    (image "U1"
      (pin "p1" "1" 10 20)
      (pin "p2" "2" 30 40)
    )
    (image "R1"
      (pin "pr1" "1" 50 60)
      (pin "pr2" "2" 70 80)
    )
  )
  (network
    (net "VBAT"
      (pins "U1-1" "R1-1")
    )
    (net "GND"
      (pins "U1-2" "R1-2")
    )
    (class "VBAT" 'VBAT'
      (circuit (use_via via0))
      (rule (width 6.0) (clearance 6.0))
    )
  )
  (wiring)
)"""


class TestRoutingDSN(unittest.TestCase):

    def test_sexpr_tokenizer_and_parser(self):
        tokens = SExprParser.tokenize('(class "VBAT" \'VBAT\' (rule (width 10.0)))')
        self.assertIn('(', tokens)
        self.assertIn(')', tokens)
        self.assertIn('"VBAT"', tokens)
        self.assertIn("'VBAT'", tokens)

        tree = SExprParser.parse('(a (b c) "hello world")')
        self.assertEqual(tree[0], 'a')
        self.assertEqual(tree[1], ['b', 'c'])
        self.assertEqual(tree[2], '"hello world"')

    def test_dsn_tree_roundtrip_and_invariants(self):
        tree = DSNTree(SAMPLE_DSN)
        self.assertEqual(tree.baseline_invariants["component_count"], 2)
        self.assertEqual(tree.baseline_invariants["net_count"], 2)
        self.assertEqual(tree.baseline_invariants["pin_count"], 4)

        # Serialize without edits
        serialized = tree.serialize()
        self.assertIn('(PCB', serialized)
        self.assertIn('(component', serialized)
        self.assertIn('"U1"', serialized)
        self.assertIn('(net', serialized)
        self.assertIn('"VBAT"', serialized)

    def test_dsn_boundary_and_grid_updates(self):
        tree = DSNTree(SAMPLE_DSN)
        tree.set_boundary(1500.0, 1200.0)
        tree.set_grid_resolution(wire_grid=1.25, via_grid=1.25)
        tree.set_default_rules(width_mil=5.0, clearance_mil=4.02)

        serialized = tree.serialize()
        self.assertIn('1500.00', serialized)
        self.assertIn('1200.00', serialized)
        self.assertIn('(grid wire 1.25)', serialized)
        self.assertIn('(grid via 1.25)', serialized)
        self.assertIn('(width 5.00)', serialized)
        self.assertIn('(clear 4.02)', serialized)

    def test_dsn_class_rule_update_preserves_circuit_subnode(self):
        tree = DSNTree(SAMPLE_DSN)
        tree.update_net_classes(
            net_widths={"VBAT": 10.0},
            net_clearances={"VBAT": 4.5},
            power_nets={"VBAT"},
            fine_pitch_width_mil=5.0
        )
        serialized = tree.serialize()
        # Verify (circuit (use_via via0)) is preserved!
        self.assertIn('(circuit', serialized)
        self.assertIn('use_via via0', serialized)
        self.assertIn('(width 10.00)', serialized)
        self.assertIn('(clearance 4.50)', serialized)

    def test_dsn_invariant_violation_detection(self):
        tree = DSNTree(SAMPLE_DSN)
        # Corrupt tree by removing a component
        placement = tree.find_node(["placement"])
        placement.pop()  # Remove R1 component

        with self.assertRaises(DSNInvariantViolationError):
            tree.serialize()


if __name__ == "__main__":
    unittest.main()
