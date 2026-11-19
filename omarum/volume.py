"""Rum's loudness, just before the speakers.

Voices come out at very different levels (ZONOS3 "Willow" measured -27 to -33 dBFS), so a
fixed boost can't fit them all. The Leveler brings any voice to about -14 dBFS (as loud as
videos and music, which laptop speakers need), leaves silence alone, never clips, and the
user's volume slider scales the result."""

from __future__ import annotations

import array

from pipecat.frames.frames import Frame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


def scale_pcm16(pcm: bytes, gain: float) -> bytes:
    if gain == 1.0:
        return pcm
    samples = array.array("h", pcm[: len(pcm) // 2 * 2])
    out = array.array("h", (max(-32768, min(32767, int(s * gain))) for s in samples))
    return out.tobytes()


import math

TARGET_DBFS = -14.0   # as loud as videos and music; laptop speakers need it
SILENCE_DBFS = -50.0  # quieter than this is a pause: don't chase it
MAX_GAIN = 20.0       # about +26 dB at most
PEAK_LIMIT = 32000


def _rms(samples: array.array) -> float:
    return math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0.0


class Leveler:
    """Automatic gain for a stream of 16-bit PCM frames."""

    def __init__(self, volume: float = 1.0) -> None:
        self.volume = volume
        self.level: float | None = None  # smoothed loudness of the voice so far
        self.target = 32768 * 10 ** (TARGET_DBFS / 20)
        self.silence = 32768 * 10 ** (SILENCE_DBFS / 20)

    def process(self, pcm: bytes) -> bytes:
        samples = array.array("h", pcm[: len(pcm) // 2 * 2])
        if not samples:
            return pcm
        rms = _rms(samples)
        if rms < self.silence and self.level is None:
            return pcm  # nothing heard yet: leave the hiss alone
        if rms >= self.silence:
            self.level = rms if self.level is None else 0.85 * self.level + 0.15 * rms
        gain = min(MAX_GAIN, max(1.0, self.target / self.level)) * self.volume
        peak = max(abs(x) for x in samples)
        if peak * gain > PEAK_LIMIT:
            gain = PEAK_LIMIT / peak  # a loud syllable: limit, never clip
        if abs(gain - 1.0) < 1e-3:
            return pcm
        return array.array("h", (int(x * gain) for x in samples)).tobytes()


class Volume(FrameProcessor):
    """Levels Rum's voice (Leveler), then applies the user's volume (1.0 = 100%)."""

    def __init__(self, gain: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.gain = gain
        self.leveler = Leveler(volume=gain)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame):
            frame.audio = self.leveler.process(frame.audio)
        await self.push_frame(frame, direction)
