from datetime import date, datetime
from pathlib import Path

from omarum import persona
from omarum.config import Config
from omarum.context import build_system_prompt
from omarum.store import Store

NOW = datetime(2026, 11, 19, 21, 40)


def _store(tmp_path: Path) -> Store:
    s = Store(tmp_path)
    s.ensure()
    return s


def test_prompt_includes_profile_and_recent_journals(tmp_path):
    s = _store(tmp_path)
    s.profile_path.write_text("- Works on a Spring app\n")
    for d in (15, 16, 17, 18):
        s.journal_path(date(2026, 11, d)).write_text(f"Day {d} was fine.")
    p = build_system_prompt(Config(user_name="Sam"), s, NOW)
    assert "## What you know about Sam" in p and "- Works on a Spring app" in p
    assert "### 2026-11-15" not in p
    assert p.index("### 2026-11-16") < p.index("### 2026-11-17") < p.index("### 2026-11-18")
    assert "It is Thursday, 19 November 2026, 21:40." in p


def test_prompt_without_memory_is_just_persona_and_time(tmp_path):
    p = build_system_prompt(Config(user_name="Sam"), _store(tmp_path), NOW)
    assert p.startswith("You are Rum.")
    assert "What you know" not in p and "Recent days" not in p
    assert "## Right now" in p


def test_hand_edited_persona_is_used(tmp_path):
    s = _store(tmp_path)
    s.persona_path.write_text("You are {name}, a pirate.")
    assert build_system_prompt(Config(), s, NOW).startswith("You are Rum, a pirate.")


def test_persona_file_created_on_first_use(tmp_path):
    s = _store(tmp_path)
    persona.load(Config(), s)
    assert s.persona_path.read_text() == persona.DEFAULT_PERSONA


def test_unknown_braces_in_persona_do_not_crash(tmp_path):
    s = _store(tmp_path)
    s.persona_path.write_text("You are {name}. Mood: {mood}. Odd { brace.")
    text = persona.load(Config(), s)
    assert text == "You are Rum. Mood: {mood}. Odd { brace."
