"""Synthetic dense-board fixtures for the dense PCB benchmark suite and tests.

Each scenario builds a PCB dump in the exact schema `tools/pcb_dump.py` produces
(mil, EasyEDA frame: ref -> {x, y, rot, layer, fp, bbox, pads[{num, dx, dy, shape, rot,
net, layer}]}) plus board size, origin, planes and the expected characteristics the
tests assert. Generation is deterministic for a given seed.

These are SYNTHETIC boards: their results demonstrate algorithm behaviour, not
real-board validation. Real-board results come from projects/WATCH.

Zero external dependencies.
"""
from __future__ import annotations
import math
import random
from typing import Any, Dict, List, Optional, Tuple

MIL = 39.37007874

SCENARIOS = [
    "mcu_2layer_compact",
    "esp32_4layer",
    "qfn_fine_pitch",
    "motor_high_current",
    "buck_boost",
    "mixed_signal",
    "rf_board",
    "dense_sensor",
    "multi_terminal",
    "multi_rail_limited_layers",
]


def _pad(num, dx_mil, dy_mil, w_mil, h_mil, net, layer=1, rot=0):
    return {"num": str(num), "dx": dx_mil, "dy": dy_mil, "shape": ["RECT", w_mil, h_mil, 0],
            "rot": rot, "net": net, "layer": layer}


def passive(ref: str, x_mm: float, y_mm: float, net_a: str, net_b: str, size: str = "0402",
            rot: int = 0, layer: int = 1) -> Tuple[str, Dict[str, Any]]:
    dims = {"0201": (23.6, 11.8, 15.7), "0402": (39.4, 19.7, 21.3), "0603": (63.0, 31.5, 35.4), "0805": (78.7, 47.2, 49.2)}
    body, pw, ph = dims.get(size, dims["0402"])
    gap = body / 2.0 - pw / 2.0 + 4.0
    pads = [_pad(1, -gap, 0.0, pw, ph, net_a, layer), _pad(2, gap, 0.0, pw, ph, net_b, layer)]
    bb = [-body / 2 - 6, body / 2 + 6, -ph / 2 - 6, ph / 2 + 6]
    if rot in (90, 270):
        bb = [bb[2], bb[3], bb[0], bb[1]]
    return ref, {"id": ref, "x": x_mm * MIL, "y": y_mm * MIL, "rot": rot, "layer": layer, "fp": f"{'C' if ref[0]=='C' else 'R'}{size}",
                 "bbox": bb, "pads": pads}


def qfn(ref: str, x_mm: float, y_mm: float, pins: int, pitch_mm: float, nets: List[str],
        body_mm: Optional[float] = None, layer: int = 1, rot: int = 0) -> Tuple[str, Dict[str, Any]]:
    """Square QFN/QFP with `pins` pads at `pitch_mm`; nets cycle through `nets`."""
    per_side = pins // 4
    body = body_mm if body_mm else (per_side + 1) * pitch_mm + 0.6
    half = body / 2.0 * MIL
    pw = pitch_mm * 0.5 * MIL
    ph = 0.8 * MIL
    pads = []
    n = 1
    for side in range(4):
        for i in range(per_side):
            off = (i - (per_side - 1) / 2.0) * pitch_mm * MIL
            net = nets[(n - 1) % len(nets)]
            if side == 0:
                pads.append(_pad(n, -half + ph / 2, off, ph, pw, net, layer, 90))
            elif side == 1:
                pads.append(_pad(n, off, half - ph / 2, pw, ph, net, layer))
            elif side == 2:
                pads.append(_pad(n, half - ph / 2, -off, ph, pw, net, layer, 90))
            else:
                pads.append(_pad(n, -off, -half + ph / 2, pw, ph, net, layer))
            n += 1
    # exposed pad on GND
    pads.append(_pad(n, 0.0, 0.0, half, half, "GND", layer))
    return ref, {"id": ref, "x": x_mm * MIL, "y": y_mm * MIL, "rot": rot, "layer": layer,
                 "fp": f"QFN-{pins}_{body:.1f}x{body:.1f}mm_P{pitch_mm}mm",
                 "bbox": [-half - 8, half + 8, -half - 8, half + 8], "pads": pads}


def module(ref: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float, pins_per_side: int, pitch_mm: float,
           nets: List[str], layer: int = 1) -> Tuple[str, Dict[str, Any]]:
    """Castellated module (ESP32-style): pads along two long edges."""
    hw, hh = w_mm / 2 * MIL, h_mm / 2 * MIL
    pads = []
    n = 1
    for side in (-1, 1):
        for i in range(pins_per_side):
            off = (i - (pins_per_side - 1) / 2.0) * pitch_mm * MIL
            pads.append(_pad(n, side * (hw - 0.6 * MIL), off, 1.0 * MIL, 0.7 * MIL, nets[(n - 1) % len(nets)], layer))
            n += 1
    return ref, {"id": ref, "x": x_mm * MIL, "y": y_mm * MIL, "rot": 0, "layer": layer, "fp": f"MODULE-{w_mm}x{h_mm}",
                 "bbox": [-hw, hw, -hh, hh], "pads": pads}


def connector(ref: str, x_mm: float, y_mm: float, pins: int, pitch_mm: float, nets: List[str],
              layer: int = 1, th: bool = True) -> Tuple[str, Dict[str, Any]]:
    pads = []
    for i in range(pins):
        off = (i - (pins - 1) / 2.0) * pitch_mm * MIL
        pads.append(_pad(i + 1, off, 0.0, 1.6 * MIL, 1.6 * MIL, nets[i % len(nets)], 11 if th else layer))
    w = (pins + 1) * pitch_mm * MIL
    return ref, {"id": ref, "x": x_mm * MIL, "y": y_mm * MIL, "rot": 0, "layer": layer, "fp": f"CONN-{pins}P{pitch_mm}",
                 "bbox": [-w / 2, w / 2, -2.0 * MIL, 2.0 * MIL], "pads": pads}


def _sprinkle_passives(dump: Dict[str, Any], rng: random.Random, count: int, region: Tuple[float, float, float, float],
                       nets: List[str], prefix: str = "C", size: str = "0402", layer: int = 1) -> None:
    x0, y0, x1, y1 = region
    for i in range(count):
        ref = f"{prefix}{i + 1 + sum(1 for r in dump if r.startswith(prefix))}"
        x = rng.uniform(x0, x1)
        y = rng.uniform(y0, y1)
        a = rng.choice(nets)
        b = "GND" if rng.random() < 0.6 else rng.choice(nets)
        rot = rng.choice([0, 90])
        r, c = passive(ref, x, y, a, b, size=size, rot=rot, layer=layer)
        dump[r] = c


def make_board(scenario: str, seed: int = 7) -> Dict[str, Any]:
    """Return {"dump", "board_mm", "origin_mm", "stackup", "planes", "keepouts", "expect", "meta"}."""
    rng = random.Random(seed)
    dump: Dict[str, Any] = {}
    stackup = ["Top", "Bottom"]
    planes: List[Dict[str, Any]] = []
    keepouts: List[Dict[str, Any]] = []
    expect: Dict[str, Any] = {}
    meta: Dict[str, Any] = {"synthetic": True, "scenario": scenario, "seed": seed}

    if scenario == "mcu_2layer_compact":
        board = (30.0, 25.0)
        sig = [f"GPIO{i}" for i in range(20)] + ["3V3", "GND", "SWDIO", "SWCLK", "UART_TX", "UART_RX", "I2C_SDA", "I2C_SCL"]
        r, c = qfn("U1", 15.0, 12.0, 32, 0.5, sig); dump[r] = c
        r, c = connector("J1", 15.0, 2.0, 6, 2.54, ["GND", "3V3", "SWDIO", "SWCLK", "UART_TX", "UART_RX"]); dump[r] = c
        r, c = connector("J2", 2.5, 12.0, 8, 2.54, [f"GPIO{i}" for i in range(8)]); dump[r] = c
        r, c = connector("J3", 27.5, 12.0, 8, 2.54, [f"GPIO{i}" for i in range(8, 16)]); dump[r] = c
        _sprinkle_passives(dump, rng, 14, (9, 6, 21, 18), sig[:20] + ["3V3"])
        expect = {"min_hotspots": 1, "fine_pitch_cause": True}

    elif scenario == "esp32_4layer":
        board = (30.0, 45.0)
        stackup = ["Top", "Inner1", "Inner2", "Bottom"]
        gpio = [f"IO{i}" for i in range(38)]
        r, c = module("U5", 15.0, 12.0, 18.0, 25.5, 20, 1.27, ["USB_DP", "USB_DM", "3V3", "GND", "EN"] + gpio, layer=2); dump[r] = c
        r, c = qfn("U1", 10.0, 32.0, 24, 0.5, ["VBAT", "VSYS", "GND", "CHG_EN", "CHG_STAT", "VBUS"] + gpio[:6]); dump[r] = c
        r, c = qfn("U2", 20.0, 32.0, 16, 0.5, ["I2S_CLK", "I2S_WS", "I2S_SD", "3V3", "GND", "AMP_SD"] + gpio[6:10]); dump[r] = c
        r, c = qfn("U3", 15.0, 40.0, 20, 0.4, ["I2C_SDA", "I2C_SCL", "INT1", "3V3", "GND"] + gpio[10:16]); dump[r] = c
        r, c = connector("J1", 15.0, 44.0, 6, 0.65, ["VBUS", "USB_DP", "USB_DM", "GND", "CC1", "CC2"], th=False); dump[r] = c
        for i, y in enumerate((28.0, 36.0, 42.0)):
            r, c = connector(f"SW{i+1}", 3.0, y, 2, 2.0, [f"BTN{i+1}", "GND"]); dump[r] = c
        _sprinkle_passives(dump, rng, 36, (5, 26, 26, 43), ["3V3", "VBAT", "VSYS", "I2C_SDA", "I2C_SCL", "I2S_CLK"] + gpio[:12])
        planes = [{"net": "GND", "layer": "Inner1", "polygon_mm": [[0.3, 0.3], [29.7, 0.3], [29.7, 44.7], [0.3, 44.7]]},
                  {"net": "3V3", "layer": "Inner2", "polygon_mm": [[0.3, 0.3], [29.7, 0.3], [29.7, 25.0], [0.3, 25.0]]}]
        keepouts = [{"name": "antenna", "rect_mm": [6.6, 0.0, 25.6, 8.8], "side": "both"}]
        expect = {"min_hotspots": 2, "fine_pitch_cause": True, "routable_layers": 2}

    elif scenario == "qfn_fine_pitch":
        board = (20.0, 20.0)
        nets = [f"S{i}" for i in range(44)] + ["3V3", "GND", "VREF"]
        r, c = qfn("U1", 10.0, 10.0, 48, 0.4, nets, body_mm=6.0); dump[r] = c
        r, c = connector("J1", 10.0, 1.5, 12, 1.0, nets[:12], th=False); dump[r] = c
        r, c = connector("J2", 10.0, 18.5, 12, 1.0, nets[12:24], th=False); dump[r] = c
        r, c = connector("J3", 1.5, 10.0, 12, 1.0, nets[24:36], th=False); dump[r] = c
        _sprinkle_passives(dump, rng, 10, (5, 5, 15, 15), ["3V3", "VREF"] + nets[36:44], size="0201")
        expect = {"min_hotspots": 1, "fine_pitch_cause": True, "max_overall_congestion": 20.0}

    elif scenario == "motor_high_current":
        board = (40.0, 30.0)
        r, c = qfn("U1", 20.0, 15.0, 32, 0.5, ["PWM_AH", "PWM_AL", "PWM_BH", "PWM_BL", "PWM_CH", "PWM_CL", "ISENSE_A", "ISENSE_B", "GND", "VDRV", "3V3"]); dump[r] = c
        for i, (x, nets) in enumerate(((8.0, ["VBUS_MOT", "PHASE_A"]), (20.0, ["VBUS_MOT", "PHASE_B"]), (32.0, ["VBUS_MOT", "PHASE_C"]))):
            r, c = connector(f"Q{2*i+1}", x, 24.0, 3, 2.54, [nets[1], nets[0], f"PWM_{'ABC'[i]}H"]); dump[r] = c
            r, c = connector(f"Q{2*i+2}", x, 6.0, 3, 2.54, ["GND", nets[1], f"PWM_{'ABC'[i]}L"]); dump[r] = c
        r, c = connector("J1", 2.0, 15.0, 2, 5.0, ["VBUS_MOT", "GND"]); dump[r] = c
        r, c = connector("J2", 38.0, 15.0, 3, 3.5, ["PHASE_A", "PHASE_B", "PHASE_C"]); dump[r] = c
        _sprinkle_passives(dump, rng, 12, (12, 10, 28, 20), ["VDRV", "3V3", "ISENSE_A", "ISENSE_B"], size="0603")
        expect = {"power_nets": ["VBUS_MOT", "PHASE_A"], "min_hotspots": 0}

    elif scenario == "buck_boost":
        board = (25.0, 20.0)
        r, c = qfn("U1", 8.0, 10.0, 16, 0.5, ["VIN", "SW", "BST", "FB", "EN", "GND", "PGND", "VCC", "COMP", "SS", "PG"]); dump[r] = c
        r, c = passive("L1", 15.0, 10.0, "SW", "VOUT", size="0805"); dump[r] = c
        for i in range(3):
            r, c = passive(f"CIN{i+1}", 3.0, 6.0 + i * 3.0, "VIN", "GND", size="0805", rot=90); dump[r] = c
            r, c = passive(f"COUT{i+1}", 21.0, 6.0 + i * 3.0, "VOUT", "GND", size="0805", rot=90); dump[r] = c
        r, c = passive("R_FB1", 18.0, 15.0, "VOUT", "FB"); dump[r] = c
        r, c = passive("R_FB2", 18.0, 17.0, "FB", "GND"); dump[r] = c
        r, c = connector("J1", 2.0, 16.0, 2, 3.0, ["VIN", "GND"]); dump[r] = c
        r, c = connector("J2", 23.0, 16.0, 2, 3.0, ["VOUT", "GND"]); dump[r] = c
        expect = {"power_nets": ["VIN", "VOUT", "SW"], "switch_node": "SW"}

    elif scenario == "mixed_signal":
        board = (35.0, 25.0)
        r, c = qfn("U1", 10.0, 12.0, 32, 0.5, [f"D{i}" for i in range(16)] + ["3V3", "GND", "SPI_CLK", "SPI_MOSI", "SPI_MISO", "CS_ADC"]); dump[r] = c
        r, c = qfn("U2", 25.0, 12.0, 20, 0.5, ["AIN0", "AIN1", "AIN2", "AIN3", "AGND", "AVDD", "REFP", "REFN", "SPI_CLK", "SPI_MOSI", "SPI_MISO", "CS_ADC"]); dump[r] = c
        r, c = connector("J1", 32.0, 5.0, 4, 2.0, ["AIN0", "AIN1", "AIN2", "AIN3"]); dump[r] = c
        r, c = connector("J2", 4.0, 5.0, 8, 1.27, [f"D{i}" for i in range(8)], th=False); dump[r] = c
        _sprinkle_passives(dump, rng, 16, (6, 6, 30, 20), ["3V3", "AVDD", "REFP", "AIN0", "AIN1", "D0", "D1"])
        expect = {"analog_nets": ["AIN0", "AVDD"], "min_hotspots": 0}

    elif scenario == "rf_board":
        board = (25.0, 30.0)
        r, c = qfn("U1", 12.5, 20.0, 32, 0.5, ["RF_OUT", "RF_IN", "GND", "VDD_RF", "VDD_PA", "XTAL_P", "XTAL_N", "SPI_CLK", "SPI_MOSI", "SPI_MISO", "CS"]); dump[r] = c
        r, c = passive("C_MATCH1", 12.5, 12.0, "RF_OUT", "ANT", size="0402"); dump[r] = c
        r, c = passive("L_MATCH1", 12.5, 9.0, "ANT", "GND", size="0402"); dump[r] = c
        r, c = passive("Y1", 6.0, 20.0, "XTAL_P", "XTAL_N", size="0805", rot=90); dump[r] = c
        r, c = connector("J1", 12.5, 2.5, 1, 1.0, ["ANT"]); dump[r] = c
        _sprinkle_passives(dump, rng, 10, (4, 16, 22, 28), ["VDD_RF", "VDD_PA", "SPI_CLK"])
        keepouts = [{"name": "antenna", "rect_mm": [6.0, 0.0, 19.0, 6.0], "side": "both"}]
        expect = {"rf_nets": ["RF_OUT", "ANT"]}

    elif scenario == "dense_sensor":
        board = (22.0, 22.0)
        sens = [f"SENS{i}" for i in range(6)]
        nets = ["I2C_SDA", "I2C_SCL", "3V3", "GND", "INT1", "INT2"] + sens
        for i, (x, y) in enumerate(((6, 6), (16, 6), (6, 16), (16, 16), (11, 11))):
            r, c = qfn(f"U{i+1}", x, y, 16, 0.5, nets[i:] + nets[:i], body_mm=3.0); dump[r] = c
        r, c = connector("J1", 11.0, 1.5, 6, 1.0, ["3V3", "GND", "I2C_SDA", "I2C_SCL", "INT1", "INT2"], th=False); dump[r] = c
        _sprinkle_passives(dump, rng, 22, (3, 3, 19, 19), nets, size="0201")
        expect = {"min_hotspots": 1}

    elif scenario == "multi_terminal":
        board = (30.0, 30.0)
        bus = [f"BUS{i}" for i in range(8)] + ["CLK", "CS0", "CS1", "CS2", "3V3", "GND"]
        for i, (x, y) in enumerate(((6, 6), (24, 6), (6, 24), (24, 24), (15, 15))):
            r, c = qfn(f"U{i+1}", x, y, 24, 0.5, bus); dump[r] = c
        _sprinkle_passives(dump, rng, 12, (8, 8, 22, 22), ["3V3"])
        expect = {"multi_terminal_nets": bus[:8], "min_crossings": 10}

    elif scenario == "multi_rail_limited_layers":
        board = (30.0, 25.0)
        stackup = ["Top", "Inner1", "Inner2", "Bottom"]
        rails = ["VIN_12V", "5V", "3V3", "1V8", "1V2"]
        r, c = qfn("U1", 8.0, 8.0, 16, 0.5, ["VIN_12V", "5V", "GND", "FB5", "EN5"]); dump[r] = c
        r, c = qfn("U2", 8.0, 17.0, 16, 0.5, ["5V", "3V3", "GND", "FB3", "EN3"]); dump[r] = c
        r, c = qfn("U3", 22.0, 8.0, 16, 0.5, ["3V3", "1V8", "GND", "FB18", "EN18"]); dump[r] = c
        r, c = qfn("U4", 22.0, 17.0, 16, 0.5, ["3V3", "1V2", "GND", "FB12", "EN12"]); dump[r] = c
        r, c = qfn("U5", 15.0, 12.5, 48, 0.4, rails + ["GND"] + [f"IO{i}" for i in range(30)], body_mm=6.0); dump[r] = c
        r, c = connector("J1", 2.0, 12.5, 2, 3.0, ["VIN_12V", "GND"]); dump[r] = c
        _sprinkle_passives(dump, rng, 24, (4, 4, 26, 21), rails, size="0603")
        planes = [{"net": "GND", "layer": "Inner1", "polygon_mm": [[0.3, 0.3], [29.7, 0.3], [29.7, 24.7], [0.3, 24.7]]},
                  {"net": "3V3", "layer": "Inner2", "polygon_mm": [[0.3, 0.3], [29.7, 0.3], [29.7, 24.7], [0.3, 24.7]]}]
        expect = {"power_nets": rails, "routable_layers": 2, "min_hotspots": 1}
    else:
        raise ValueError(f"unknown scenario {scenario}; choose from {SCENARIOS}")

    return {"dump": dump, "board_mm": board, "origin_mm": (0.0, 0.0), "stackup": stackup, "planes": planes,
            "keepouts": keepouts, "expect": expect, "meta": meta}


def plane_layers_from_planes(planes: List[Dict[str, Any]], stackup: List[str]) -> Dict[int, str]:
    """Map plane declarations (layer name) to stackup indexes -> net."""
    out = {}
    names = [s.lower() for s in stackup]
    for p in planes or []:
        name = str(p.get("layer", "")).lower()
        if name in names:
            out[names.index(name) + 1] = p["net"]
    return out
