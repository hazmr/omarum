"""Rum's loudness: scales the voice just before the speakers (with clipping, never wrapping)."""

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


class Volume(FrameProcessor):
    def __init__(self, gain: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.gain = gain

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame) and self.gain != 1.0:
            frame.audio = scale_pcm16(frame.audio, self.gain)
        await self.push_frame(frame, direction)
