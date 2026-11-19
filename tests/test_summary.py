from datetime import date
from pathlib import Path

from omarum.config import Config
from omarum.library import Talk
from omarum.summary import duration, ears_label, shortcut_label, summary, to_hex, voice_label

PALETTE = {"user": (1.0, 0.5, 0.0), "companion": (0.0, 0.5, 1.0), "idle": (0.2, 0.2, 0.2),
           "error": (1.0, 0.0, 0.0), "background": (0.0, 0.0, 0.0)}


def talk(day, time, seconds, first="hello there"):
    return Talk(Path("/x"), day, time, seconds, first, [])


def test_duration():
    assert duration(None) == ""
    assert duration(9) == "9s"
    assert duration(252) == "4m 12s"
    assert duration(3720) == "1h 2m"


def test_labels():
    cfg = Config()
    assert ears_label(cfg, has_gpu=True) == "Whisper · large-v3-turbo"
    assert ears_label(cfg, has_gpu=False) == "Whisper · base.en"
    assert ears_label(Config(whisper_device="cpu"), has_gpu=True) == "Whisper · base.en"
    assert voice_label(Config(voice_primary="zonos3", zonos3_voice="Savannah")) == "ZONOS3 · Savannah"
    assert voice_label(Config(voice_primary="kokoro")) == "Kokoro · af_heart"
    assert voice_label(Config(voice_primary="elevenlabs")) == "ElevenLabs"
    assert shortcut_label("CTRL + SHIFT + SPACE") == "Ctrl+Shift+Space"
    assert shortcut_label("") == "none"
    assert to_hex((1.0, 0.5, 0.0)) == "#ff8000"


def test_summary_with_conversations():
    today = date(2026, 11, 19)
    talks = [talk(today, "21:40", 252, "Could you continue building the app?"),
             talk(date(2026, 11, 18), "09:30", 60)]
    s = summary(Config(companion_name="Rum", brain_model="sonnet"), talks, today, has_gpu=False, palette=PALETTE)
    assert s["name"] == "Rum"
    assert s["brain"] == "Claude Code · sonnet"
    assert s["talks"] == 2
    assert s["last"] == {"text": "Could you continue building the app?", "when": "today 21:40", "length": "4m 12s"}
    # The bar and panel use the orb's own colors: vivid you / companion, plain idle.
    assert s["colors"]["idle"] == "#333333"
    assert s["colors"]["user"].startswith("#") and len(s["colors"]["user"]) == 7
    assert s["colors"]["user"] != s["colors"]["companion"]


def test_summary_yesterday_older_and_none():
    today = date(2026, 11, 19)
    s = summary(Config(), [talk(date(2026, 11, 18), "09:30", None)], today, False, PALETTE)
    assert s["last"]["when"] == "yesterday 09:30"
    assert s["last"]["length"] == ""
    s = summary(Config(), [talk(date(2026, 11, 2), "09:30", 5)], today, False, PALETTE)
    assert s["last"]["when"] == "Nov 2 09:30"
    s = summary(Config(), [], today, False, PALETTE)
    assert s["last"] is None and s["talks"] == 0
