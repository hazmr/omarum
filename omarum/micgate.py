"""First stop after the microphone: lets your voice through only when it should, and can stop Rum."""

from __future__ import annotations

from pipecat.frames.frames import Frame, InputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class MicGate(FrameProcessor):
    """Closed: audio becomes silence of the same length (so voice detection sees you stop)."""

    def __init__(self, open_: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self.is_open = open_
        self.breaker: "Breaker | None" = None  # where interruptions are sent from (see Breaker)

    def set_open(self, open_: bool) -> None:
        self.is_open = open_

    async def interrupt(self) -> None:
        """Stop Rum mid-sentence, exactly as if the user had started talking."""
        await (self.breaker or self).broadcast_interruption()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and not self.is_open:
            frame = InputAudioRawFrame(
                audio=bytes(len(frame.audio)), sample_rate=frame.sample_rate, num_channels=frame.num_channels
            )
        await self.push_frame(frame, direction)


class Breaker(FrameProcessor):
    """Sits just after the user aggregator. Interruptions sent from here reach the brain, the voice
    and the speakers directly; sent from the mic, the aggregator drops them while it mutes the user
    (mute_while_speaking), so a push-to-talk press couldn't stop Rum."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
