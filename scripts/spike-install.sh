#!/usr/bin/env bash
# Omarum spike: put `omarum` on PATH, bind a talk shortcut, start the daemon and the orb.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
hypr="$HOME/.config/hypr"

uv tool install --quiet --force --editable "$repo"
omarum_bin="$(command -v omarum || echo "$HOME/.local/bin/omarum")"

# Keyboard shortcuts come from config.toml (default: hold Ctrl+Shift+Space to talk, tap for hands-free).
"$omarum_bin" shortcuts

# Follow Omarchy theme changes: the theme-set hook asks the orb to reload its colors.
hookdir="$HOME/.config/omarchy/hooks/theme-set.d"
mkdir -p "$hookdir"
printf '#!/bin/sh\n# Added by Omarum: refresh the orb colors when the Omarchy theme changes.\n"%s" reload >/dev/null 2>&1 || true\n' "$omarum_bin" > "$hookdir/50-omarum"
chmod +x "$hookdir/50-omarum"

# (Re)start the daemon and the orb in the background.
pkill -f "^[^ ]*sh -c while true; do .*omarum.* daemon" 2>/dev/null || true
pkill -f "^[^ ]*python[^ ]* [^ ]*/bin/omarum daemon" 2>/dev/null || true
pkill -f "^/usr/bin/python3 [^ ]*/orb/omarum_orb.py" 2>/dev/null || true
pkill -f "^[^ ]*/zonos3-server " 2>/dev/null || true
sleep 1
mkdir -p "$HOME/.local/state/omarum"
# Keep the daemon alive: if it ever crashes, restart it a second later.
uwsm app -- sh -c "while true; do \"$omarum_bin\" daemon >>\"$HOME/.local/state/omarum/daemon.log\" 2>&1; echo \"[omarum] daemon exited (\$?), restarting\" >>\"$HOME/.local/state/omarum/daemon.log\"; sleep 1; done" >/dev/null 2>&1 &
uwsm app -- "$repo/bin/omarum-orb" >"$HOME/.local/state/omarum/orb.log" 2>&1 </dev/null &
echo "Omarum ready. Hold Ctrl+Shift+Space to talk (tap it for hands-free). Settings: omarum settings. Logs: ~/.local/state/omarum/"
