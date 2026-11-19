"""Where the orb sits and how big it is. Stdlib only."""

from __future__ import annotations

POSITIONS = ("top-right", "top-center", "top-left", "center", "bottom-center")
MARGIN = 16
MIN_SIZE, MAX_SIZE, DEFAULT_SIZE = 96, 320, 160

_EDGES = {
    "top-right": {"top", "right"},
    "top-left": {"top", "left"},
    "top-center": {"top"},
    "bottom-center": {"bottom"},
    "center": set(),
}


def normalize_position(name: str) -> str:
    return name if name in POSITIONS else "top-right"


def clamp_size(px) -> int:
    try:
        return max(MIN_SIZE, min(MAX_SIZE, int(px)))
    except (TypeError, ValueError):
        return DEFAULT_SIZE


def anchors(position: str) -> dict:
    edges = _EDGES[normalize_position(position)]
    return {**{e: e in edges for e in ("top", "bottom", "left", "right")}, "margin": MARGIN}


def dims_screen(position: str) -> bool:
    return normalize_position(position) == "center"
