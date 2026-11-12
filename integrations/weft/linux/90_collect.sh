#!/usr/bin/env bash
# Diagnostics bundle for a failed or finished validation. Collects results, logs, DESK traces and Weft's own state.
# Leaves out the secrets folder, and refuses to finish if a known secret value appears in what it collected.
source "$(dirname "$0")/common.sh"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="${VAL_DIR}/bundle-${stamp}"
mkdir -p "$out/weft" "$out/desk"
cp -f "${RESULTS}" "$out/" 2>/dev/null || true
cp -rf "${VAL_LOGS}" "$out/logs" 2>/dev/null || true
cp -rf "${VAL_PROJECTS}/${VAL_PROJECT}/state/weft" "$out/desk/records" 2>/dev/null || true
{
  echo "desk commit: $(git -C "${DESK_REPO}" rev-parse HEAD) $( [[ -n "$(git -C "${DESK_REPO}" status --porcelain)" ]] && echo '(local changes)')"
  echo "weft pin:    ${PIN}"
  echo "weft head:   $(git -C "${WEFT_DIR}" rev-parse HEAD 2>/dev/null)"
  uname -a; . /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-}"
  docker version --format 'docker engine {{.Server.Version}}' 2>/dev/null || true
  rustup show active-toolchain 2>/dev/null || true
} > "$out/environment.txt"
if command -v weft >/dev/null; then
  weft --version > "$out/weft/version.txt" 2>&1 || true
  weft daemon status > "$out/weft/daemon_status.txt" 2>&1 || true
  weft --json runs --tag "${VAL_PROJECT}" --limit 20 > "$out/weft/runs.json" 2>&1 || true
  timeout 5 weft daemon logs > "$out/weft/daemon_logs.txt" 2>&1 || true   # it follows the log; take 5 s of it
fi
cp -f "$HOME/.local/share/weft/setup-runs.log" "$out/weft/" 2>/dev/null || true

# Fail closed on a leak: every value in the secrets folder must be absent from the bundle.
leak=0
for f in "${VAL_SECRETS}"/*; do
  [[ -f "$f" ]] || continue
  while IFS= read -r v; do
    [[ ${#v} -ge 16 ]] || continue
    if grep -rqF -- "$v" "$out"; then leak=1; fi
  done < <(python3 - "$f" <<'EOF'
import json, sys
text = open(sys.argv[1]).read().strip()
try:
    doc = json.loads(text)
    # a minted signal token: the token and the url carrying it are secret; its id and recognizer are not
    vals = [doc[k] for k in ("token", "url") if isinstance(doc, dict) and isinstance(doc.get(k), str)]
except ValueError:
    vals = [text]
print("\n".join(vals))
EOF
)
done
if (( leak )); then
  rm -rf "$out"
  die "a secret value was found in the collected files; the bundle was deleted. Inspect ${VAL_LOGS} by hand."
fi
tar -C "${VAL_DIR}" -czf "${out}.tar.gz" "$(basename "$out")" && rm -rf "$out"
say "Bundle: ${out}.tar.gz (no secrets folder; checked for secret values)"
