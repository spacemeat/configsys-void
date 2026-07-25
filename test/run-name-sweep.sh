#!/usr/bin/env bash
# Name-existence sweep for the Void OS (see configsys core docs/name-sweep-test.md). Resolves the
# whole component catalog on `void` with this plugin loaded and checks every xbps package name it
# maps to actually exists in Void's repos (ghcr.io/void-linux/void-glibc). This is what keeps the
# plugin's `component-names:` map honest as Void rolls: a rename upstream turns the sweep red.
#
# Needs podman and a configsys checkout. Point CONFIGSYS_REPO at it, or place this repo beside it
# (../configsys). Void has both glibc and musl variants; this targets glibc (matches `using: linux`).
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(dirname "$here")"
repo="${CONFIGSYS_REPO:-$plugin_root/../configsys}"
py="$repo/.venv/bin/python"; [ -x "$py" ] || py=python3

exec "$py" "$repo/tools/namesweep.py" --sweep \
    --plugin "$plugin_root/routes.hu" \
    --context void --manager xbps \
    --image ghcr.io/void-linux/void-glibc:latest \
    --setup "$here/void-repo-setup.sh" \
    --allowlist "$here/namesweep-allowlist.hu"
