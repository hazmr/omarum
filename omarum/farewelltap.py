"""Right after speech recognition: tell the daemon when the user says goodbye."""

from __future__ import annotations

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from omarum.farewell import is_farewell


class FarewellTap(FrameProcessor):
    def __init__(self, emit, **kwargs) -> None:
        super().__init__(**kwargs)
        self._emit = emit

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and is_farewell(frame.text):
            self._emit({"type": "farewell"})
        await self.push_frame(frame, direction)
