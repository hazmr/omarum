import stat
from datetime import date, datetime
from pathlib import Path

from omarum.store import Store


def _conv(store: Store, when: datetime, text: str = '{"who":"user","text":"hi"}\n') -> Path:
    d = store.new_conversation(when)
    (d / "transcript.jsonl").write_text(text)
    return d


def test_ensure_creates_private_layout(tmp_path: Path):
    s = Store(tmp_path / "omarum")
    s.ensure()
    assert stat.S_IMODE(s.root.stat().st_mode) == 0o700
    assert s.journal_dir.is_dir() and s.conversations_dir.is_dir()
    assert s.profile_path.parent.is_dir()


def test_new_conversation_path(tmp_path: Path):
    s = Store(tmp_path)
    s.ensure()
    a = s.new_conversation(datetime(2026, 11, 19, 21, 40))
    b = s.new_conversation(datetime(2026, 11, 19, 21, 40))
    assert a.parent.name == "2026-11-19"
    assert a.name.startswith("214000-")
    assert a != b and a.is_dir() and b.is_dir()


def test_days_without_journal(tmp_path: Path):
    s = Store(tmp_path)
    s.ensure()
    _conv(s, datetime(2026, 11, 17, 10, 0))
    _conv(s, datetime(2026, 11, 18, 10, 0))
    _conv(s, datetime(2026, 11, 16, 10, 0), text="")  # empty transcript: not a real conversation
    s.journal_path(date(2026, 11, 17)).write_text("journal")
    assert s.days_without_journal(date(2026, 11, 19)) == [date(2026, 11, 18)]
    assert s.conversations_on(date(2026, 11, 16)) == []


def test_prune_respects_retention(tmp_path: Path):
    s = Store(tmp_path)
    s.ensure()
    _conv(s, datetime(2026, 11, 1, 9, 0))
    _conv(s, datetime(2026, 11, 18, 9, 0))
    now = datetime(2026, 11, 19, 12, 0)
    assert s.prune(0, now) == 0
    assert s.prune(7, now) == 1
    assert not (s.conversations_dir / "2026-11-01").exists()
    assert (s.conversations_dir / "2026-11-18").exists()


def test_same_minute_conversations_sort_in_time_order(tmp_path: Path):
    s = Store(tmp_path)
    s.ensure()
    first = _conv(s, datetime(2026, 11, 19, 2, 54, 5))
    second = _conv(s, datetime(2026, 11, 19, 2, 54, 40))
    assert s.conversations_on(datetime(2026, 11, 19).date()) == [first, second]
