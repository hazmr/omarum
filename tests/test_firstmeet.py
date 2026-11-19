import json
from datetime import datetime

from omarum import firstmeet
from omarum.config import Config
from omarum.context import build_system_prompt
from omarum.store import Store


def _talk(store, rows):
    d = store.new_conversation(datetime(2026, 11, 19, 18, 0))
    (d / "transcript.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def test_first_meeting_until_a_real_conversation_is_saved(tmp_path):
    store = Store(tmp_path)
    store.ensure()
    assert firstmeet.is_first_meeting(store)
    store.new_conversation(datetime(2026, 11, 19, 17, 0))  # an empty, aborted session doesn't count
    assert firstmeet.is_first_meeting(store)
    _talk(store, [{"who": "user", "text": "hi"}])
    assert not firstmeet.is_first_meeting(store)


def test_existing_memory_means_not_a_first_meeting(tmp_path):
    store = Store(tmp_path)
    store.ensure()
    store.profile_path.parent.mkdir(parents=True, exist_ok=True)
    store.profile_path.write_text("- likes tea\n")
    assert not firstmeet.is_first_meeting(store)


def test_first_meeting_prompt_only_the_first_time(tmp_path):
    store = Store(tmp_path)
    store.ensure()
    cfg = Config(companion_name="Rum", user_name="z")
    first = build_system_prompt(cfg, store, datetime(2026, 11, 19, 18, 0))
    assert "first time" in first.lower() and "My name is" in first
    _talk(store, [{"who": "user", "text": "hi"}])
    later = build_system_prompt(cfg, store, datetime(2026, 11, 19, 19, 0))
    assert "My name is" not in later


def test_names_chosen_in_the_first_talk():
    rows = [
        {"who": "companion", "text": "Hi! I'm just waking up. I've been thinking about what to call myself."},
        {"who": "user", "text": "Nice to meet you. My name is Hazem, by the way."},
        {"who": "companion", "text": "Okay, I've decided. My name is Nova. It feels bright."},
        {"who": "companion", "text": "Actually my name is something I'll keep."},  # later, lowercase: ignored
    ]
    assert firstmeet.chosen_names(rows) == ("Nova", "Hazem")


def test_names_ignore_non_names_and_missing():
    assert firstmeet.chosen_names([{"who": "user", "text": "call me later"}]) == (None, None)
    assert firstmeet.chosen_names([{"who": "user", "text": "you can call me Haz"}]) == (None, "Haz")
    assert firstmeet.chosen_names([{"who": "companion", "text": "My name is The."}]) == (None, None)
    assert firstmeet.chosen_names([]) == (None, None)


def test_name_updates_only_what_changed():
    rows = [{"who": "companion", "text": "My name is Nova."}, {"who": "user", "text": "call me Hazem"}]
    assert firstmeet.name_updates(rows, Config(companion_name="Rum", user_name="z")) == \
        {"companion_name": "Nova", "user_name": "Hazem"}
    assert firstmeet.name_updates(rows, Config(companion_name="Nova", user_name="Hazem")) == {}
    assert firstmeet.name_updates([], Config()) == {}
