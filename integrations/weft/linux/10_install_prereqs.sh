#!/usr/bin/env bash
# Step 1: system prerequisites on Ubuntu 24.04. CHANGES THE MACHINE (apt, Docker, rustup); needs --yes and sudo.
#   - build tools (Weft's from-source build compiles C for `ring` and `zstd-sys`)
#   - Docker Engine from Docker's own apt repository (Weft runs Postgres and its object store in containers)
#   - rustup with NO default toolchain: Weft's rust-toolchain.toml (1.99.1 at the pin) selects and installs its own
#   - lingering for this user, so Weft's systemd --user service keeps running without an open login session
source "$(dirname "$0")/common.sh"

say "Prerequisites"
cat <<EOF
   This installs: git curl ca-certificates build-essential pkg-config python3 (apt);
                  docker-ce docker-ce-cli containerd.io docker-buildx-plugin (Docker's apt repo);
                  rustup (rustup.rs, no default toolchain); and adds ${USER} to the docker group.
EOF
require_yes "$@"
command -v apt-get >/dev/null || die "apt-get not found; this script is for Ubuntu/Debian. Install the same packages by hand."

sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential pkg-config python3
record prereqs.apt PASS "build tools installed"

if docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  record prereqs.docker PASS "already reachable: engine $(docker version --format '{{.Server.Version}}')"
else
  if ! command -v docker >/dev/null; then
    . /etc/os-release
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  fi
  sudo systemctl enable --now docker
  if ! id -nG "$USER" | grep -qw docker; then
    sudo usermod -aG docker "$USER"
    record prereqs.docker_group PASS "added ${USER} to the docker group"
    warn "log out and back in (or run: newgrp docker) before step 2, so this user can reach the engine"
  fi
  record prereqs.docker PASS "Docker Engine installed (re-login may be needed before it is reachable)"
fi

if ! command -v rustup >/dev/null; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain none --profile minimal --no-modify-path
  record prereqs.rustup PASS "rustup installed; the toolchain comes from Weft's rust-toolchain.toml"
else
  record prereqs.rustup PASS "already installed: $(rustup --version 2>/dev/null | head -1)"
fi
grep -q '.cargo/bin' "$HOME/.profile" 2>/dev/null || echo 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"' >> "$HOME/.profile"

if command -v loginctl >/dev/null; then
  sudo loginctl enable-linger "$USER" && record prereqs.linger PASS "systemd --user services survive logout"
fi

say "Prerequisites done. If you were added to the docker group, log in again, then run 00_preflight.sh"
