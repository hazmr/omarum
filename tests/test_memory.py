from datetime import date, datetime
from pathlib import Path

from omarum.config import Config
from omarum.memory import MemoryPassFailed, update_profile, valid_profile, write_journal
from omarum.store import Store

TRANSCRIPT = [
    {"at": "2026-11-19T21:40:05", "who": "user", "text": "I'm job hunting this week."},
    {"at": "2026-11-19T21:40:09", "who": "companion", "text": "Good luck! What kind of role?"},
]


def _store(tmp_path: Path, profile: str | None = "- Works on a Spring app\n") -> Store:
    s = Store(tmp_path)
    s.ensure()
    if profile is not None:
        s.profile_path.write_text(profile)
    return s


class FakeClaude:
    def __init__(self, reply="- Works on a Spring app\n- Job hunting this week (Nov 2026)\n", fail=False):
        self.reply, self.fail, self.calls = reply, fail, []

    def __call__(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if self.fail:
            raise MemoryPassFailed("usage limit reached")
        return self.reply


def test_profile_updated_and_backed_up(tmp_path):
    s = _store(tmp_path)
    assert update_profile(s, TRANSCRIPT, Config(), run=FakeClaude()) is True
    assert "Job hunting" in s.profile_path.read_text()
    assert s.profile_path.with_suffix(".md.bak").read_text() == "- Works on a Spring app\n"


def test_junk_output_keeps_old_profile(tmp_path):
    s = _store(tmp_path)
    assert update_profile(s, TRANSCRIPT, Config(), run=FakeClaude("Sure! Here is the profile:")) is False
    assert s.profile_path.read_text() == "- Works on a Spring app\n"


def test_empty_output_keeps_old_profile(tmp_path):
    s = _store(tmp_path)
    assert update_profile(s, TRANSCRIPT, Config(), run=FakeClaude("   \n")) is False
    assert s.profile_path.read_text() == "- Works on a Spring app\n"


def test_runner_failure_keeps_profile(tmp_path):
    s = _store(tmp_path)
    assert update_profile(s, TRANSCRIPT, Config(), run=FakeClaude(fail=True)) is False
    assert s.profile_path.read_text() == "- Works on a Spring app\n"


def test_first_profile_is_created(tmp_path):
    s = _store(tmp_path, profile=None)
    assert update_profile(s, TRANSCRIPT, Config(), run=FakeClaude("- Job hunting this week\n")) is True
    assert s.profile_path.read_text().startswith("- Job hunting")


def test_prompt_contains_current_profile_and_transcript(tmp_path):
    s = _store(tmp_path)
    fake = FakeClaude()
    update_profile(s, TRANSCRIPT, Config(user_name="Sam", companion_name="Rum"), run=fake)
    _system, prompt = fake.calls[0]
    assert "- Works on a Spring app" in prompt
    assert "Sam: I'm job hunting this week." in prompt
    assert "Rum: Good luck! What kind of role?" in prompt


def _day_with_conversation(s: Store) -> date:
    d = s.new_conversation(datetime(2026, 11, 18, 20, 0))
    (d / "transcript.jsonl").write_text('{"at":"2026-11-18T20:00:01","who":"user","text":"Long day."}\n')
    return date(2026, 11, 18)


def test_journal_written_once(tmp_path):
    s = _store(tmp_path)
    day = _day_with_conversation(s)
    assert write_journal(s, day, Config(), run=FakeClaude("Sam had a long day.")) is True
    assert write_journal(s, day, Config(), run=FakeClaude("Something else.")) is False
    assert s.journal_path(day).read_text().strip() == "Sam had a long day."


def test_journal_failure_writes_nothing(tmp_path):
    s = _store(tmp_path)
    day = _day_with_conversation(s)
    assert write_journal(s, day, Config(), run=FakeClaude(fail=True)) is False
    assert not s.journal_path(day).exists()


def test_valid_profile_rules():
    assert valid_profile("- a\n- b\n")
    assert valid_profile("- a\n\n- b")
    assert not valid_profile("")
    assert not valid_profile("Here you go:\n- a")
    assert not valid_profile("\n".join(f"- fact {i}" for i in range(201)))
