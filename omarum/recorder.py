"""Recording a conversation: a crash-safe transcript and both voices (spec §6.2)."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TranscriptWriter:
    """Append-only JSONL; every line is flushed and fsynced so a crash loses nothing said."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lines = 0

    def add(self, who: str, text: str, at: datetime) -> None:
        text = text.strip()
        if not text:
            return
        record = {"at": at.isoformat(timespec="seconds"), "who": who, "text": text}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.lines += 1


def read_transcript(path: Path) -> list[dict]:
    rows = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("text"):
            rows.append(row)
    return rows


class TranscriptTap(FrameProcessor):
    """User side: final transcriptions. Companion side: each reply, joined from streamed text."""

    def __init__(self, writer: TranscriptWriter, who: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._writer = writer
        self._who = who
        self._reply: list[str] = []

    def _flush_reply(self) -> None:
        if self._reply:
            self._writer.add("companion", "".join(self._reply), datetime.now())
            self._reply = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if self._who == "user":
            if isinstance(frame, TranscriptionFrame):
                self._writer.add("user", frame.text, datetime.now())
        else:
            if isinstance(frame, LLMFullResponseStartFrame):
                self._reply = []
            elif isinstance(frame, LLMTextFrame):
                self._reply.append(frame.text)
            elif isinstance(frame, (LLMFullResponseEndFrame, InterruptionFrame)):
                self._flush_reply()  # an interrupted reply is still recorded, as far as it got
        await self.push_frame(frame, direction)
