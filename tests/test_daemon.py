import asyncio
import time

import pytest

from omarum import cli
from omarum.claude_code_llm import BrainUnavailable
from omarum.config import Config
from omarum.daemon import Daemon


class FakeHub:
    def __init__(self):
        self.sent = []

    def broadcast(self, msg):
        self.sent.append(msg)


class FakeFactory:
    """Stands in for build_pipeline: records starts; the 'task' runs until stopped."""

    def __init__(self, build_delay=0.0, fail=None):
        self.starts = 0
        self.stops = 0
        self.build_delay = build_delay
        self.fail = fail
        self.emit = None

    def __call__(self, cfg, emit):
        time.sleep(self.build_delay)
        if self.fail:
            raise self.fail
        self.starts += 1
        self.emit = emit
        done = asyncio.Event()

        async def stop():
            self.stops += 1
            done.set()

        self.finish = done.set  # lets a test end the "pipeline" on its own
        return done, stop, None


async def fake_run(task):
    await task.wait()


@pytest.fixture(autouse=True)
def claude_on_path(monkeypatch):
    monkeypatch.setattr("omarum.daemon.shutil.which", lambda name: "/usr/bin/claude")


def make(factory, **cfg):
    return Daemon(Config(**cfg), FakeHub(), pipeline_factory=factory, run_task=fake_run)


async def test_toggle_starts_then_stops():
    f = FakeFactory()
    d = make(f)
    r = await d.handle({"cmd": "toggle"})
    assert r["ok"] and d.state == "listening" and f.starts == 1
    r = await d.handle({"cmd": "toggle"})
    assert d.state == "closed" and f.stops == 1


async def test_double_toggle_while_starting_single_session():
    f = FakeFactory(build_delay=0.2)
    d = make(f)
    await asyncio.gather(d.handle({"cmd": "toggle"}), d.handle({"cmd": "toggle"}))
    assert f.starts == 1
    assert d.state == "listening"


async def test_missing_claude_cli_errors_without_crash(monkeypatch):
    monkeypatch.setattr("omarum.daemon.shutil.which", lambda name: None)
    d = make(FakeFactory())
    r = await d.handle({"cmd": "toggle"})
    assert r["ok"] is False and r["state"] == "error" and "claude" in r["reason"]
    r = await d.handle({"cmd": "status"})
    assert r["state"] == "error"


async def test_factory_exception_sets_error():
    d = make(FakeFactory(fail=RuntimeError("no microphone")))
    r = await d.handle({"cmd": "start"})
    assert r["ok"] is False and d.state == "error" and "no microphone" in r["reason"]


async def test_brain_unavailable_sets_error():
    f = FakeFactory()
    d = make(f)
    await d.handle({"cmd": "start"})
    f.emit({"type": "state", "state": "error", "reason": str(BrainUnavailable("usage limit reached"))})
    r = await d.handle({"cmd": "status"})
    assert r["state"] == "error" and "usage limit" in r["reason"]


async def test_idle_timeout_closes_session():
    f = FakeFactory()
    d = make(f, idle_timeout_secs=0.1)
    await d.handle({"cmd": "start"})
    await asyncio.sleep(0.4)
    assert d.state == "closed" and f.stops == 1


async def test_listening_does_not_override_user_speaking():
    f = FakeFactory()
    d = make(f)
    await d.handle({"cmd": "start"})
    f.emit({"type": "state", "state": "user_speaking"})
    f.emit({"type": "state", "state": "listening"})
    assert d.state == "user_speaking"


def test_cli_no_daemon_exit_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("omarum.cli.SOCKET_PATH", tmp_path / "missing.sock")
    with pytest.raises(SystemExit) as e:
        cli.main(["toggle"])
    assert e.value.code == 1
    assert capsys.readouterr().err.strip() == "omarum: daemon not running (start it with: omarum daemon)"


def test_cli_waits_long_enough_for_session_start(monkeypatch, capsys):
    seen = {}

    def fake_send(cmd, path, timeout=2.0):
        seen["timeout"] = timeout
        return {"ok": True, "state": "listening"}

    monkeypatch.setattr("omarum.cli.send_command", fake_send)
    with pytest.raises(SystemExit):
        cli.main(["toggle"])
    assert seen["timeout"] >= 15


def test_cli_timeout_prints_busy(monkeypatch, capsys):
    def slow(cmd, path, timeout=2.0):
        raise TimeoutError

    monkeypatch.setattr("omarum.cli.send_command", slow)
    with pytest.raises(SystemExit) as e:
        cli.main(["status"])
    assert e.value.code == 1
    assert "not responding" in capsys.readouterr().err


def test_claude_service_settings_complete():
    from omarum.claude_code_llm import ClaudeCodeLLMService

    svc = ClaudeCodeLLMService(model="haiku", system_prompt="hi")
    assert svc._settings.model == "haiku"
    assert svc._settings.temperature is None


async def test_late_events_from_closed_session_are_ignored():
    f = FakeFactory()
    d = make(f)
    await d.handle({"cmd": "start"})
    old_emit = f.emit
    await d.handle({"cmd": "toggle"})
    assert d.state == "closed"
    old_emit({"type": "state", "state": "speaking"})
    old_emit({"type": "level", "who": "companion", "value": 0.9})
    assert d.state == "closed"
    assert d.hub.sent[-1] == {"type": "state", "state": "closed"}


async def test_user_voice_keeps_session_alive():
    f = FakeFactory()
    d = make(f, idle_timeout_secs=0.3)
    await d.handle({"cmd": "start"})
    for _ in range(8):  # 0.4s of talking, longer than the idle timeout
        f.emit({"type": "level", "who": "user", "value": 0.6})
        await asyncio.sleep(0.05)
    assert d.state == "listening"  # not closed while the user is talking
    await asyncio.sleep(0.5)
    assert d.state == "closed"  # silence afterwards still closes it


async def test_new_session_waits_for_audio_release_after_stop():
    f = FakeFactory()
    d = make(f, audio_release_secs=0.3)
    await d.handle({"cmd": "start"})
    t0 = time.monotonic()
    await asyncio.gather(d.handle({"cmd": "toggle"}), d.handle({"cmd": "start"}))
    # the second start may only open audio after the first session released it
    assert f.starts in (1, 2)
    if f.starts == 2:
        assert time.monotonic() - t0 >= 0.3
    await d.handle({"cmd": "stop"})
    t1 = time.monotonic()
    await d.handle({"cmd": "start"})
    assert time.monotonic() - t1 >= 0.25  # start right after stop is delayed, not raced


async def test_session_that_ends_by_itself_is_closed_and_cools_down():
    f = FakeFactory()
    d = make(f, audio_release_secs=0.3)
    await d.handle({"cmd": "start"})
    f.emit({"type": "state", "state": "speaking"})
    f.finish()  # the pipeline finishes on its own (not via toggle)
    await asyncio.sleep(0.1)
    assert d.state == "closed"
    t0 = time.monotonic()
    await d.handle({"cmd": "start"})
    assert time.monotonic() - t0 >= 0.15  # audio cooldown still applies


async def test_brain_error_closes_the_session_and_mic():
    f = FakeFactory()
    d = make(f)
    await d.handle({"cmd": "start"})
    f.emit({"type": "state", "state": "error", "reason": "usage limit reached"})
    await asyncio.sleep(0.2)
    assert f.stops == 1            # pipeline (and microphone) stopped
    assert d.state == "error"      # the orb still shows the error
    r = await d.handle({"cmd": "status"})
    assert "usage limit" in r["reason"]


# ---- phase 2: memory -------------------------------------------------------

from datetime import date as _date, datetime as _datetime

from omarum.store import Store


class FakeSession:
    def __init__(self, saved_dir):
        self.saved_dir, self.meta, self.closed = saved_dir, {"voices": []}, 0

    def close(self, meta):
        self.closed += 1
        return self.saved_dir


class SessionFactory(FakeFactory):
    def __init__(self, saved_dir, **kw):
        super().__init__(**kw)
        self.session = FakeSession(saved_dir)

    def __call__(self, cfg, emit):
        task, stop, _ = super().__call__(cfg, emit)
        return task, stop, self.session


def inline(job):
    job()


def make_mem(factory, tmp_path, monkeypatch, fail=False, **cfg):
    calls = []

    def fake_update(store, transcript, cfg_):
        calls.append(("profile", transcript))
        if fail:
            raise RuntimeError("usage limit")
        return True

    def fake_journal(store, day, cfg_):
        calls.append(("journal", day))
        return True

    monkeypatch.setattr("omarum.daemon.update_profile", fake_update)
    monkeypatch.setattr("omarum.daemon.write_journal", fake_journal)
    store = Store(tmp_path)
    store.ensure()
    d = Daemon(Config(**cfg), FakeHub(), pipeline_factory=factory, run_task=fake_run,
               store=store, memory_runner=inline)
    return d, calls, store


def _saved(tmp_path):
    d = tmp_path / "conv"
    d.mkdir()
    (d / "transcript.jsonl").write_text('{"who":"user","text":"I am job hunting"}\n')
    return d


async def test_profile_update_queued_after_session(tmp_path, monkeypatch):
    f = SessionFactory(_saved(tmp_path))
    d, calls, _ = make_mem(f, tmp_path, monkeypatch)
    await d.handle({"cmd": "start"})
    await d.handle({"cmd": "stop"})
    assert f.session.closed == 1
    assert calls == [("profile", [{"who": "user", "text": "I am job hunting"}])]


async def test_empty_session_queues_nothing(tmp_path, monkeypatch):
    f = SessionFactory(None)
    d, calls, _ = make_mem(f, tmp_path, monkeypatch)
    await d.handle({"cmd": "start"})
    await d.handle({"cmd": "stop"})
    assert f.session.closed == 1 and calls == []


async def test_self_ended_session_also_saved(tmp_path, monkeypatch):
    f = SessionFactory(_saved(tmp_path))
    d, calls, _ = make_mem(f, tmp_path, monkeypatch)
    await d.handle({"cmd": "start"})
    f.finish()
    await asyncio.sleep(0.1)
    assert f.session.closed == 1 and [c[0] for c in calls] == ["profile"]


async def test_memory_failure_does_not_break_next_session(tmp_path, monkeypatch):
    f = SessionFactory(_saved(tmp_path))
    d, calls, _ = make_mem(f, tmp_path, monkeypatch, fail=True)
    await d.handle({"cmd": "start"})
    await d.handle({"cmd": "stop"})
    r = await d.handle({"cmd": "start"})
    assert r["ok"] and d.state == "listening"
    assert (await d.handle({"cmd": "status"}))["memory"] == "idle"


async def test_journals_for_missing_days_queued_at_start(tmp_path, monkeypatch):
    f = SessionFactory(None)
    d, calls, store = make_mem(f, tmp_path, monkeypatch)
    c = store.new_conversation(_datetime(2026, 11, 17, 9, 0))
    (c / "transcript.jsonl").write_text('{"who":"user","text":"hi"}\n')
    d.on_startup(_datetime(2026, 11, 19, 12, 0))
    assert calls == [("journal", _date(2026, 11, 17))]


async def test_reload_broadcasts():
    d = make(FakeFactory())
    r = await d.handle({"cmd": "reload"})
    assert r["ok"] and {"type": "reload"} in d.hub.sent


def test_cli_reload_command(monkeypatch, capsys):
    seen = {}

    def fake_send(cmd, path, timeout=2.0):
        seen.update(cmd=cmd, timeout=timeout)
        return {"ok": True, "state": "idle"}

    monkeypatch.setattr("omarum.cli.send_command", fake_send)
    with pytest.raises(SystemExit):
        cli.main(["reload"])
    assert seen == {"cmd": "reload", "timeout": 2.0}


async def test_reload_rereads_config(tmp_path, monkeypatch):
    p = tmp_path / "config.toml"
    p.write_text('brain_model = "sonnet"\n')
    monkeypatch.setattr("omarum.config.CONFIG_PATH", p)
    d = make(FakeFactory())
    assert d.cfg.brain_model == "haiku"
    await d.handle({"cmd": "reload"})
    assert d.cfg.brain_model == "sonnet"


# ---- push-to-talk ------------------------------------------------------------

class FakeGate:
    def __init__(self):
        self.is_open, self.interrupts = True, 0

    def set_open(self, v):
        self.is_open = v

    async def interrupt(self):
        self.interrupts += 1


class GateFactory(FakeFactory):
    def __call__(self, cfg, emit):
        task, stop, _ = super().__call__(cfg, emit)
        self.session = FakeSession(None)
        self.session.gate = self.gate = FakeGate()
        return task, stop, self.session


async def test_ptt_hold_starts_session_and_release_closes_mic(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("omarum.daemon.time.monotonic", lambda: clock[0])
    f = GateFactory()
    d = make(f)
    await d.handle({"cmd": "ptt_down"})
    assert f.starts == 1 and f.gate.is_open
    clock[0] = 2.0
    await d.handle({"cmd": "ptt_up"})
    assert not f.gate.is_open and d.state == "listening"


async def test_ptt_tap_hands_free_then_tap_closes(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("omarum.daemon.time.monotonic", lambda: clock[0])
    f = GateFactory()
    d = make(f)
    await d.handle({"cmd": "ptt_down"})
    clock[0] = 0.1
    await d.handle({"cmd": "ptt_up"})
    assert f.gate.is_open  # hands-free: mic stays open
    clock[0] = 5.0
    await d.handle({"cmd": "ptt_down"})
    clock[0] = 5.1
    await d.handle({"cmd": "ptt_up"})
    assert d.state == "closed" and f.stops == 1


async def test_ptt_hold_interrupts_rum(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("omarum.daemon.time.monotonic", lambda: clock[0])
    f = GateFactory()
    d = make(f)
    await d.handle({"cmd": "ptt_down"})
    clock[0] = 2.0
    await d.handle({"cmd": "ptt_up"})
    f.emit({"type": "state", "state": "speaking"})
    clock[0] = 5.0
    await d.handle({"cmd": "ptt_down"})
    assert f.gate.interrupts == 1 and f.gate.is_open


async def test_ptt_release_during_slow_start_applies_after(monkeypatch):
    f = GateFactory(build_delay=0.3)
    d = make(f)
    down = asyncio.create_task(d.handle({"cmd": "ptt_down"}))
    await asyncio.sleep(0.05)
    # simulate a long hold released while the pipeline is still being built
    d._ptt._down_at -= 1.0
    await d.handle({"cmd": "ptt_up"})
    await down
    assert f.gate.is_open is False


async def test_tap_opens_hands_free_then_closes():
    f = GateFactory()
    d = make(f)
    await d.handle({"cmd": "tap"})
    assert f.starts == 1 and f.gate.is_open and d._ptt.mode == "hands_free"
    await d.handle({"cmd": "tap"})
    assert d.state == "closed" and f.stops == 1


async def test_tap_during_start_is_single_session():
    f = GateFactory(build_delay=0.2)
    d = make(f)
    await asyncio.gather(d.handle({"cmd": "tap"}), d.handle({"cmd": "tap"}))
    assert f.starts == 1


def test_cli_summary_prints_one_json_line(monkeypatch, capsys):
    import json

    from omarum import cli, summary

    monkeypatch.setattr(summary, "current", lambda: {"name": "Rum", "talks": 0})
    cli.main(["summary"])
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and json.loads(out) == {"name": "Rum", "talks": 0}
