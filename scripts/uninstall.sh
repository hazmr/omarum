#!/usr/bin/env bash
# Remove what scripts/install.sh added, and only that.
# Your conversations, memory, models and settings are kept unless you pass --purge.
#
#   scripts/uninstall.sh [--purge]
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
purge=0
for arg in "$@"; do
  case "$arg" in
    --purge) purge=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

config="${XDG_CONFIG_HOME:-$HOME/.config}"
share="${XDG_DATA_HOME:-$HOME/.local/share}"
units="$config/systemd/user"
say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
# Runs before the omarum tool is removed (last step); stdlib only, so the system Python works too.
integ() { PYTHONPATH="$repo" python3 -m omarum.integration "$@"; }

say "Services"
systemctl --user disable --now omarum-orb.service omarum.service 2>/dev/null || true
rm -f "$units/omarum.service" "$units/omarum-orb.service"
systemctl --user daemon-reload

say "Bar button"
omarchy plugin disable omarum.panel >/dev/null 2>&1 || true
for plugin in "$config/omarchy/plugins/omarum.panel" "$config/omarchy/plugins/omarum"; do
  if [ -L "$plugin" ] && [ "$(readlink -f "$plugin")" = "$repo/bar/omarum" ]; then
    rm "$plugin"
  fi
done
omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true

say "Omarchy menu entries"
integ menu-remove "$config/omarchy/extensions/omarchy-menu.jsonc"

say "App launcher entry"
rm -f "$share/applications/omarum.desktop"
update-desktop-database "$share/applications" >/dev/null 2>&1 || true

say "Theme hook"
hook="$config/omarchy/hooks/theme-set.d/50-omarum"
if [ -f "$hook" ] && grep -q "Added by Omarum" "$hook"; then rm "$hook"; fi

say "Keyboard shortcuts"
integ unrequire "$config/hypr/bindings.lua"
if [ -f "$config/hypr/omarum.lua" ] && head -1 "$config/hypr/omarum.lua" | grep -q "Written by Omarum"; then
  rm "$config/hypr/omarum.lua"
fi
hyprctl reload >/dev/null 2>&1 || true

say "The omarum command"
uv tool uninstall omarum >/dev/null 2>&1 || true

if [ "$purge" = 1 ]; then
  say "Purging conversations, memory, models and settings"
  rm -rf "$share/omarum" "$config/omarum" "$HOME/.local/state/omarum"
else
  echo "Kept your data: $share/omarum (conversations, memory, models) and $config/omarum (settings)."
  echo "Run with --purge to delete them too."
fi
