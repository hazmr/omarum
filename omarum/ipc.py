"""Newline-delimited JSON over a Unix socket.

Stdlib only: the orb imports this with the system Python.

Events (daemon -> clients):
  {"type": "state", "state": "idle|listening|user_speaking|thinking|speaking|error|closed", "reason"?: str}
  {"type": "level", "who": "user|companion", "value": 0..1}
Commands (client -> daemon): {"cmd": "toggle|start|stop|status"}
Reply: {"ok": bool, "state": str, "reason"?: str}
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path
from typing import Awaitable, Callable

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omarum.sock"


class DaemonNotRunning(Exception):
    pass


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode()


def decode(line: bytes) -> dict:
    try:
        msg = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"bad message: {line[:80]!r}") from exc
    if not isinstance(msg, dict):
        raise ValueError("message is not an object")
    return msg


class EventHub:
    """Serves commands and broadcasts events to every connected client."""

    def __init__(self) -> None:
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._path: Path | None = None

    async def serve(self, path: Path, on_command: Callable[[dict], Awaitable[dict]]) -> None:
        path.unlink(missing_ok=True)
        self._path = path

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            self._clients.add(writer)
            try:
                while line := await reader.readline():
                    try:
                        reply = await on_command(decode(line))
                    except ValueError as exc:
                        reply = {"ok": False, "state": "error", "reason": str(exc)}
                    writer.write(encode(reply))
                    await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                self._clients.discard(writer)
                writer.close()

        self._server = await asyncio.start_unix_server(handle, path=str(path))

    def broadcast(self, msg: dict) -> None:
        data = encode(msg)
        for w in list(self._clients):
            # Drop clients that are gone or not reading (buffer over 64 KiB).
            if w.is_closing() or w.transport.get_write_buffer_size() > 65536:
                self._clients.discard(w)
                w.close()
                continue
            w.write(data)

    async def close(self) -> None:
        for w in list(self._clients):
            w.close()
        self._clients.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._path:
            self._path.unlink(missing_ok=True)


def send_command(cmd: str, path: Path = SOCKET_PATH, timeout: float = 2.0) -> dict:
    """Send one command and return the daemon's reply (skips broadcast events)."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(path))
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        s.close()
        raise DaemonNotRunning(str(path)) from exc
    with s, s.makefile("rb") as f:
        s.sendall(encode({"cmd": cmd}))
        for line in f:
            msg = decode(line)
            if "ok" in msg:
                return msg
    raise DaemonNotRunning("connection closed without a reply")


def watch(path: Path, on_message: Callable[[dict], None], retry_secs: float = 1.0,
          stop: Callable[[], bool] | None = None) -> None:
    """Follow the daemon's state (levels skipped). Down or gone: report 'off' and retry."""
    import time

    stop = stop or (lambda: False)
    while not stop():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(str(path))
                s.sendall(encode({"cmd": "status"}))
                with s.makefile("rb") as f:
                    for line in f:
                        try:
                            msg = decode(line)
                        except ValueError:
                            continue
                        if msg.get("type") == "state" or "ok" in msg:
                            on_message({"type": "state", "state": msg.get("state", "idle"),
                                        **({"reason": msg["reason"]} if msg.get("reason") else {})})
                        if stop():
                            return
        except OSError:
            pass
        on_message({"type": "state", "state": "off"})
        time.sleep(retry_secs)
