from omarum.orbplace import anchors, clamp_size, dims_screen, normalize_position


def test_unknown_position_falls_back():
    assert normalize_position("upside-down") == "top-right"
    assert normalize_position("center") == "center"


def test_anchor_table():
    edges = lambda p: {k for k in ("top", "bottom", "left", "right") if anchors(p)[k]}
    assert edges("top-right") == {"top", "right"}
    assert edges("top-left") == {"top", "left"}
    assert edges("top-center") == {"top"}
    assert edges("bottom-center") == {"bottom"}
    assert edges("center") == set()
    assert anchors("top-right")["margin"] == 16


def test_clamp_size():
    assert clamp_size(20) == 96
    assert clamp_size(999) == 320
    assert clamp_size("big") == 160
    assert clamp_size(200) == 200


def test_only_center_dims():
    assert dims_screen("center")
    assert not any(dims_screen(p) for p in ("top-right", "top-left", "top-center", "bottom-center"))
