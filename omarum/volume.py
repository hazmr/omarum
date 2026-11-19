"""Rum's loudness, just before the speakers.

Voices come out at very different levels (ZONOS3 "Willow" measured -27 to -33 dBFS,
ElevenLabs "Jessica" -21 with -2 dB peaks), so a fixed boost can't fit them all. The Leveler
brings any voice to about -16 dBFS smoothly, leaves silence alone, never clips, and the user's
volume slider scales the result."""

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

TARGET_DBFS = -16.0   # loud enough for laptop speakers, with room for peaks
SILENCE_DBFS = -50.0  # quieter than this is a pause: don't chase it
MAX_GAIN = 20.0       # about +26 dB at most (for very quiet voices like ZONOS3)
CEILING = 29000       # about -1 dB: peaks are kept under this
KNEE = 22000          # above this, peaks are rounded off softly instead of cut
RISE = 1.15           # the volume rises at most 15 % per 20 ms (no sudden jumps)


def _rms(samples: array.array) -> float:
    return math.sqrt(sum(x * x for x in samples) / len(samples)) if samples else 0.0


def _soft(y: float) -> int:
    """Round off a peak above KNEE so it approaches CEILING but never reaches the hard limit."""
    a = abs(y)
    if a <= KNEE:
        return int(y)
    room = CEILING - KNEE
    return int(math.copysign(KNEE + room * math.tanh((a - KNEE) / room), y))


class Leveler:
    """Automatic, smooth gain for a stream of 16-bit PCM frames.

    The gain glides sample by sample from one frame to the next, rises slowly, drops in time
    for a loud peak (the whole frame is known before it plays), and peaks are rounded softly:
    no jumps and no hard clipping, which is what made loud voices crackle.
    """

    def __init__(self, volume: float = 1.0) -> None:
        self.volume = volume
        self.level: float | None = None  # smoothed loudness of the voice so far
        self.gain = 1.0                  # the gain at the end of the last frame
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
            self.level = rms if self.level is None else 0.9 * self.level + 0.1 * rms
        want = min(MAX_GAIN, max(1.0, self.target / self.level)) * self.volume
        peak = max(abs(x) for x in samples) or 1
        want = min(want, CEILING / peak, self.gain * RISE)  # fits this frame's peak; rises gently
        start, n = self.gain, len(samples)
        self.gain = want
        if abs(start - 1.0) < 1e-3 and abs(want - 1.0) < 1e-3:
            return pcm
        out = array.array("h", (_soft(x * (start + (want - start) * (i + 1) / n)) for i, x in enumerate(samples)))
        return out.tobytes()


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


OUTPUT_FRAMES = 2048  # ~85 ms at 24 kHz: PortAudio's default is a few ms and runs dry under load


def big_output_buffer(py_audio) -> None:
    """Make PyAudio open Rum's speaker stream with a big buffer (Pipecat can't pass one).

    Measured with a screen recorder running: 5 drop-outs (crackles) in 15 s of speech with
    PortAudio's default buffer, 0 with 2048 frames.
    """
    open_ = py_audio.open

    def open_big(*args, **kwargs):
        if kwargs.get("output") and not kwargs.get("frames_per_buffer"):
            kwargs["frames_per_buffer"] = OUTPUT_FRAMES
        return open_(*args, **kwargs)

    py_audio.open = open_big
