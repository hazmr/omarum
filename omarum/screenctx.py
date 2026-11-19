"""The step before the brain that adds the code on screen to what the user just said."""

from __future__ import annotations

import asyncio

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from omarum import screen


class ScreenContext(FrameProcessor):
    def __init__(self, note=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen = screen.Seen()
        self._note = note or (lambda: screen.current_note(self._seen))

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                note = await asyncio.to_thread(self._note)
            except Exception:  # never let a window lookup break the conversation
                note = ""
            if note:
                messages = list(frame.context.get_messages())
                for i in range(len(messages) - 1, -1, -1):
                    m = messages[i]
                    if m.get("role") == "user" and isinstance(m.get("content"), str):
                        messages[i] = {**m, "content": f"{note}\n\n{m['content']}"}
                        frame.context.set_messages(messages)
                        break
        await self.push_frame(frame, direction)
