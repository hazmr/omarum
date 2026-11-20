from pathlib import Path

from omarum import theme

LH_ACCENT = (0xB5 / 255, 0x97 / 255, 0x90 / 255)


def test_fallback_when_omarchy_missing(monkeypatch):
    monkeypatch.setattr(theme.shutil, "which", lambda name: None)
    assert theme.load_palette()["user"] == LH_ACCENT


def test_parses_colors_toml(tmp_path: Path):
    (tmp_path / "colors.toml").write_text('accent = "#ff0000"\nmagenta = "#00ff00"\n')
    p = theme.load_palette(theme_dir=tmp_path)
    assert p["user"] == (1.0, 0.0, 0.0)
    assert p["companion"] == (0.0, 1.0, 0.0)
    assert p["error"] == theme.FALLBACK["error"]  # missing keys fall back


def test_bad_hex_falls_back(tmp_path: Path):
    (tmp_path / "colors.toml").write_text('accent = "nope"\n')
    assert theme.load_palette(theme_dir=tmp_path)["user"] == LH_ACCENT


def test_bad_toml_falls_back(tmp_path: Path):
    (tmp_path / "colors.toml").write_text("this is [not toml")
    assert theme.load_palette(theme_dir=tmp_path)["user"] == LH_ACCENT


def test_state_color_mapping():
    p = theme.FALLBACK
    assert theme.state_color("user_speaking", p) == theme.vivid(p["user"])
    assert theme.state_color("speaking", p) == theme.vivid(p["companion"])
    assert theme.state_color("error", p) == theme.vivid(p["error"])
    for s in ("idle", "listening", "thinking", "closed"):
        assert theme.state_color(s, p) == p["idle"]


def test_theme_dir_uses_slug_when_display_name_dir_missing(tmp_path: Path):
    (tmp_path / "last-horizon").mkdir()
    assert theme.existing_theme_dir(tmp_path / "Last Horizon") == tmp_path / "last-horizon"
    assert theme.existing_theme_dir(tmp_path / "Nope Theme") is None


def test_vivid_increases_saturation_but_keeps_hue():
    import colorsys

    rose = theme.FALLBACK["user"]
    h1, l1, s1 = colorsys.rgb_to_hls(*rose)
    h2, l2, s2 = colorsys.rgb_to_hls(*theme.vivid(rose))
    assert abs(h1 - h2) < 0.01
    assert s2 > s1 * 1.5


def test_speaking_colors_are_vivid_idle_is_not():
    p = theme.FALLBACK
    assert theme.state_color("user_speaking", p) == theme.vivid(p["user"])
    assert theme.state_color("speaking", p) == theme.vivid(p["companion"])
    assert theme.state_color("listening", p) == p["idle"]


def test_palette_presets():
    assert theme.palette_for("warm")["user"] == theme._hex("#ff8a65")
    assert theme.palette_for("glass")["companion"] == theme._hex("#e0f2ff")


def test_unknown_colors_use_theme(monkeypatch):
    monkeypatch.setattr(theme, "load_palette", lambda *a, **k: {"sentinel": True})
    assert theme.palette_for("neon") == {"sentinel": True}
    assert theme.palette_for("theme") == {"sentinel": True}


def test_ui_colors_from_theme(tmp_path):
    (tmp_path / "colors.toml").write_text('background = "#101010"\nforeground = "#eeeeee"\naccent = "#ff0000"\n')
    c = theme.ui_colors(theme_dir=tmp_path)
    assert c["background"] == "#101010" and c["accent"] == "#ff0000"
    assert c["muted"] == theme.UI_FALLBACK["muted"]  # missing keys fall back


def test_ui_colors_reject_bad_values(tmp_path):
    (tmp_path / "colors.toml").write_text('background = "red; }"\n')
    assert theme.ui_colors(theme_dir=tmp_path)["background"] == theme.UI_FALLBACK["background"]


def test_classic_colors_are_the_default():
    """Orange = you talking, blue = Rum talking (like the first demo), gray = idle (mic off)."""
    from omarum.config import Config
    from omarum.theme import PRESETS, _hex

    assert Config().orb_colors == "classic"
    c = PRESETS["classic"]
    assert c["user"] == _hex("#ff8c42") and c["companion"] == _hex("#4da3ff") and c["idle"] == _hex("#8c8c8c")
