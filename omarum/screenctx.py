"""The step before the brain: what's on screen goes with what the user just said.

- The code file open in a focused editor (screen.current_note), every turn.
- A screenshot, only when they ask Rum to look ("look at my screen", "what do you see?"),
  sent for that turn only: older screenshots are replaced by a short placeholder.
"""

from __future__ import annotations

import asyncio
import base64

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from omarum import screen

SHOWN = {"type": "text", "text": "[a screenshot was shown here]"}


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type") == "text")


def _without_images(content):
    if not isinstance(content, list) or not any(p.get("type") == "image_url" for p in content if isinstance(p, dict)):
        return content
    return [SHOWN if isinstance(p, dict) and p.get("type") == "image_url" else p for p in content]


class ScreenContext(FrameProcessor):
    def __init__(self, note=None, screenshot=None, code: bool = True, look: bool = True, **kwargs) -> None:
        super().__init__(**kwargs)
        self._seen = screen.Seen()
        self._note = note or (lambda: screen.current_note(self._seen))
        self._screenshot = screenshot or screen.capture_screenshot
        self._code, self._look = code, look

    async def _add_screen(self, context) -> None:
        messages = [{**m, "content": _without_images(m.get("content"))} if m.get("role") == "user" else m
                    for m in context.get_messages()]
        last = next((i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"), None)
        if last is None:
            context.set_messages(messages)
            return
        said = _text(messages[last].get("content"))
        note = await asyncio.to_thread(self._note) if self._code else ""
        text = f"{note}\n\n{said}" if note else said
        image = await asyncio.to_thread(self._screenshot) if self._look and screen.wants_screenshot(said) else None
        if image:
            url = "data:image/jpeg;base64," + base64.b64encode(image).decode()
            messages[last] = {**messages[last], "content": [
                {"type": "text", "text": f"{text}\n\n[A screenshot of their screen, taken just now, is attached.]"},
                {"type": "image_url", "image_url": {"url": url}}]}
        elif note:
            messages[last] = {**messages[last], "content": text}
        context.set_messages(messages)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            try:
                await self._add_screen(frame.context)
            except Exception:  # never let a window lookup or a screenshot break the conversation
                pass
        await self.push_frame(frame, direction)
