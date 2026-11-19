import json
import tarfile
from datetime import date, datetime
from pathlib import Path

import pytest

from omarum import library
from omarum.store import Store


def _store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "data")
    s.ensure()
    return s


def _talk(s: Store, when: datetime, text: str, secs: int = 65, audio: bool = True) -> Path:
    d = s.new_conversation(when)
    (d / "transcript.jsonl").write_text(json.dumps({"who": "user", "text": text}) + "\n")
    end = when.replace(minute=when.minute + secs // 60, second=secs % 60)
    (d / "meta.json").write_text(json.dumps({"started": when.isoformat(), "ended": end.isoformat()}))
    if audio:
        (d / "user.opus").write_bytes(b"x")
        (d / "companion.opus").write_bytes(b"x")
    return d


def test_facts_and_forget_with_backup(tmp_path):
    s = _store(tmp_path)
    s.profile_path.write_text("- Likes tea\n- Job hunting\n- Lives in Cairo\n")
    assert library.facts(s) == ["Likes tea", "Job hunting", "Lives in Cairo"]
    library.forget(s, 1)
    assert library.facts(s) == ["Likes tea", "Lives in Cairo"]
    assert "Job hunting" in s.profile_path.with_suffix(".md.bak").read_text()


def test_journals_newest_first(tmp_path):
    s = _store(tmp_path)
    s.journal_path(date(2026, 11, 17)).write_text("old")
    s.journal_path(date(2026, 11, 18)).write_text("new")
    assert [d for d, _ in library.journals(s)] == [date(2026, 11, 18), date(2026, 11, 17)]


def test_talks_newest_first_with_duration_and_first_line(tmp_path):
    s = _store(tmp_path)
    _talk(s, datetime(2026, 11, 18, 9, 0, 0), "older")
    _talk(s, datetime(2026, 11, 19, 21, 40, 0), "x" * 100, secs=125)
    talks = library.talks(s)
    assert [t.day for t in talks] == [date(2026, 11, 19), date(2026, 11, 18)]
    assert talks[0].time == "21:40" and talks[0].seconds == 125
    assert talks[0].first_line == "x" * 59 + "…"


def test_play_command(tmp_path):
    s = _store(tmp_path)
    _talk(s, datetime(2026, 11, 19, 9, 0, 0), "hi")
    _talk(s, datetime(2026, 11, 19, 10, 0, 0), "silent", audio=False)
    with_audio, without = sorted(library.talks(s), key=lambda t: t.time)
    cmd = library.play_command(with_audio)
    assert cmd[0] == "mpv" and cmd[-2].endswith("user.opus") and cmd[-1].endswith("companion.opus")
    assert library.play_command(without) == []


def test_delete_talk_refuses_outside_store(tmp_path):
    s = _store(tmp_path)
    d = _talk(s, datetime(2026, 11, 19, 9, 0, 0), "bye")
    t = library.talks(s)[0]
    library.delete_talk(s, t)
    assert not d.exists()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(ValueError):
        library.delete_talk(s, library.Talk(outside, date(2026, 11, 19), "09:00", None, "", []))
    assert outside.exists()


def test_export_contains_profile(tmp_path):
    s = _store(tmp_path)
    s.profile_path.write_text("- Likes tea\n")
    out = library.export(s, tmp_path / "out")
    with tarfile.open(out) as tar:
        assert any(n.endswith("memory/profile.md") for n in tar.getnames())
