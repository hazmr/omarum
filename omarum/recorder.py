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

from omarum.transcripts import read_transcript  # noqa: F401  (re-exported)


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


def write_wav(path: Path, pcm16: bytes, sample_rate: int) -> None:
    import wave

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16)


def compress_to_opus(wav: Path, ffmpeg: str | None = "auto") -> Path:
    """WAV -> Opus (24 kbps speech). Keeps the WAV if ffmpeg is missing or fails."""
    import shutil
    import subprocess

    if ffmpeg == "auto":
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return wav
    out = wav.with_suffix(".opus")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libopus", "-b:a", "24k", str(out)],
            check=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        out.unlink(missing_ok=True)
        return wav
    wav.unlink(missing_ok=True)
    return out


class Session:
    """One conversation's folder: transcript as it happens, audio and meta when it ends."""

    def __init__(self, store, cfg, started: datetime) -> None:
        self.cfg = cfg
        self.started = started
        self.dir = store.new_conversation(started)
        self.transcript = TranscriptWriter(self.dir / "transcript.jsonl")
        self._audio: tuple[bytes, bytes, int] | None = None
        self.meta: dict = {}  # filled in by the pipeline (brain, voices, latencies)

    def add_audio(self, user_pcm: bytes, companion_pcm: bytes, sample_rate: int) -> None:
        self._audio = (user_pcm, companion_pcm, sample_rate)

    def close(self, meta: dict) -> Path | None:
        """Write audio + meta.json; a conversation where nobody said anything leaves no folder."""
        import shutil

        if self.transcript.lines == 0:
            shutil.rmtree(self.dir, ignore_errors=True)
            return None
        if self.cfg.record_audio and self._audio:
            user, companion, rate = self._audio
            for name, pcm in (("user", user), ("companion", companion)):
                if pcm:
                    wav = self.dir / f"{name}.wav"
                    write_wav(wav, pcm, rate)
                    compress_to_opus(wav)
        record = {"started": self.started.isoformat(timespec="seconds"),
                  "ended": datetime.now().isoformat(timespec="seconds"), **meta}
        (self.dir / "meta.json").write_text(json.dumps(record, indent=2))
        return self.dir
