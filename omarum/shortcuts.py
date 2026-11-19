"""Rum's keyboard shortcuts in Hyprland (via Omarchy's o.bind / o.bind_hold). Stdlib only."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

MOD_ORDER = ("SUPER", "CTRL", "ALT", "SHIFT")
MOD_BITS = {"SHIFT": 1, "CTRL": 4, "ALT": 8, "SUPER": 64}
ALIASES = {"CONTROL": "CTRL", "WIN": "SUPER", "META": "SUPER", "ENTER": "RETURN", "ESC": "ESCAPE"}
OUR_DESCRIPTIONS = ("Talk to Rum", "Omarum settings")

# Common app shortcuts a desktop-wide bind would take away from them.
APP_CONFLICTS = {
    "CTRL + SHIFT + SPACE": "IntelliJ: smart code completion",
    "ALT + RETURN": "IntelliJ: quick fix",
    "CTRL + SHIFT + RETURN": "IntelliJ: complete statement",
    "CTRL + SHIFT + T": "Browsers: reopen closed tab",
    "CTRL + SHIFT + Z": "Most apps: redo",
    "CTRL + SHIFT + C": "Terminals: copy",
    "CTRL + SHIFT + V": "Terminals: paste",
    "CTRL + SHIFT + ESCAPE": "Task manager (common)",
}

HYPR_DIR = Path.home() / ".config" / "hypr"


def normalize(combo: str) -> str:
    parts = [p.strip().upper() for p in combo.replace("+", " ").split() if p.strip()]
    parts = [ALIASES.get(p, p) for p in parts]
    mods = [m for m in MOD_ORDER if m in parts]
    keys = [p for p in parts if p not in MOD_BITS]
    return " + ".join(mods + keys[-1:]) if keys else ""


def _mask_and_key(combo: str) -> tuple[int, str]:
    parts = normalize(combo).split(" + ")
    return sum(MOD_BITS[p] for p in parts[:-1]), parts[-1].lower()


def conflicts(combo: str, binds: list[dict]) -> list[str]:
    combo = normalize(combo)
    if not combo:
        return []
    mask, key = _mask_and_key(combo)
    found = [
        b.get("description") or b.get("dispatcher", "another shortcut")
        for b in binds
        if b.get("modmask") == mask and str(b.get("key", "")).lower() == key
        and not str(b.get("description", "")).startswith(OUR_DESCRIPTIONS)
    ]
    if combo in APP_CONFLICTS:
        found.append(APP_CONFLICTS[combo])
    return found


def current_binds() -> list[dict]:
    try:
        return json.loads(subprocess.run(["hyprctl", "binds", "-j"], capture_output=True, text=True, timeout=3).stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def to_lua(cfg, omarum_bin: str) -> str:
    lines = ["-- Written by Omarum (change these in `omarum settings`, not here)."]
    talk = normalize(cfg.talk_shortcut)
    if talk:
        lines.append(f'o.bind_hold("{talk}", "Talk to Rum (hold) / hands-free (tap)", "{omarum_bin} ptt_down", '
                     f'"Talk to Rum: release", "{omarum_bin} ptt_up")')
    settings = normalize(cfg.settings_shortcut)
    if settings:
        lines.append(f'o.bind("{settings}", "Omarum settings", "{omarum_bin} settings")')
    return "\n".join(lines) + "\n"


def apply(cfg, omarum_bin: str, hypr_dir: Path = HYPR_DIR) -> None:
    """Write ~/.config/hypr/omarum.lua, load it from bindings.lua once, reload Hyprland."""
    (hypr_dir / "omarum.lua").write_text(to_lua(cfg, omarum_bin))
    bindings = hypr_dir / "bindings.lua"
    text = bindings.read_text() if bindings.exists() else ""
    if "hypr.omarum" not in text:
        bindings.write_text(text + '\n-- Omarum voice companion\npcall(require, "hypr.omarum")\n')
    subprocess.run(["hyprctl", "reload"], capture_output=True, timeout=10)
