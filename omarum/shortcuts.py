"""Rum's keyboard shortcuts in Hyprland (via Omarchy's o.bind / o.bind_hold). Stdlib only."""

from __future__ import annotations

import json
import subprocess

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
