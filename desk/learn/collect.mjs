// DESK Learning Engine - transcript collection through Backpass's harness adapters (MIT, (c) Kun Chen).
// We do NOT parse harness formats ourselves: Backpass's adapters (claude, codex, pi, opencode, cursor, grok,
// hermes) do that. This shim only enumerates, filters to DESK-relevant sessions, redacts, and emits JSONL.
//
// node collect.mjs <backpass_dir> <out.jsonl> <roots_json> [sinceDays] [knownJson]
//   roots_json: ["C:/path/DESK", "C:/path/product"]  - a session is DESK-relevant if its cwd is under a root
//               OR any tool call references DESK tools (tools/ctx.py, tools/build.py, eda bridge /execute)
//   knownJson : {"<harness>:<id>": "<mtime>:<bytes>"} - unchanged sessions are skipped (incremental)
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [bpDir, outFile, rootsJson, sinceDays = "365", knownJson = "{}"] = process.argv.slice(2);
const imp = (p) => import(pathToFileURL(path.join(bpDir, "src", p)).href);
const { ADAPTERS } = await imp("discovery/index.js");
const { redact } = await imp("redact.js");

const norm = (p) => (p || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
const roots = JSON.parse(rootsJson).map(norm);
const known = JSON.parse(fs.readFileSync(knownJson, "utf8") || "{}");
const cutoff = Date.now() - Number(sinceDays) * 86400e3;
const DESK_RX = /tools[\\/](ctx|build|verify|lint|resolve|pins|clear_block|release|erc|drc|route|pcb_\w+|desk|ledger)\.py|\/execute\b|eda\.(sch|pcb|dmt|lib)_/;
const MAXTXT = 4000; // per event text kept; sizes are measured before truncation

const out = fs.createWriteStream(outFile);
const stats = { harnesses: {}, kept: 0, skippedUnchanged: 0 };
for (const [name, adapter] of Object.entries(ADAPTERS)) {
  const h = (stats.harnesses[name] = { candidates: 0, kept: 0, errors: 0 });
  let candidates = [];
  try {
    candidates = adapter.sqliteBacked                      // opencode, hermes, cursor-ide: rows are full descriptors
      ? (adapter.discover ? (await adapter.discover({ cutoffMs: cutoff, config: {}, warn: () => {} })) || [] : adapter.enumerate({ cutoffMs: cutoff, repo: null, config: {} }) || [])
      : adapter.enumerate({ cutoffMs: cutoff, repo: null, config: {} }) || [];
  } catch (e) { h.errors++; h.error = String(e).slice(0, 200); continue; }
  const ctx = adapter.createScanContext?.();
  for (const c of candidates) {
    h.candidates++;
    if (c.mtimeMs && c.mtimeMs < cutoff) continue;
    let d;
    try { d = adapter.discover ? c : adapter.classify(c, { repo: null, config: {}, scanContext: ctx }); } catch { h.errors++; continue; }
    if (!d) continue;
    const key = `${name}:${d.id}`, sig = `${Math.round(c.mtimeMs || 0)}:${c.bytes || 0}`;
    if (known[key] === sig) { stats.skippedUnchanged++; continue; }
    const underRoot = roots.some((r) => norm(d.cwd) === r || norm(d.cwd).startsWith(r + "/"));
    let res;
    try { res = await adapter.read({ ...c, ...d }); } catch { h.errors++; continue; }
    const events = res.events || [];
    const usesDesk = events.some((e) => e.kind === "tool" && DESK_RX.test(JSON.stringify(e.input || "")));
    if (!underRoot && !usesDesk) continue;
    const ev = events.map((e, i) => {
      const input = e.input === undefined ? undefined : JSON.stringify(e.input);
      const result = e.result === undefined ? undefined : typeof e.result === "string" ? e.result : JSON.stringify(e.result);
      return {
        i, kind: e.kind, role: e.role, name: e.name, status: e.status,
        text: e.text ? redact(e.text.slice(0, MAXTXT)) : undefined, textChars: e.text ? e.text.length : 0,
        input: input ? redact(input.slice(0, MAXTXT)) : undefined, inputChars: input ? input.length : 0,
        result: result ? redact(result.length > MAXTXT ? result.slice(0, MAXTXT / 2) + " … " + result.slice(-MAXTXT / 2) : result) : undefined, resultChars: result ? result.length : 0,
      };
    });
    out.write(JSON.stringify({ harness: name, id: d.id, key, sig, cwd: d.cwd, model: res.model || d.model || null,
      startedAt: d.startedAt, parent: d.parentSessionId || null, underRoot, usesDesk, events: ev }) + "\n");
    h.kept++; stats.kept++;
  }
}
out.end(() => process.stdout.write(JSON.stringify(stats) + "\n"));
