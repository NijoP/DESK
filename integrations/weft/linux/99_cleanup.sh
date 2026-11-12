#!/usr/bin/env bash
# Cleanup after a validation. Default: stop the DESK node service, stop the scratch project's unfinished Weft runs,
# revoke the signal token. Nothing else.
#   --forget-connection   also delete the stored node-service connection from Weft (every pick of it goes too)
#   --remove-scratch      also delete the validation folder (records, logs, secrets)
#   --uninstall-weft      also run upstream's `./setup.sh --uninstall` (removes the default Weft install)
# Docker, rustup and apt packages are never removed by this script.
source "$(dirname "$0")/common.sh"

say "Stop the DESK node service"
pidfile="${VAL_DIR}/service.pid"
if [[ -s "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
  kill "$(cat "$pidfile")" && info "stopped pid $(cat "$pidfile")"
fi
rm -f "$pidfile"

if command -v weft >/dev/null; then
  say "Stop the scratch project's unfinished runs"
  weft --json runs --tag "${VAL_PROJECT}" --status running --limit 100 2>/dev/null \
    | python3 -c '
import json, sys
text = sys.stdin.read().strip()
try:
    doc = json.loads(text)
except ValueError:
    doc = [json.loads(l) for l in text.splitlines() if l.strip().startswith("{")]
rows = doc if isinstance(doc, list) else doc.get("runs", [])
for r in rows:
    rid = r.get("id") or r.get("runId")
    if rid: print(rid)
' | while read -r rid; do weft stop "$rid" >/dev/null 2>&1 && info "stopped ${rid}"; done || true

  sigfile="${VAL_SECRETS}/signal_token.json"
  if [[ -s "$sigfile" ]]; then
    id="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$sigfile")"
    weft token revoke "$id" >/dev/null 2>&1 && info "revoked signal token ${id}" && rm -f "$sigfile"
  fi
  if [[ " $* " == *" --forget-connection "* && -s "${VAL_DIR}/connection.id" ]]; then
    staged="$(staged_dir requirement_to_profile)"
    (cd "$staged" && weft connect --forget "$(cat "${VAL_DIR}/connection.id")" --yes) && rm -f "${VAL_DIR}/connection.id"
  fi
fi

if [[ " $* " == *" --uninstall-weft "* ]]; then
  say "Uninstall the default Weft install (upstream ./setup.sh --uninstall)"
  (cd "${WEFT_DIR}" && ./setup.sh --uninstall)
fi
if [[ " $* " == *" --remove-scratch "* ]]; then
  rm -rf "${VAL_DIR}" && info "removed ${VAL_DIR}"
fi
say "Cleanup done"
