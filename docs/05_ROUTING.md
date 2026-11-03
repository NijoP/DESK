# 05 — Routing mental model

Write a short **routing plan** (`projects/<P>/ROUTING_PLAN.md`) before the first track. Route in the order below.

## 1. Stackup decision
| Layers | Use when | Typical use |
|---|---|---|
| 2 | simple, low density, no USB HS / RF critical | Top signals + power, Bottom mostly solid GND |
| 4 | MCU + RF + switching regulators, dense boards | L1 parts/signals · **L2 solid GND (no traces)** · L3 power islands + long buses · L4 signals + GND pour |

## 2. Net classes (set them in EasyEDA before routing)
| Class | Example nets | Width rule |
|---|---|---|
| High current | battery, VSYS, VBUS | IPC-2221 for current, ΔT 10 °C; pours / zones; via arrays (~1 A per 0.3 mm via) |
| Switching loop | SW, inductor, Cin/Cout | pour-shaped, shortest loop, one layer |
| Rails | +3V3, +5V | 0.3–0.5 mm or plane island |
| Differential | USB D+/D- | 90 Ω differential, length-matched, over unbroken GND |
| Signal | everything else | 0.1–0.15 mm |
Clearances: ~0.1 mm signal, 0.2 mm power, 0.5 mm copper to board edge.

## 3. Routing order
1. **Switching regulator loops** (they decide the copper around them).
2. **High-current paths** (battery → charger → system).
3. **Sensitive / controlled** — USB diff pair, crystal, antenna feed, analog sense lines.
4. **Power distribution** — rails to every IC, decaps first then pin.
5. **Buses** (I²C, SPI, I²S) — grouped, parallel, short.
6. **Remaining signals.**
7. **GND pours** on outer layers, stitched to the GND plane; stitching vias every ~2 mm along edges.

## 4. Grounding (no loops, no splits)
- One GND net, one solid plane. Every GND pad gets its own via to the plane (≤ 0.5 mm).
- Never route across a plane split; no traces on the GND plane layer.
- Regulator feedback dividers reference the IC's own GND pin.

## 5. Finish
EasyEDA DRC → **0 errors, 0 unrouted**. Document every accepted warning in the routing plan.
Export Gerber / BOM / Pick-and-place into `projects/<P>/exports/`, commit.
