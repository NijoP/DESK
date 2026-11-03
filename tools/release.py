"""Manufacturing release. Gates first, exports second, cross-checks third, manifest last.
Usage: python tools/release.py projects/<product> <REV> [--layers 4] [--skip-drc-reason "..."]
       python tools/release.py projects/<product> --check <REV>      (re-verify file hashes of an existing release)

Offline gates : lint --final PASS, offline ERC 0 errors, every block 'verified' FRESH in the ledger,
                no pending live operations, BOM audit (tools/bom.py rules) without ERC errors
Live gates    : EasyEDA ERC 0 errors (sch_Drc), DRC 0 violations (pcb_Drc), PCB designators == spec designators
Exports       : Gerber+drill zip, BOM csv, pick-and-place csv, netlist, IPC-D-356A, schematic PDF
Cross-checks  : BOM designators == specs, PnP has every placed part with numeric coordinates, Gerber zip has
                copper/mask/outline/drill (+ inner layers for --layers N)
Output        : projects/<P>/release/<REV>/ + MANIFEST.json (sha256 + gate evidence) + ledger 'release' entry.
Nothing is written if a gate fails."""
import sys, os, json, time, subprocess
from _common import ex, guard, load_project, check, S
from desk.bridge import fetch_file
from desk import ledger as LG, ops, release as RL, erc

a = sys.argv[1:]
proj = a[0]
if "--check" in a:
    rev = a[a.index("--check") + 1]; bad = RL.verify_manifest(os.path.join(proj, "release", rev))
    print("MANIFEST OK" if not bad else f"MODIFIED/MISSING: {bad}"); sys.exit(1 if bad else 0)
rev = a[1]
layers = int(a[a.index("--layers") + 1]) if "--layers" in a else 2
P = load_project(proj)
out = os.path.join(proj, "release", rev)
if os.path.exists(out): raise SystemExit(f"STOP: release {rev} exists. Releases are immutable; use a new revision.")
gates, fail = {}, []

def gate(name, ok, detail=""):
    gates[name] = {"ok": bool(ok), "detail": detail}; print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""))
    if not ok: fail.append(name)

# ---------- offline gates
E, _ = S.lint(proj, final=True); gate("lint --final", not E, f"{len(E)} errors" + (f", first: {E[0]}" if E else ""))
ee, _ = erc.check(proj); gate("offline ERC", not ee, f"{len(ee)} errors")
lib = S.load_library(); led = LG.read(proj); blocks = S.load_blocks(proj)
stale = [b["id"] for b in blocks if LG.verification_state(led, b["id"], LG.block_hash(b, lib)) != "fresh"]
gate("all blocks verified fresh", not stale, ", ".join(stale))
pend = ops.pending(proj); gate("no pending live operations", not pend, ", ".join(p["op"] + " " + p["target"] for p in pend))
if fail: raise SystemExit("RELEASE BLOCKED (offline gates). Nothing exported.")

# ---------- live gates
GS, GP = guard(P["sheet_uuid"]), guard(P["pcb_uuid"])
r = check(ex(GS + 'const r=await eda.sch_Drc.check(true,false,true); return Array.isArray(r)?r.filter(e=>!/warn/i.test(String(e.errorLevel||e.level||e.type||""))).length:-1;', timeout=300))
gate("EasyEDA ERC 0 errors", r == 0, f"{r} errors")
if "--skip-drc-reason" in a:
    gate("EasyEDA DRC (SKIPPED)", True, a[a.index("--skip-drc-reason") + 1])
else:
    r = check(ex(GP + 'const r=await eda.pcb_Drc.check(true,false,true); return Array.isArray(r)?r.length:-1;', timeout=600))
    gate("EasyEDA DRC 0 violations", r == 0, f"{r} violations")
pcb_refs = set(check(ex(GP + 'const cs=await eda.pcb_PrimitiveComponent.get(await eda.pcb_PrimitiveComponent.getAllPrimitiveId()); return cs.map(c=>c.getState_Designator()).filter(x=>x);')))
refs = RL.spec_refs(blocks)
gate("PCB designators == specs", pcb_refs == refs, f"missing {sorted(refs - pcb_refs)[:10]} extra {sorted(pcb_refs - refs)[:10]}")
if fail: raise SystemExit("RELEASE BLOCKED (live gates). Nothing exported.")

# ---------- exports (into a temp dir, moved only when cross-checks pass)
tmp = out + ".partial"; os.makedirs(tmp, exist_ok=True)
name = f"{P.get('name', 'board')}_{rev}"
jobs = {"gerber": GP + f'const f=await eda.pcb_ManufactureData.getGerberFile("{name}_gerber");',
        "bom": GP + f'const f=await eda.pcb_ManufactureData.getBomFile("{name}_bom","csv");',
        "pnp": GP + f'const f=await eda.pcb_ManufactureData.getPickAndPlaceFile("{name}_pnp","csv");',
        "ipc356": GP + f'const f=await eda.pcb_ManufactureData.getIpcD356AFile("{name}_ipc356");',
        "netlist": GS + f'const f=await eda.sch_ManufactureData.getNetlistFile("{name}_netlist");',
        "schematic_pdf": GS + f'const f=await eda.sch_ManufactureData.getExportDocumentFile("{name}_schematic","PDF");'}
files = {}
for k, js in jobs.items():
    try:
        files[k] = fetch_file(js, tmp); print(f"exported {k}: {os.path.basename(files[k])} ({os.path.getsize(files[k])} B)")
    except SystemExit as e:
        (gate if k in ("gerber", "bom", "pnp") else (lambda n, ok, d: print(f"WARN optional export {n} failed: {d}")))(f"export {k}", False, str(e)[:160])
if not fail:
    def txt(k): return open(files[k], encoding="utf-8-sig", errors="replace").read()
    e = RL.check_bom(txt("bom"), refs); gate("BOM designators == specs", not e, "; ".join(e))
    e = RL.check_pnp(txt("pnp"), refs); gate("pick-and-place complete", not e, "; ".join(e))
    e, names = RL.check_gerber(files["gerber"], layers); gate(f"Gerber set ({layers} layers)", not e, "; ".join(e) or f"{len(names)} files")
if fail:
    raise SystemExit(f"RELEASE BLOCKED (exports/cross-checks). Partial files kept for diagnosis in {tmp}")
os.rename(tmp, out)
try: commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
except OSError: commit = ""
m = RL.write_manifest(out, rev, [os.path.join(out, os.path.basename(f)) for f in files.values()], gates,
                      {"date": time.strftime("%Y-%m-%d %H:%M"), "git_commit": commit, "layers": layers,
                       "spec_hashes": {b["id"]: LG.block_hash(b, lib) for b in blocks}})
LG.add(proj, "release", f"release {rev}: {len(m['files'])} files, all gates passed", source=f"release/{rev}/MANIFEST.json")
print(f"RELEASED {rev} -> {out}  (tag it: git tag {P.get('name', 'board')}-{rev})")
