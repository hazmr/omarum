"""Orb colors from the active Omarchy theme. Stdlib only (the orb uses system Python)."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

RGB = tuple[float, float, float]

# palette key -> Omarchy colors.toml key
KEYS = {"user": "accent", "companion": "magenta", "idle": "muted", "error": "red", "background": "background"}


def _hex(value: str) -> RGB:
    v = value.strip().lstrip("#")
    if len(v) != 6:
        raise ValueError(value)
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


# Last Horizon, used whenever the theme can't be read.
FALLBACK: dict[str, RGB] = {
    "user": _hex("#b59790"),
    "companion": _hex("#c4d8e2"),
    "idle": _hex("#584e51"),
    "error": _hex("#c38b7b"),
    "background": _hex("#0c0b0c"),
}


def _current_theme_dir() -> Path | None:
    if shutil.which("omarchy") is None:
        return None
    try:
        name = subprocess.run(["omarchy", "theme", "current"], capture_output=True, text=True, timeout=3).stdout.strip()
        out = subprocess.run(["omarchy", "theme", "dir", name], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return existing_theme_dir(Path(out)) if out else None


def existing_theme_dir(path: Path) -> Path | None:
    """`omarchy theme dir` may print the display name ("Last Horizon"); folders are slugs."""
    if path.is_dir():
        return path
    slug = path.with_name(path.name.lower().replace(" ", "-"))
    return slug if slug.is_dir() else None


def load_palette(theme_dir: Path | None = None) -> dict[str, RGB]:
    palette = dict(FALLBACK)
    theme_dir = theme_dir or _current_theme_dir()
    if theme_dir is None:
        return palette
    try:
        colors = tomllib.loads((theme_dir / "colors.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return palette
    for key, toml_key in KEYS.items():
        try:
            palette[key] = _hex(colors[toml_key])
        except (KeyError, ValueError, TypeError, AttributeError):
            pass
    return palette


def vivid(rgb: RGB, boost: float = 2.2, min_saturation: float = 0.45) -> RGB:
    """Same hue, more color: pastel theme colors read as gray on a glowing orb."""
    import colorsys

    h, l, s = colorsys.rgb_to_hls(*rgb)
    s = min(1.0, max(s * boost, min_saturation))
    l = min(l, 0.72)
    return colorsys.hls_to_rgb(h, l, s)


def state_color(state: str, palette: dict[str, RGB]) -> RGB:
    return {
        "user_speaking": vivid(palette["user"]),
        "speaking": vivid(palette["companion"]),
        "error": vivid(palette["error"]),
    }.get(state, palette["idle"])


def _preset(user: str, companion: str) -> dict[str, RGB]:
    return {"user": _hex(user), "companion": _hex(companion), "idle": _hex("#5a5a5a"),
            "error": _hex("#e57373"), "background": _hex("#000000")}


PRESETS: dict[str, dict[str, RGB]] = {
    "warm": _preset("#ff8a65", "#ffb74d"),
    "glass": _preset("#9ad1ff", "#e0f2ff"),
    "mono": _preset("#e0e0e0", "#ffffff"),
}


def palette_for(colors: str) -> dict[str, RGB]:
    """'theme' (live Omarchy palette) or a built-in preset; anything unknown follows the theme."""
    return dict(PRESETS[colors]) if colors in PRESETS else load_palette()
