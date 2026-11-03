"""Placement rule engine tests: each synthetic board breaks exactly one rule (docs/04_PLACEMENT.md)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from desk import placement as PL  # noqa: E402

M = PL.MIL


def part(x, y, w, h, fp="R0402", side=1, pads=None, rot=0):
    """Part centred at (x,y) mm with body w x h mm; default 2 pads along x."""
    if pads is None:
        pads = [{"num": "1", "dx": -w / 3 * M, "dy": 0, "shape": ["RECT", w / 3 * M, h * 0.8 * M], "rot": 0, "net": "N1"},
                {"num": "2", "dx": w / 3 * M, "dy": 0, "shape": ["RECT", w / 3 * M, h * 0.8 * M], "rot": 0, "net": "GND"}]
    return {"x": x * M, "y": y * M, "rot": rot, "layer": side, "fp": fp, "bbox": [-w / 2 * M, w / 2 * M, -h / 2 * M, h / 2 * M], "pads": pads}


def ic(x, y, n=8, w=3.0, net_prefix="S"):
    pads = [{"num": str(k + 1), "dx": (-w / 2 + 0.1) * M if k < n // 2 else (w / 2 - 0.1) * M, "dy": ((k % (n // 2)) - n / 4) * 1.27 * M,
             "shape": ["RECT", 0.6 * M, 0.4 * M], "rot": 0, "net": f"{net_prefix}{k}"} for k in range(n)]
    return part(x, y, w, w, fp="SOIC-8", pads=pads)


BASE = {"board_mm": [30, 20], "roles": {}}


def run(dump, **plan):
    return PL.check(dump, {**BASE, **plan})


class T(unittest.TestCase):
    def test_clean_board(self):
        E, W, Mx = run({"U1": ic(15, 10), "R1": part(10, 10, 1.0, 0.5), "R2": part(20, 10, 1.0, 0.5)})
        self.assertEqual(E, []); self.assertGreater(Mx["T"]["utilisation"], 0)

    def test_pad_to_pad_by_class(self):
        E, _, _ = run({"R1": part(10, 10, 1.0, 0.5), "R2": part(11.1, 10, 1.0, 0.5)})   # pads ~0.1 mm apart
        self.assertTrue(any("pad-to-pad" in e and "0.25" in e for e in E), E)
        E2, _, _ = run({"R1": part(10, 10, 1.0, 0.5, fp="R0201"), "R2": part(11.4, 10, 1.0, 0.5, fp="R0201")})
        self.assertFalse(any("pad-to-pad" in e for e in E2), E2)

    def test_body_overlap_error(self):
        E, _, _ = run({"U1": ic(10, 10), "U2": ic(11, 10, net_prefix="Q")})
        self.assertTrue(any("overlap" in e for e in E))

    def test_opposite_sides_do_not_conflict(self):
        E, _, _ = run({"R1": part(10, 10, 1.0, 0.5), "R2": part(10, 10, 1.0, 0.5, side=2)})
        self.assertEqual(E, [])

    def test_edge_clearance(self):
        E, _, _ = run({"R1": part(0.6, 10, 1.0, 0.5)})
        self.assertTrue(any("board edge" in e for e in E))

    def test_connector_must_be_at_edge_and_front_free(self):
        E, _, _ = run({"J1": part(8, 10, 4, 6, fp="USB-C")})
        self.assertTrue(any("connector" in e and "from board edge" in e for e in E))
        E2, _, _ = run({"J1": part(4.0, 10, 4, 6, fp="USB-C"), "R1": part(1.2, 10, 1.0, 0.5)}, rules={"edge_pad_mm": 0.0})
        self.assertTrue(any("R1: inside the mating/front keep-out of connector J1" in e for e in E2), E2)

    def test_sensor_heat_and_rf(self):
        d = {"U5": ic(5, 10, net_prefix="A"), "U2": ic(10, 10, net_prefix="B"), "U1": ic(15, 10, net_prefix="C")}
        E, _, _ = run(d, roles={"sensors": ["U5"], "heat": ["U2"], "rf": ["U1"]})
        self.assertTrue(any("U5: sensor" in e for e in E)); self.assertTrue(any("U1: RF" in e for e in E))

    def test_keepout_and_height_zone(self):
        d = {"U1": ic(26, 16), "C1": part(27, 17, 1.0, 0.5)}
        E, _, _ = run(d, keepouts=[{"name": "antenna", "rect_mm": [24, 14, 30, 20], "allow": ["U1"]}],
                      heights={"U1": 2.0}, height_zones=[{"name": "lid", "rect_mm": [20, 10, 30, 20], "max_mm": 1.5}])
        self.assertTrue(any("C1: inside keep-out" in e for e in E)); self.assertFalse(any("U1: inside keep-out" in e for e in E))
        self.assertTrue(any("U1: 2.0 mm tall" in e for e in E))

    def test_overpopulation_and_unbalanced_free_space(self):
        d = {f"R{i}{j}": part(1.5 + i * 1.1, 1.5 + j * 0.6, 1.05, 0.58, fp="R0201") for i in range(12) for j in range(16)}
        E, W, Mx = run(d, board_mm=[40, 30], rules={"max_utilisation": 0.03})
        self.assertTrue(any("utilisation" in e for e in E))
        self.assertGreater(Mx["T"]["hotspot_cells"], 0)
        self.assertTrue(any("unbalanced" in w for w in W), W)
        self.assertGreater(Mx["T"]["largest_free_mm2"], 500)

    def test_reserved_area_not_counted_as_free(self):
        d = {"R1": part(2, 2, 1.0, 0.5)}
        _, _, a = run(d)
        _, _, b = run(d, reserved=[{"name": "battery", "rect_mm": [5, 0, 30, 20]}])
        self.assertLess(b["T"]["largest_free_mm2"], a["T"]["largest_free_mm2"])

    def test_decap_distance_from_spec_role(self):
        blocks = [{"parts": [{"ref": "C1", "role": "U1 VDD cap, at pin 1"}]}]
        E, _, _ = PL.check({"U1": ic(10, 10), "C1": part(20, 10, 1.0, 0.5)}, BASE, blocks)
        self.assertTrue(any("C1:" in e and "pin 1" in e for e in E))

    def test_non_orthogonal_rotation_warns(self):
        _, W, _ = run({"R1": part(10, 10, 1.0, 0.5, rot=45)})
        self.assertTrue(any("non-orthogonal" in w for w in W))


if __name__ == "__main__":
    unittest.main()
