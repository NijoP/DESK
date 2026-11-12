#!/usr/bin/env bash
# Step 0: read-only checks. Changes nothing on the machine.
source "$(dirname "$0")/common.sh"

say "Preflight (read-only) for the DESK x Weft validation at pin ${PIN:0:12}"
hard=0

[[ "$(uname -s)" == "Linux" ]] && record preflight.os PASS "$(uname -sr)" || { record preflight.os FAIL "not Linux"; hard=1; }
if grep -qi microsoft /proc/version 2>/dev/null; then
  warn "this is WSL. The procedure targets a separate Linux machine; under WSL keep DESK and Weft in the Linux home, never under /mnt"
fi
case "$(uname -m)" in
  x86_64|aarch64) record preflight.arch PASS "$(uname -m)" ;;
  *) record preflight.arch FAIL "$(uname -m): upstream publishes and tests x86_64 and aarch64 Linux"; hard=1 ;;
esac
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" == "ubuntu" && "${VERSION_ID:-}" == "24.04" ]]; then
    record preflight.distro PASS "${PRETTY_NAME}"
  else
    record preflight.distro PASS "${PRETTY_NAME:-unknown} (procedure written for Ubuntu 24.04; apt steps may differ)"
  fi
fi
case "${DESK_REPO}" in /mnt/*) record preflight.repo_path FAIL "DESK is under /mnt; Weft refuses Windows drives"; hard=1 ;; *) record preflight.repo_path PASS "${DESK_REPO}" ;; esac

free_gb=$(( $(df -Pk "$HOME" | awk 'NR==2 {print $4}') / 1024 / 1024 ))
if (( free_gb >= 40 )); then record preflight.disk PASS "${free_gb} GB free in \$HOME"
else record preflight.disk FAIL "${free_gb} GB free; a from-source Weft build plus Docker images needs about 40 GB"; hard=1; fi
mem_gb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
(( mem_gb >= 8 )) && record preflight.memory PASS "${mem_gb} GB" || record preflight.memory PASS "${mem_gb} GB (under 8 GB: the Rust build will be slow)"

for tool in git curl python3; do
  command -v "$tool" >/dev/null && record "preflight.$tool" PASS "$(command -v "$tool")" || { record "preflight.$tool" FAIL "missing"; hard=1; }
done
python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' \
  && record preflight.python_version PASS "$(python3 -V 2>&1)" || { record preflight.python_version FAIL "DESK needs Python 3.9+"; hard=1; }
command -v cc >/dev/null && record preflight.c_compiler PASS "$(cc --version | head -1)" || record preflight.c_compiler "NOT RUN" "no C compiler yet (10_install_prereqs.sh installs build-essential)"
command -v rustup >/dev/null && record preflight.rustup PASS "$(rustup --version 2>/dev/null | head -1)" || record preflight.rustup "NOT RUN" "rustup not installed yet"

if command -v docker >/dev/null; then
  if v="$(docker version --format '{{.Server.Version}}' 2>/dev/null)"; then
    major="${v%%.*}"
    (( major >= 23 )) && record preflight.docker PASS "engine ${v}" || { record preflight.docker FAIL "engine ${v}; setup.sh needs >= 23 for its safe volume prune"; hard=1; }
  else
    record preflight.docker FAIL "docker is installed but this user cannot reach the engine (in the docker group? logged in again?)"; hard=1
  fi
else
  record preflight.docker "NOT RUN" "Docker Engine not installed yet"
fi

for port in 14111 "${SERVICE_PORT}"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null; then
    info "port ${port} is already answering (an existing Weft install or DESK service?)"
  fi
done

if [[ -d "${WEFT_DIR}/.git" ]]; then
  head="$(git -C "${WEFT_DIR}" rev-parse HEAD)"
  [[ "$head" == "$PIN" ]] && record preflight.weft_checkout PASS "${WEFT_DIR} at the pin" \
    || warn "${WEFT_DIR} is at ${head:0:12}, not the pin; 20_install_weft.sh checks out the pin and refuses a dirty tree"
fi
if command -v weft >/dev/null; then
  info "a weft command already exists: $(command -v weft) ($(weft --version 2>/dev/null || echo 'version unknown'))"
  warn "20_install_weft.sh reinstalls the DEFAULT install; on a machine with Weft work of its own, use a separate machine"
fi

if [[ -n "$(git -C "${DESK_REPO}" status --porcelain 2>/dev/null)" ]]; then
  warn "the DESK checkout has local changes; the validation records the commit it ran against: $(git -C "${DESK_REPO}" rev-parse --short HEAD)"
fi

(( hard == 0 )) && { say "Preflight passed"; exit 0; } || { say "Preflight found a hard problem (see FAIL lines)"; exit 1; }
