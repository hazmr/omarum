"""Pipeline taps that turn frames into orb events (state + audio level)."""

from __future__ import annotations

import array
import math
import time
from typing import Callable

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

Emit = Callable[[dict], None]
LEVEL_INTERVAL = 0.033


def rms_level(pcm16: bytes) -> float:
    """0..1 loudness of 16-bit little-endian PCM, boosted so speech looks lively."""
    if len(pcm16) < 2:
        return 0.0
    samples = array.array("h", pcm16[: len(pcm16) // 2 * 2])
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return min(1.0, math.sqrt(rms / 32768) * 1.6)


class LatencyClock:
    """Measures end of user speech -> first companion audio, once per turn."""

    def __init__(self) -> None:
        self.user_stopped_at: float | None = None
        self.samples: list[float] = []

    def user_stopped(self) -> None:
        self.user_stopped_at = time.monotonic()

    def companion_audio(self) -> float | None:
        if self.user_stopped_at is None:
            return None
        ms = (time.monotonic() - self.user_stopped_at) * 1000
        self.user_stopped_at = None
        self.samples.append(ms)
        logger.info(f"latency_ms={ms:.0f}")
        return ms


class StateTap(FrameProcessor):
    """Passes every frame through; emits orb events for one side of the talk."""

    def __init__(self, emit: Emit, who: str, clock: LatencyClock, **kwargs) -> None:
        super().__init__(**kwargs)
        self._emit = emit
        self._who = who
        self._clock = clock
        self._last_level = 0.0

    def _level(self, audio: bytes) -> None:
        now = time.monotonic()
        if now - self._last_level >= LEVEL_INTERVAL:
            self._last_level = now
            who = "companion" if self._who == "speaker" else self._who
            self._emit({"type": "level", "who": who, "value": round(rms_level(audio), 3)})

    def _state(self, state: str) -> None:
        self._emit({"type": "state", "state": state})

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._who == "user":
            if isinstance(frame, InputAudioRawFrame):
                self._level(frame.audio)
            elif isinstance(frame, UserStartedSpeakingFrame):
                self._state("user_speaking")
            elif isinstance(frame, UserStoppedSpeakingFrame):
                self._clock.user_stopped()
                self._state("thinking")
        elif self._who == "speaker":
            # After the speaker output: frames arrive in 10 ms pieces right after each is
            # played, so these levels move with the words actually heard.
            if isinstance(frame, OutputAudioRawFrame):
                self._level(frame.audio)
        else:
            if isinstance(frame, OutputAudioRawFrame):
                if self._clock.user_stopped_at is not None:
                    self._clock.companion_audio()
            elif isinstance(frame, BotStartedSpeakingFrame):
                self._state("speaking")  # audio is actually playing (comes upstream from the transport)
            elif isinstance(frame, BotStoppedSpeakingFrame):
                self._state("listening")
        await self.push_frame(frame, direction)
