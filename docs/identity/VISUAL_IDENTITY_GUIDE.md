# Visual Identity & Brand Guide: THE SENTINEL

**Project:** DESK — Electronics Engineering Workbench  
**Brand Persona:** THE SENTINEL (Homeostatic Engineering Organism)  
**Scope:** GitHub Presentation, Technical Documentation, SVG Assets, and Local Mission Control Cockpit UI

---

## 1. Brand Philosophy & Aesthetic Direction

THE SENTINEL's visual identity bridges **biological organic complexity** and **high-precision electronics engineering**. 

It conveys scientific seriousness, vigilance, and non-destructive protection. It must never appear whimsical, juvenile, or decorative. Every visual element—from color choices to circuit trace widths—has an engineering or physiological meaning.

### Visual Pillars:
- **Scientific Rigor:** Clear, sharp vectors mimicking silicon wafers, multilayer FR-4 PCBs, and cellular membranes.
- **Deep Environmental Contrast:** Rich, low-light backgrounds reminiscent of an cleanroom inspection microscope or dark-mode CAD canvas.
- **Restrained Illumination:** Bioluminescent cyan and teal conduits that represent signal flow and neural pathways without overwhelming decorative glow.
- **Deterministic Color Coding:** Every color denotes a verified physical or electrical state.

---

## 2. Master Color Palette

```
┌────────────────────────────────────────────────────────────────────────┐
│                          COLOR SPECIFICATION                           │
├──────────────┬──────────────┬──────────────┬───────────────────────────┤
│ Role         │ Color Name   │ Hex Code     │ Meaning / Engineering Use │
├──────────────┼──────────────┼──────────────┼───────────────────────────┤
│ Background   │ Deep Abyss   │ `#03070d`    │ Terminal & canvas base    │
│ Foundation   │ Dark Charcoal│ `#080e18`    │ Card & panel background   │
│ Exoskeleton  │ Slate Armor  │ `#1e293b`    │ Borders & structural ribs │
│ Primary Glow │ Cyber Cyan   │ `#38bdf8`    │ Main neural-circuit traces│
│ Secondary    │ Deep Sky     │ `#0284c7`    │ Bus routes & core aperture│
│ Healthy / OK │ Emerald Life │ `#10b981`    │ Verified gates, 0 DRC err │
│ Warning      │ Amber Sensor │ `#f59e0b`    │ Unrouted nets, DRC checks │
│ Critical     │ Crimson Fault│ `#ef4444`    │ Shorts, clearance crashes │
│ Luminous Core│ Pure Photon  │ `#ffffff`    │ Mathematical core center  │
└──────────────┴──────────────┴──────────────┴───────────────────────────┘
```

### Color Usage Rules:
1. **Red (`#ef4444`) is strictly reserved for critical faults:** Never use red for branding, decorative borders, or non-critical labels. In electronics, red means an electrical short circuit or irreversible hazard.
2. **Green (`#10b981`) requires proof:** Only display green indicators when physical readback and all 8 acceptance gates have passed with fresh test evidence.
3. **Amber (`#f59e0b`) is diagnostic:** Use amber for ongoing audits, pending approvals, and non-fatal warnings (e.g., silkscreen clearance).

---

## 3. Brand Assets & Typography

### Asset Directory Structure:
```text
assets/
  branding/
    desk-logo.svg                      # Standalone brand mark (emblem)
    desk-sentinel.svg                  # Character hero vector illustration
    desk-homeostasis-loop.svg          # 7-stage closed-loop operating model
    desk-biological-architecture.svg   # 4-pillar biomimetic mapping diagram
```

### Typography Hierarchy:
- **Primary Body Font:** Clean system sans-serif: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
- **Engineering / Code Font:** High-legibility monospaced font: `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace`.
- **Title Headers:** Bold, high-contrast, tracking letter-spacing $+2\,\text{px}$ to $+4\,\text{px}$ on major titles.

---

## 4. Asset Guidelines & Clear Space

### 1. THE SENTINEL Hero Illustration (`desk-sentinel.svg`)
- **Dimensions:** $1200 \times 800\,\text{px}$ vector viewBox.
- **Context:** Used at the top of technical overviews and GitHub README Hero sections.
- **Integrity:** Never crop the central luminous nucleus. The lateral sensory axons must remain fully visible to convey environmental awareness.

### 2. The DESK Brand Emblem (`desk-logo.svg`)
- **Dimensions:** $512 \times 512\,\text{px}$ vector viewBox.
- **Context:** Repository avatar, favicon, Local Mission Control navigation header, and badge icon.
- **Minimum Sizing:** Minimum display size is $32 \times 32\,\text{px}$ without losing structural clarity.

### 3. The Homeostasis Loop Diagram (`desk-homeostasis-loop.svg`)
- **Dimensions:** $1200 \times 520\,\text{px}$ vector viewBox.
- **Context:** Workflow sections, architectural documentation, and repair guides.
- **Rule:** The returning feedback loop from stage 7 to stage 1 must always be retained; without feedback, the homeostatic loop is broken.

### 4. Biological Architecture Diagram (`desk-biological-architecture.svg`)
- **Dimensions:** $1200 \times 680\,\text{px}$ vector viewBox.
- **Context:** Architecture specifications and system engineering reviews.
- **Rule:** Displays actual verified module paths (`desk/rework/audit.py`, `desk/quality.py`, etc.). Do not substitute hypothetical or unverified components.

---

## 5. UI Integration in Local Mission Control (Port 49630)

When rendering telemetry and lifecycle stages in the in-browser cockpit:
- Display the **THE SENTINEL** brand mark at the top left of the dashboard.
- Active rework and engineering stages should pulse in restrained cyan (`#38bdf8`).
- Gated states awaiting human approval must highlight with an amber border (`#f59e0b`) and display the explicit authorization token prompt (`RW-APR-XXXX`).
- Quality gate summaries must use the emerald (`#10b981`) and crimson (`#ef4444`) binary fail-closed indicators.
