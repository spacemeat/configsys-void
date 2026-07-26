#!/usr/bin/env bash
# Name-existence sweep for Void (see configsys core docs/name-sweep-test.md). Resolves the whole
# component catalog on this plugin and checks every xbps package name it maps to actually exists in
# Void's repos. Void ships two libc flavors — glibc and musl — and this sweeps BOTH: the xbps names
# are libc-agnostic, so a rename upstream turns the sweep red for whichever flavor it lands on.
#
# Needs podman and a configsys checkout. Point CONFIGSYS_REPO at it, or place this repo beside it
# (../configsys).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(dirname "$here")"
repo="${CONFIGSYS_REPO:-$plugin_root/../configsys}"
py="$repo/.venv/bin/python"; [ -x "$py" ] || py=python3

sweep() {  # <os-context> <image>
    "$py" "$repo/tools/namesweep.py" --sweep \
        --plugin "$plugin_root/routes.hu" \
        --context "$1" --manager xbps --image "$2" \
        --setup "$here/void-repo-setup.sh" \
        --allowlist "$here/namesweep-allowlist.hu"
}

sweep void       ghcr.io/void-linux/void-glibc:latest
sweep void_musl  ghcr.io/void-linux/void-musl:latest
