import math

from omarum.orbshapes import glow_layers, line_paths, normalize_style, ring_points

SIZE = 160
C = SIZE / 2


def _radii(points):
    return [math.hypot(x - C, y - C) for x, y in points]


def test_normalize_style():
    assert normalize_style("lines") == "lines"
    assert normalize_style("Sparkles") == "glow"


def test_glow_has_four_closed_layers():
    layers = glow_layers(1.0, 0.5, SIZE)
    assert len(layers) == 4 and all(len(l) == 91 for l in layers)
    for l in layers:
        assert math.isclose(l[0][0], l[-1][0], abs_tol=1e-6) and math.isclose(l[0][1], l[-1][1], abs_tol=1e-6)


def test_glow_grows_with_energy():
    assert max(_radii(glow_layers(1.0, 1.0, SIZE)[0])) > max(_radii(glow_layers(1.0, 0.0, SIZE)[0]))


def test_glow_fits_box():
    for layer in glow_layers(2.0, 1.0, SIZE):
        assert all(0 <= x <= SIZE and 0 <= y <= SIZE for x, y in layer)


def test_lines_are_five_and_flat_when_quiet():
    paths = line_paths(1.0, 0.0, SIZE)
    assert len(paths) == 5
    assert max(abs(y - C) for p in paths for _, y in p) < SIZE * 0.05


def test_ring_radius_stays_near_base():
    radii = _radii(ring_points(1.0, 0.0, SIZE))
    assert len(radii) == 181
    assert all(abs(r - SIZE * 0.34) <= SIZE * 0.02 for r in radii)
