import asyncio
from pathlib import Path

import pytest

from omarum.ipc import DaemonNotRunning, EventHub, decode, encode, send_command


def test_encode_decode_roundtrip():
    msg = {"type": "level", "who": "user", "value": 0.5}
    line = encode(msg)
    assert line.endswith(b"\n")
    assert decode(line) == msg


def test_decode_bad_json_raises():
    with pytest.raises(ValueError):
        decode(b"{not json\n")


async def _start_hub(path: Path, on_command=None):
    async def default(cmd):
        return {"ok": True, "state": "idle"}

    hub = EventHub()
    await hub.serve(path, on_command or default)
    return hub


async def test_broadcast_reaches_two_clients(tmp_path: Path):
    sock = tmp_path / "s.sock"
    hub = await _start_hub(sock)
    r1, w1 = await asyncio.open_unix_connection(str(sock))
    r2, w2 = await asyncio.open_unix_connection(str(sock))
    await asyncio.sleep(0.05)  # let the hub register both clients
    hub.broadcast({"type": "state", "state": "thinking"})
    for r in (r1, r2):
        line = await asyncio.wait_for(r.readline(), 1)
        assert decode(line) == {"type": "state", "state": "thinking"}
    w1.close()
    w2.close()
    await hub.close()


async def test_command_reply(tmp_path: Path):
    sock = tmp_path / "s.sock"
    seen = []

    async def on_command(cmd):
        seen.append(cmd)
        return {"ok": True, "state": "idle"}

    hub = await _start_hub(sock, on_command)
    reply = await asyncio.to_thread(send_command, "status", sock)
    assert reply == {"ok": True, "state": "idle"}
    assert seen == [{"cmd": "status"}]
    await hub.close()


def test_send_command_no_daemon_raises(tmp_path: Path):
    with pytest.raises(DaemonNotRunning):
        send_command("status", tmp_path / "missing.sock")


async def test_watch_reports_off_then_reconnects(tmp_path: Path):
    from omarum.ipc import watch

    sock = tmp_path / "w.sock"
    seen: list[dict] = []
    stop = lambda: any(m.get("state") == "idle" for m in seen)
    task = asyncio.create_task(asyncio.to_thread(watch, sock, seen.append, 0.05, stop))
    await asyncio.sleep(0.15)
    assert {"type": "state", "state": "off"} in seen
    hub = await _start_hub(sock)
    await asyncio.wait_for(task, 3)
    assert seen[-1]["state"] == "idle"
    await hub.close()


async def test_commands_on_one_connection_dont_wait_for_each_other(tmp_path: Path):
    """The plugin keeps one socket: a key release must be handled while the press is still
    starting Rum (otherwise a tap is timed as a hold)."""
    sock = tmp_path / "s.sock"
    events = []

    async def on_command(cmd):
        events.append(("start", cmd["cmd"]))
        if cmd["cmd"] == "ptt_down":
            await asyncio.sleep(0.5)  # loading Whisper and the voice
        events.append(("done", cmd["cmd"]))
        return {"ok": True, "state": "idle"}

    hub = await _start_hub(sock, on_command)
    r, w = await asyncio.open_unix_connection(str(sock))
    w.write(encode({"cmd": "ptt_down"}) + encode({"cmd": "ptt_up"}))
    await w.drain()
    for _ in range(2):
        await asyncio.wait_for(r.readline(), 2)
    assert events.index(("done", "ptt_up")) < events.index(("done", "ptt_down"))
    assert events[0] == ("start", "ptt_down")  # still handled in the order sent
    w.close()
    await hub.close()
