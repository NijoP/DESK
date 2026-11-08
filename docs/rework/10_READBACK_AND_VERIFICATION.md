# DESK Rework Mode: Readback & Verification

**Document ID:** `docs/rework/10_READBACK_AND_VERIFICATION.md`  

---

## 1. Non-Negotiable Physical Readback

A successful HTTP or API return code does not prove that physical geometry was correctly modified in the ECAD canvas.

Rework Mode mandates **Physical Readback**:
- **Track Operations:** Read back actual start/end coordinates, layer, net, and width.
- **Via Operations:** Read back coordinate, drill diameter, layer span, and net.
- **Component Operations:** Read back designator, $(X, Y)$ coordinate, rotation, and package.
- **Pad Operations:** Read back assigned net string and clearance.
- **Copper Operations:** Read back zone ID, polygon coordinates, and repour state.

---

## 2. Immediate Post-Mutation Verification

Immediately following readback, DESK evaluates:
1. Did the target primitive change to the expected state?
2. Did unrelated protected primitives remain unchanged?
3. Were any new short circuits or opens introduced?

If verification passes, the repair is marked `VERIFIED`. If verification fails, dependent operations are immediately blocked.
