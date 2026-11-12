#!/usr/bin/env bash
# Step 2: the pinned Weft, built from source, as this machine's DEFAULT install. CHANGES THE MACHINE; needs --yes.
#
# Facts from the pinned source (setup.sh, crates/weft-core/src/infra/install.rs):
#   - The install a checkout drives is picked by its branch; a detached HEAD picks none, and upstream's answer is
#     WEFT_INSTALL=default (set in common.sh). Upstream's one-line installer always takes the tip of main, so it is
#     not used here.
#   - Prebuilt binaries exist only for the tree CI last published; the pin is older, so setup.sh compiles from
#     source (Rust 1.99.1 from rust-toolchain.toml, tens of minutes).
#   - On every install setup.sh reaps ORPHANED ANONYMOUS Docker volumes (`docker volume prune --force`, engine >= 23),
#     caps the BuildKit cache at 20 GB and removes Weft images nothing uses. Named volumes are left alone.
#     Run this on a machine whose Docker holds nothing you need to keep.
#   - CREDENTIAL_ENCRYPTION_KEY seals stored connections. Without it Weft uses a public development key. It is read
#     from the shell that starts the daemon and then kept in the install's secrets file (crates/weft-cli/src/commands/daemon.rs).
source "$(dirname "$0")/common.sh"

say "Install Weft ${PIN:0:12} into ${WEFT_DIR} as the default install"
require_yes "$@"
need git; need docker; need rustup; need python3
docker version --format '{{.Server.Version}}' >/dev/null 2>&1 || die "this user cannot reach the Docker engine (log in again after joining the docker group)"

if [[ ! -d "${WEFT_DIR}/.git" ]]; then
  git clone --quiet "${WEFT_REPO_URL}" "${WEFT_DIR}"
fi
origin="$(git -C "${WEFT_DIR}" remote get-url origin)"
[[ "$origin" == "${WEFT_REPO_URL}" || "$origin" == "${WEFT_REPO_URL%.git}" ]] || die "${WEFT_DIR} is a clone of ${origin}, not upstream Weft"
git -C "${WEFT_DIR}" cat-file -e "${PIN}^{commit}" 2>/dev/null || git -C "${WEFT_DIR}" fetch --quiet origin
[[ -z "$(git -C "${WEFT_DIR}" status --porcelain)" ]] || die "${WEFT_DIR} has local changes; refusing to build a modified Weft"
git -C "${WEFT_DIR}" checkout --quiet --detach "${PIN}"
[[ "$(git -C "${WEFT_DIR}" rev-parse HEAD)" == "${PIN}" ]] || die "checkout did not land on the pin"
record weft.checkout PASS "${WEFT_DIR} at ${PIN}"

keyfile="$(secret_file credential_encryption_key "python3 -c 'import base64,os; print(base64.b64encode(os.urandom(32)).decode())'")"
log="${VAL_LOGS}/setup.log"
info "building and starting Weft (log: ${log}); this compiles from source and takes a while"
if (cd "${WEFT_DIR}" && CREDENTIAL_ENCRYPTION_KEY="$(cat "${keyfile}")" ./setup.sh --cli --daemon --yes) >"${log}" 2>&1; then
  record weft.setup PASS "setup.sh --cli --daemon finished"
else
  record weft.setup FAIL "setup.sh failed; last lines of ${log}:"
  tail -n 40 "${log}" >&2
  exit 1
fi

command -v weft >/dev/null || die "weft is not on PATH after the install (expected ~/.local/bin/weft)"
record weft.version PASS "$(weft --version 2>&1 | head -1)"
status="$(weft daemon status 2>&1 || true)"
if grep -q "running at" <<<"$status"; then record weft.daemon PASS "$(head -1 <<<"$status")"
else record weft.daemon FAIL "$(head -1 <<<"$status")"; exit 1; fi

st="$(desk weft status --json || true)"
match="$(python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d["weft"].get("pinMatch"))' <<<"$st" 2>/dev/null || echo unknown)"
[[ "$match" == "True" ]] && record weft.pin_match PASS "DESK sees the pinned Weft" || { record weft.pin_match FAIL "desk weft status: pinMatch=${match}"; exit 1; }

say "Weft is installed. Next: 30_prepare_desk.sh"
