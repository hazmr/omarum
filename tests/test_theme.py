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
    assert theme.state_color("user_speaking", p) == p["user"]
    assert theme.state_color("speaking", p) == p["companion"]
    assert theme.state_color("error", p) == p["error"]
    for s in ("idle", "listening", "thinking", "closed"):
        assert theme.state_color(s, p) == p["idle"]


def test_theme_dir_uses_slug_when_display_name_dir_missing(tmp_path: Path):
    (tmp_path / "last-horizon").mkdir()
    assert theme.existing_theme_dir(tmp_path / "Last Horizon") == tmp_path / "last-horizon"
    assert theme.existing_theme_dir(tmp_path / "Nope Theme") is None
