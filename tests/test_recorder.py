import json
from datetime import datetime
from pathlib import Path

from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.tests.utils import run_test

from omarum.recorder import TranscriptTap, TranscriptWriter, read_transcript

AT = datetime(2026, 11, 19, 21, 40, 5)


def test_writer_appends_and_flushes(tmp_path: Path):
    p = tmp_path / "transcript.jsonl"
    w = TranscriptWriter(p)
    w.add("user", "hello", AT)
    w.add("companion", "hi there", AT)
    lines = p.read_text().splitlines()  # readable before the writer is closed
    assert [json.loads(l)["who"] for l in lines] == ["user", "companion"]
    assert json.loads(lines[0]) == {"at": "2026-11-19T21:40:05", "who": "user", "text": "hello"}
    assert w.lines == 2


def test_blank_text_ignored(tmp_path: Path):
    w = TranscriptWriter(tmp_path / "t.jsonl")
    w.add("user", "   ", AT)
    assert w.lines == 0


def test_read_transcript_skips_corrupt_line(tmp_path: Path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"who":"user","text":"a"}\n{broken\n{"who":"companion","text":"b"}\n')
    assert [r["text"] for r in read_transcript(p)] == ["a", "b"]


async def test_user_tap_records_transcription(tmp_path: Path):
    w = TranscriptWriter(tmp_path / "t.jsonl")
    await run_test(
        TranscriptTap(w, "user"),
        frames_to_send=[TranscriptionFrame("hello Rum", "", "2026-11-19T21:40:05")],
        expected_down_frames=[TranscriptionFrame],
    )
    assert [(r["who"], r["text"]) for r in read_transcript(w.path)] == [("user", "hello Rum")]


async def test_companion_tap_joins_streamed_reply(tmp_path: Path):
    w = TranscriptWriter(tmp_path / "t.jsonl")
    await run_test(
        TranscriptTap(w, "companion"),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("Hi "),
            LLMTextFrame("there."),
            LLMFullResponseEndFrame(),
        ],
        expected_down_frames=[LLMFullResponseStartFrame, LLMTextFrame, LLMTextFrame, LLMFullResponseEndFrame],
    )
    assert [(r["who"], r["text"]) for r in read_transcript(w.path)] == [("companion", "Hi there.")]
