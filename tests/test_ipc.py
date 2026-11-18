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
