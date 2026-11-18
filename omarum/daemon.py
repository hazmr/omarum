"""Session control: one conversation at a time, driven by socket commands."""

from __future__ import annotations

import asyncio
import shutil
import time
from typing import Awaitable, Callable

from loguru import logger

from omarum.config import Config

ACTIVE = {"listening", "user_speaking", "thinking", "speaking"}


async def _pipecat_run(task) -> None:
    from pipecat.pipeline.runner import PipelineRunner

    await PipelineRunner(handle_sigint=False).run(task)


def _default_factory(cfg, emit):
    from omarum.pipeline import build_pipeline  # heavy import: only when talking

    return build_pipeline(cfg, emit)


class Daemon:
    def __init__(
        self,
        cfg: Config,
        hub,
        pipeline_factory: Callable = _default_factory,
        run_task: Callable[[object], Awaitable[None]] = _pipecat_run,
    ) -> None:
        self.cfg = cfg
        self.hub = hub
        self.state = "idle"
        self.reason: str | None = None
        self._factory = pipeline_factory
        self._run_task = run_task
        self._starting = False
        self._stop: Callable[[], Awaitable[None]] | None = None
        self._runner: asyncio.Task | None = None
        self._watchdog: asyncio.Task | None = None
        self._listening_since = time.monotonic()
        self._session = 0  # bumps on every start/end; stale sessions' events are dropped

    # -- events from the pipeline -------------------------------------------
    def _emitter(self, session: int):
        def emit(msg: dict) -> None:
            if session == self._session:
                self.on_event(msg)

        return emit

    def on_event(self, msg: dict) -> None:
        if msg.get("type") == "state":
            new = msg["state"]
            if new == "listening" and self.state == "user_speaking":
                return  # the companion stopped because the user interrupted
            self._set_state(new, msg.get("reason"))
        else:
            self.hub.broadcast(msg)

    def _set_state(self, state: str, reason: str | None = None) -> None:
        self.state = state
        self.reason = reason if state == "error" else None
        if state == "listening":
            self._listening_since = time.monotonic()
        msg = {"type": "state", "state": state}
        if self.reason:
            msg["reason"] = self.reason
        self.hub.broadcast(msg)

    def _reply(self, ok: bool = True) -> dict:
        r = {"ok": ok, "state": self.state}
        if self.reason:
            r["reason"] = self.reason
        return r

    @property
    def _active(self) -> bool:
        return self._runner is not None and not self._runner.done()

    # -- commands ------------------------------------------------------------
    async def handle(self, cmd: dict) -> dict:
        match cmd.get("cmd"):
            case "status":
                return self._reply()
            case "start":
                return await self._start()
            case "stop":
                return await self._end()
            case "toggle":
                if self._starting:
                    return self._reply()
                return await (self._end() if self._active else self._start())
            case other:
                return {"ok": False, "state": self.state, "reason": f"unknown command {other!r}"}

    async def _start(self) -> dict:
        if self._starting or self._active:
            return self._reply()
        if shutil.which("claude") is None:
            self._set_state("error", "claude CLI not found")
            return self._reply(ok=False)
        self._starting = True
        try:
            self._session += 1
            emit = self._emitter(self._session)
            task, self._stop = await asyncio.to_thread(self._factory, self.cfg, emit)
        except Exception as exc:  # no mic, model load failure, ...
            logger.exception("could not start a session")
            self._set_state("error", str(exc))
            return self._reply(ok=False)
        finally:
            self._starting = False
        self._runner = asyncio.create_task(self._run(task))
        self._watchdog = asyncio.create_task(self._watch_idle())
        self._set_state("listening")
        return self._reply()

    async def _run(self, task) -> None:
        try:
            await self._run_task(task)
        except Exception as exc:
            logger.exception("session crashed")
            self._set_state("error", str(exc))

    async def _watch_idle(self) -> None:
        while self._active:
            await asyncio.sleep(0.05)
            idle = time.monotonic() - self._listening_since
            if self.state == "listening" and idle > self.cfg.idle_timeout_secs:
                await self._end()
                return

    async def _end(self) -> dict:
        if not self._active:
            return self._reply()
        runner = self._runner
        self._session += 1  # from now on, this session's events are ignored
        if self._stop:
            await self._stop()
        try:
            await asyncio.wait_for(asyncio.shield(runner), 3)
        except asyncio.TimeoutError:
            runner.cancel()
        if self.state != "error":
            self._set_state("closed")
        return self._reply()


async def run_daemon() -> None:
    from omarum.config import load_config
    from omarum.ipc import SOCKET_PATH, EventHub

    from omarum import zonos3_tts

    cfg = load_config()
    hub = EventHub()
    daemon = Daemon(cfg, hub)
    await hub.serve(SOCKET_PATH, daemon.handle)
    logger.info(f"omarum daemon listening on {SOCKET_PATH}")
    # ZONOS3 keeps its model loaded in its own server; start it once with the daemon.
    zonos = zonos3_tts.start_server(cfg.zonos3_port) if cfg.voice_primary in ("elevenlabs", "zonos3") else None
    if zonos:
        logger.info(f"zonos3-server started (pid {zonos.pid}) on port {cfg.zonos3_port}")
    import signal

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        await hub.close()
        if zonos:
            zonos.terminate()
