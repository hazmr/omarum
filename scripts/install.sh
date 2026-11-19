#!/usr/bin/env bash
# Install Omarum for this user: the `omarum` command, models, shortcuts, theme hook,
# systemd user services, app launcher entry, Omarchy menu entries and bar button.
# Safe to run again: every step checks first and never touches other people's entries.
#
#   scripts/install.sh [--with-zonos3]
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
with_zonos3=0
for arg in "$@"; do
  case "$arg" in
    --with-zonos3) with_zonos3=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

config="${XDG_CONFIG_HOME:-$HOME/.config}"
data="${XDG_DATA_HOME:-$HOME/.local/share}/omarum"
state="$HOME/.local/state/omarum"
models="$data/models"
units="$config/systemd/user"
say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
integ() { uv run --project "$repo" --quiet python -m omarum.integration "$@"; }

say "Installing the omarum command"
uv tool install --quiet --force --editable "$repo"
omarum_bin="$(command -v omarum || echo "$HOME/.local/bin/omarum")"
mkdir -p "$state"
chmod 700 "$state"

say "Models (skipped when already downloaded)"
whisper() {  # $1 = faster-whisper model name
  if [ -f "$models/whisper/$1/model.bin" ]; then echo "    whisper $1: present"; return; fi
  echo "    whisper $1: downloading"
  uv run --project "$repo" --quiet python -c \
    "import sys; from faster_whisper import download_model; download_model(sys.argv[1], output_dir=sys.argv[2])" \
    "$1" "$models/whisper/$1"
}
whisper base.en
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L 2>/dev/null | grep -q GPU; then
  whisper large-v3-turbo
fi
kokoro="$models/kokoro"
kokoro_url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
mkdir -p "$kokoro"
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  if [ -s "$kokoro/$f" ]; then echo "    kokoro $f: present"; continue; fi
  echo "    kokoro $f: downloading"
  curl -fL --progress-bar -o "$kokoro/$f.part" "$kokoro_url/$f"
  mv "$kokoro/$f.part" "$kokoro/$f"
done

if [ "$with_zonos3" = 1 ]; then
  say "ZONOS3-Mini voice (optional local engine)"
  engine="$data/engines/zonos3"
  ggml="$engine/servers/ggml"
  for tool in git cmake cargo; do
    command -v "$tool" >/dev/null || { echo "ZONOS3 needs '$tool' to build; install it and run again." >&2; exit 1; }
  done
  [ -d "$engine/.git" ] || git clone --recursive https://github.com/Zyphra/ZONOS3-Mini.git "$engine"
  git -C "$engine" submodule update --init --recursive --quiet
  if [ ! -x "$ggml/build-vulkan/zonos3-server" ] && [ ! -x "$ggml/build/zonos3-server" ]; then
    if (cd "$ggml" && cmake -B build-vulkan -DGGML_VULKAN=ON -DCMAKE_BUILD_TYPE=Release >build-vulkan.log 2>&1 \
          && cmake --build build-vulkan -j --target zonos3-server >>build-vulkan.log 2>&1); then
      echo "    built for the GPU (Vulkan)"
    else
      echo "    Vulkan build failed (see $ggml/build-vulkan.log); building for the CPU"
      rm -rf "$ggml/build-vulkan"
      (cd "$ggml" && cmake -B build -DCMAKE_BUILD_TYPE=Release >build-cpu.log 2>&1 \
         && cmake --build build -j --target zonos3-server >>build-cpu.log 2>&1)
    fi
  else
    echo "    server: present"
  fi
  if [ ! -f "$ggml/gguf/backbone-ptq.gguf" ] || [ ! -d "$ggml/gguf/voices" ]; then
    (cd "$ggml" && uvx --quiet --from huggingface_hub hf download Zyphra/ZONOS3-Mini \
       gguf/backbone-ptq.gguf gguf/zac-keep2.gguf gguf/spk-encoder.gguf gguf/steer.gguf --local-dir . \
     && uvx --quiet --from huggingface_hub hf download Zyphra/ZONOS3-Mini --include 'gguf/voices/*' --local-dir .)
  else
    echo "    model files: present"
  fi
fi

say "Keyboard shortcuts (from ~/.config/omarum/config.toml)"
"$omarum_bin" shortcuts

say "Theme hook: the orb follows Omarchy theme changes"
hookdir="$config/omarchy/hooks/theme-set.d"
mkdir -p "$hookdir"
printf '#!/bin/sh\n# Added by Omarum: refresh the orb colors when the Omarchy theme changes.\n"%s" reload >/dev/null 2>&1 || true\n' \
  "$omarum_bin" > "$hookdir/50-omarum"
chmod +x "$hookdir/50-omarum"

say "Stopping any earlier copy (spike loop or old services)"
systemctl --user stop omarum-orb.service omarum.service 2>/dev/null || true
pkill -f "^[^ ]*sh -c while true; do .*omarum.* daemon" 2>/dev/null || true
pkill -f "^[^ ]*python[^ ]* [^ ]*/bin/omarum daemon" 2>/dev/null || true
pkill -f "^/usr/bin/python3 [^ ]*/orb/omarum_orb.py" 2>/dev/null || true
pkill -f "^[^ ]*/zonos3-server " 2>/dev/null || true
sleep 1

say "Services: start at login, restart after a crash"
for unit in omarum.service omarum-orb.service; do
  integ unit "$repo/packaging/systemd/$unit" "$units/$unit" "$repo" "$omarum_bin"
done
systemctl --user daemon-reload
systemctl --user enable --quiet omarum.service omarum-orb.service
systemctl --user restart omarum.service omarum-orb.service

say "App launcher entry"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$apps"
install -m 644 "$repo/packaging/omarum.desktop" "$apps/omarum.desktop"
update-desktop-database "$apps" >/dev/null 2>&1 || true

say "Omarchy menu entries"
integ menu-add "$config/omarchy/extensions/omarchy-menu.jsonc"

say "Bar button"
plugin="$config/omarchy/plugins/omarum"
mkdir -p "$config/omarchy/plugins"
if [ -L "$plugin" ] && [ "$(readlink -f "$plugin")" = "$repo/bar/omarum" ]; then
  echo "    plugin link: present"
elif [ -e "$plugin" ] || [ -L "$plugin" ]; then
  echo "    $plugin already exists and is not Omarum's link; left alone" >&2
else
  ln -s "$repo/bar/omarum" "$plugin"
fi
omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
sleep 1
if omarchy plugin list 2>/dev/null | grep -q '^omarum.panel .*enabled'; then
  echo "    omarum.panel: enabled"
else
  omarchy plugin enable omarum.panel || echo "    could not enable the bar button; run: omarchy plugin enable omarum.panel" >&2
fi

say "Done"
echo "Hold Ctrl+Shift+Space to talk to Rum (tap it for hands-free), or click the orb in the bar."
echo "Settings: omarum settings · Logs: journalctl --user -u omarum -u omarum-orb"
