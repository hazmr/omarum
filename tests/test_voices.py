from pathlib import Path

from pipecat.utils.errors import ErrorCategory

from omarum.config import Config
from omarum.voices import load_env_file, should_fail_over, voice_chain
from omarum.zonos3_tts import float32_to_int16

ALL = {"elevenlabs", "zonos3", "kokoro"}


def test_order_from_elevenlabs():
    assert voice_chain(Config(voice_primary="elevenlabs"), ALL) == ["elevenlabs", "zonos3", "kokoro"]


def test_choosing_zonos3_skips_elevenlabs():
    assert voice_chain(Config(voice_primary="zonos3"), ALL) == ["zonos3", "kokoro"]


def test_choosing_kokoro_is_kokoro_only():
    assert voice_chain(Config(voice_primary="kokoro"), ALL) == ["kokoro"]


def test_unavailable_voices_are_skipped():
    # no ElevenLabs key, ZONOS3 not installed
    assert voice_chain(Config(voice_primary="elevenlabs"), {"kokoro"}) == ["kokoro"]
    assert voice_chain(Config(voice_primary="elevenlabs"), {"zonos3", "kokoro"}) == ["zonos3", "kokoro"]


def test_kokoro_always_last_resort():
    assert voice_chain(Config(voice_primary="zonos3"), set()) == ["kokoro"]


def test_piper_is_a_manual_choice():
    assert voice_chain(Config(voice_primary="piper"), ALL) == ["piper"]


def test_fail_over_on_quota_network_and_server_errors():
    for c in (ErrorCategory.QUOTA, ErrorCategory.CONNECTIVITY, ErrorCategory.SERVER,
              ErrorCategory.RATE_LIMIT, ErrorCategory.AUTHENTICATION):
        assert should_fail_over(c), c
    assert not should_fail_over(ErrorCategory.CONTENT_FILTERED)


def test_float32_to_int16():
    import struct
    raw = struct.pack("<3f", 0.0, 1.0, -1.5)
    assert struct.unpack("<3h", float32_to_int16(raw)) == (0, 32767, -32767)


def test_load_env_file(tmp_path: Path):
    p = tmp_path / "env"
    p.write_text("# keys\nELEVENLABS_API_KEY=abc123\n\nBAD LINE\nX = y \n")
    assert load_env_file(p) == {"ELEVENLABS_API_KEY": "abc123", "X": "y"}


def test_load_env_file_missing(tmp_path: Path):
    assert load_env_file(tmp_path / "nope") == {}


def test_pick_speaker_by_name():
    from omarum.zonos3_tts import pick_speaker

    speakers = [
        {"id": "default_aa", "name": "Imogen_en-British_F_1"},
        {"id": "default_bb", "name": "Savannah_en-American_F_1"},
    ]
    assert pick_speaker(speakers, "Savannah") == "default_bb"
    assert pick_speaker(speakers, "savannah") == "default_bb"
    assert pick_speaker(speakers, "default_aa") == "default_aa"
    assert pick_speaker(speakers, "Nobody") == "default_aa"  # unknown name -> first voice
    assert pick_speaker([], "Savannah") is None
