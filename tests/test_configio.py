import stat
from pathlib import Path

from omarum.config import load_config
from omarum.configio import has_secret, save_config, set_secret


def test_wrong_type_uses_default(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('orb_size = "big"\n')
    assert load_config(p).orb_size == 160


def test_unknown_choice_uses_default(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('voice_primary = "siri"\norb_style = "ring"\n')
    cfg = load_config(p)
    assert cfg.voice_primary == "elevenlabs" and cfg.orb_style == "ring"


def test_bad_toml_gives_defaults(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text("this is = = not toml")
    assert load_config(p).companion_name == "Rum"


def test_int_accepted_for_float(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text("vad_stop_secs = 1\n")
    assert load_config(p).vad_stop_secs == 1.0


def test_save_preserves_comments_and_unknown_keys(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('# my notes\n# keep me\nfuture_key = "x"\norb_style = "glow"\n')
    save_config({"orb_style": "ring", "orb_size": 200}, p)
    text = p.read_text()
    assert text.startswith("# my notes\n# keep me\n")
    assert 'future_key = "x"' in text
    cfg = load_config(p)
    assert cfg.orb_style == "ring" and cfg.orb_size == 200


def test_save_roundtrip_types(tmp_path: Path):
    p = tmp_path / "sub" / "c.toml"
    save_config({"companion_name": 'Ru"m', "record_audio": False, "retention_days": 30, "vad_stop_secs": 0.4}, p)
    cfg = load_config(p)
    assert (cfg.companion_name, cfg.record_audio, cfg.retention_days, cfg.vad_stop_secs) == ('Ru"m', False, 30, 0.4)


def test_set_secret_mode_and_replace(tmp_path: Path):
    p = tmp_path / "env"
    set_secret("ELEVENLABS_API_KEY", "one", p)
    set_secret("OTHER", "x", p)
    set_secret("ELEVENLABS_API_KEY", "two", p)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert p.read_text().count("ELEVENLABS_API_KEY=") == 1 and "ELEVENLABS_API_KEY=two" in p.read_text()
    set_secret("ELEVENLABS_API_KEY", "", p)
    assert "ELEVENLABS" not in p.read_text() and "OTHER=x" in p.read_text()


def test_has_secret(tmp_path: Path):
    p = tmp_path / "env"
    assert not has_secret("ELEVENLABS_API_KEY", p)
    set_secret("ELEVENLABS_API_KEY", "k", p)
    assert has_secret("ELEVENLABS_API_KEY", p)
