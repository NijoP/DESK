# Shared by the DESK x Weft Linux validation scripts. Source it; do not run it.
# Every fact about Weft used here was read from the pinned upstream source; docs/weft/05_LINUX_VALIDATION.md cites where.
set -euo pipefail

DESK_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LINUX_DIR="${DESK_REPO}/integrations/weft/linux"
WEFT_DIR="${WEFT_DIR:-$HOME/weft}"
WEFT_REPO_URL="https://github.com/WeaveMindAI/weft.git"
VAL_DIR="${DESK_VALIDATION_DIR:-$HOME/desk-weft-validation}"
VAL_PROJECTS="${VAL_DIR}/projects"
VAL_PROJECT="${DESK_VALIDATION_PROJECT:-WEFTVAL01}"
VAL_LOGS="${VAL_DIR}/logs"
VAL_SECRETS="${VAL_DIR}/secrets"
RESULTS="${VAL_DIR}/results.tsv"
DISPATCHER="${DESK_WEFT_DISPATCHER:-http://127.0.0.1:14111}"
SERVICE_PORT="${DESK_WEFT_SERVICE_PORT:-14500}"
SERVICE_URL="http://127.0.0.1:${SERVICE_PORT}"
CONNECTION_LABEL="desk-node-service"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
# The checkout sits on a detached HEAD at the pin, and a weft checkout's branch is what picks an install; upstream's
# own answer for that case is WEFT_INSTALL (crates/weft-core/src/infra/install.rs, on_no_branch). `default` is the
# install whose `weft` is linked on PATH.
export WEFT_INSTALL=default

mkdir -p "${VAL_PROJECTS}"
install -d -m 700 "${VAL_LOGS}"
install -d -m 700 "${VAL_SECRETS}"

PIN="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "${DESK_REPO}/integrations/weft/WEFT_PIN.json")"

say()  { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }
warn() { printf '   WARNING: %s\n' "$*" >&2; }
die()  { printf '   STOP: %s\n' "$*" >&2; exit 1; }

# record <step> <PASS|FAIL|NOT RUN|BLOCKED> <detail>: one line per check in results.tsv. Never PASS without evidence.
record() {
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${3:-}" >> "${RESULTS}"
  printf '   [%s] %s %s\n' "$2" "$1" "${3:+- $3}"
}

need() { command -v "$1" >/dev/null 2>&1 || die "$1 is not installed (run 10_install_prereqs.sh first)"; }

desk() { (cd "${DESK_REPO}" && python3 tools/desk.py "$@"); }

# A step that needs an explicit go-ahead because it changes the machine.
require_yes() {
  [[ " $* " == *" --yes "* ]] || die "this step changes the machine; read what it does above, then re-run it with --yes"
}

# The secret files: created once, readable by this user only, never printed.
secret_file() { # name generator-command
  local f="${VAL_SECRETS}/$1"
  if [[ ! -s "$f" ]]; then
    (umask 077; eval "$2" > "$f")
  fi
  chmod 600 "$f"
  printf '%s' "$f"
}

# Where the staged workflow project lives (the folder `weft` commands run in).
staged_dir() { # workflow
  (cd "${DESK_REPO}" && python3 - "$1" <<'EOF'
import sys
sys.path.insert(0, ".")
from desk.weft import staging
print(staging.stage(sys.argv[1]))
EOF
  )
}

weft_wait() { # run-id timeout [--waiting-for-input]; echoes weft wait's exit code (0 done, 10 failed, 11 parked, 12 running)
  local rc=0
  weft wait "$1" --timeout "$2" ${3:-} >/dev/null 2>&1 || rc=$?
  printf '%s' "$rc"
}
