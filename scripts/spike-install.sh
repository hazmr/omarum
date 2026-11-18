#!/usr/bin/env bash
# Omarum spike: put `omarum` on PATH, bind a talk shortcut, start the daemon and the orb.
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
hypr="$HOME/.config/hypr"

uv tool install --quiet --force --editable "$repo"
omarum_bin="$(command -v omarum || echo "$HOME/.local/bin/omarum")"

# Pick a free shortcut: SUPER+H, else SUPER+ALT+H.
key="SUPER + H"
if hyprctl binds -j | python3 -c 'import json,sys; sys.exit(0 if any(b["modmask"]==64 and b["key"].lower()=="h" and b.get("description")!="Talk to Rum" for b in json.load(sys.stdin)) else 1)'; then
  key="SUPER + ALT + H"
fi

cat > "$hypr/omarum.lua" <<LUA
-- Added by Omarum (spike). Remove this file and the require line in bindings.lua to undo.
o.bind("$key", "Talk to Rum", "$omarum_bin toggle")
LUA
grep -q 'hypr.omarum' "$hypr/bindings.lua" || printf '\n-- Omarum voice companion\npcall(require, "hypr.omarum")\n' >> "$hypr/bindings.lua"
hyprctl reload >/dev/null

# (Re)start the daemon and the orb in the background.
pkill -f "^[^ ]*python[^ ]* [^ ]*/bin/omarum daemon" 2>/dev/null || true
pkill -f "^/usr/bin/python3 [^ ]*/orb/omarum_orb.py" 2>/dev/null || true
mkdir -p "$HOME/.local/state/omarum"
uwsm app -- "$omarum_bin" daemon >"$HOME/.local/state/omarum/daemon.log" 2>&1 &
uwsm app -- "$repo/bin/omarum-orb" >"$HOME/.local/state/omarum/orb.log" 2>&1 &
echo "Omarum ready. Press $key to talk to Rum. Logs: ~/.local/state/omarum/"
