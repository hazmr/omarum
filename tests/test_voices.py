from pathlib import Path

from omarum.config import Config
from omarum.voices import load_env_file, voice_chain


def test_elevenlabs_first_then_kokoro_when_key_present():
    assert voice_chain(Config(), {"ELEVENLABS_API_KEY": "k"}) == ["elevenlabs", "kokoro"]


def test_kokoro_only_without_key():
    assert voice_chain(Config(), {}) == ["kokoro"]


def test_local_voice_can_be_forced():
    assert voice_chain(Config(voice_primary="kokoro"), {"ELEVENLABS_API_KEY": "k"}) == ["kokoro"]


def test_piper_still_selectable():
    assert voice_chain(Config(voice_primary="piper"), {}) == ["piper"]


def test_load_env_file(tmp_path: Path):
    p = tmp_path / "env"
    p.write_text("# keys\nELEVENLABS_API_KEY=abc123\n\nBAD LINE\nX = y \n")
    assert load_env_file(p) == {"ELEVENLABS_API_KEY": "abc123", "X": "y"}


def test_load_env_file_missing(tmp_path: Path):
    assert load_env_file(tmp_path / "nope") == {}
