"""The orb's three styles as pure point lists (ported from the approved mockup). Stdlib only."""

from __future__ import annotations

import math

STYLES = ("glow", "lines", "ring")
Point = tuple[float, float]


def normalize_style(name: str) -> str:
    return name if name in STYLES else "glow"


def glow_layers(t: float, e: float, size: float, breathe: float = 1.0) -> list[list[Point]]:
    """Four wobbling blobs, outermost first ("Breathing glow")."""
    c, base = size / 2, size * 0.29
    layers = []
    for layer in range(3, -1, -1):
        rb = base * (0.55 + layer * 0.12) * breathe * (1 + 0.04 * math.sin(t * 1.3)) + e * size * 0.05
        pts = []
        for i in range(91):
            a = i / 90 * 2 * math.pi
            wob = (math.sin(a * 3 + t * 1.7 + layer) * 0.5
                   + math.sin(a * 5 - t * 2.3 + layer * 2) * 0.35
                   + math.sin(a * 2 + t * 0.8) * 0.4)
            r = rb + wob * (size * 0.0125 + e * size * 0.0625) * (1 + layer * 0.3)
            pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
        layers.append(pts)
    return layers


def line_paths(t: float, e: float, size: float) -> list[list[Point]]:
    """Five soft lines drifting across the circle ("Flowing lines")."""
    c, radius, step = size / 2, size * 0.42, size / 80
    paths = []
    for k in range(5):
        amp = (size * 0.04 + e * size * 0.44) * (1 - abs(k - 2) / 5)
        freq, phase = 1.6 + k * 0.35, t * (1.2 + k * 0.25) + k
        pts, x = [], -radius
        while x <= radius + 1e-9:
            env = math.cos(x / radius * math.pi / 2) ** 2
            pts.append((c + x, c + math.sin(x / radius * math.pi * freq + phase) * amp * env))
            x += step
        paths.append(pts)
    return paths


def ring_points(t: float, e: float, size: float) -> list[Point]:
    """A thin ring whose edge is the waveform ("Sound ring")."""
    c, radius = size / 2, size * 0.34
    pts = []
    for i in range(181):
        a = i / 180 * 2 * math.pi - math.pi / 2
        n = math.sin(a * 8 + t * 4) * math.sin(a * 3 - t * 2.2) + 0.5 * math.sin(a * 13 + t * 6)
        r = radius + n * (size * 0.01 + e * size * 0.16)
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    return pts
