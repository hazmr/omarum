"""Session control: one conversation at a time, driven by socket commands."""

from __future__ import annotations

import asyncio
import shutil
import time
from typing import Awaitable, Callable

from loguru import logger

from omarum.config import Config
from omarum.memory import update_profile, write_journal
from omarum.recorder import read_transcript
from omarum.store import Store
from omarum.orbstate import USER_VOICE_THRESHOLD

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
        store: Store | None = None,
        memory_runner: Callable[[Callable[[], None]], None] | None = None,
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
        self._recording = None  # the current conversation's Session
        self.store = store or Store()
        self._memory_runner = memory_runner or self._background
        self._memory_jobs = 0
        self._executor = None
        self._audio_free_at = 0.0  # monotonic time when the last session's audio threads are done

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
            if new == "error" and self._active:
                asyncio.create_task(self._end())  # a broken session must not keep the mic open
        else:
            if msg.get("who") == "user" and msg.get("value", 0) >= USER_VOICE_THRESHOLD:
                self._listening_since = time.monotonic()  # the user is talking: not idle
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
        r = {"ok": ok, "state": self.state, "memory": "updating" if self._memory_jobs else "idle"}
        if self.reason:
            r["reason"] = self.reason
        return r

    @property
    def _active(self) -> bool:
        return self._runner is not None and not self._runner.done()

    # -- memory (runs in one background thread, never blocks a conversation) ---
    def _background(self, job: Callable[[], None]) -> None:
        if self._executor is None:
            from concurrent.futures import ThreadPoolExecutor

            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omarum-memory")
        self._executor.submit(job)

    def _queue(self, job: Callable[[], None]) -> None:
        def run() -> None:
            try:
                job()
            except Exception:
                logger.exception("memory job failed")
            finally:
                self._memory_jobs -= 1

        self._memory_jobs += 1
        self._memory_runner(run)

    def _save_conversation(self) -> None:
        rec, self._recording = self._recording, None
        if rec is None:
            return
        cfg, store = self.cfg, self.store

        def job() -> None:
            folder = rec.close(rec.meta)  # audio compression happens here, off the event loop
            if folder:
                update_profile(store, read_transcript(folder / "transcript.jsonl"), cfg)

        self._queue(job)

    def on_startup(self, now) -> None:
        """Catch up on journals for past days, then apply the retention policy."""
        for day in self.store.days_without_journal(now.date()):
            self._queue(lambda day=day: write_journal(self.store, day, self.cfg))
        self._queue(lambda: self.store.prune(self.cfg.retention_days, now))

    # -- commands ------------------------------------------------------------
    async def handle(self, cmd: dict) -> dict:
        match cmd.get("cmd"):
            case "status":
                return self._reply()
            case "reload":
                self.hub.broadcast({"type": "reload"})  # the orb re-reads config and theme
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
            # PyAudio write threads outlive a cancelled pipeline briefly; reopening ALSA
            # while one still writes to the closed stream segfaults (seen 2026-11-19).
            wait = self._audio_free_at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._session += 1
            emit = self._emitter(self._session)
            task, self._stop, self._recording = await asyncio.to_thread(self._factory, self.cfg, emit)
        except Exception as exc:  # no mic, model load failure, ...
            logger.exception("could not start a session")
            self._set_state("error", str(exc))
            return self._reply(ok=False)
        finally:
            self._starting = False
        self._runner = asyncio.create_task(self._run(task, self._session))
        self._watchdog = asyncio.create_task(self._watch_idle())
        self._set_state("listening")
        return self._reply()

    async def _run(self, task, session: int) -> None:
        try:
            await self._run_task(task)
        except Exception as exc:
            logger.exception("session crashed")
            self._set_state("error", str(exc))
        finally:
            if session == self._session:  # ended on its own, not through _end()
                self._session += 1
                self._save_conversation()
                self._audio_free_at = time.monotonic() + self.cfg.audio_release_secs
                if self.state != "error":
                    self._set_state("closed")

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
        self._audio_free_at = time.monotonic() + self.cfg.audio_release_secs
        self._save_conversation()
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
    daemon.store.ensure()
    from datetime import datetime

    daemon.on_startup(datetime.now())
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
