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


import shutil
import wave

import pytest

from omarum.config import Config
from omarum.recorder import Session, compress_to_opus, write_wav
from omarum.store import Store

PCM = b"\x10\x00\xf0\xff" * 800  # 0.1 s of 16 kHz mono 16-bit


def test_write_wav_roundtrip(tmp_path: Path):
    p = tmp_path / "a.wav"
    write_wav(p, PCM, 16000)
    with wave.open(str(p)) as w:
        assert w.getframerate() == 16000 and w.getnframes() == 1600 and w.getnchannels() == 1


def test_compress_falls_back_without_ffmpeg(tmp_path: Path):
    p = tmp_path / "a.wav"
    write_wav(p, PCM, 16000)
    assert compress_to_opus(p, ffmpeg=None) == p and p.exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_compress_with_ffmpeg(tmp_path: Path):
    p = tmp_path / "a.wav"
    write_wav(p, PCM * 10, 16000)
    out = compress_to_opus(p)
    assert out.suffix == ".opus" and out.exists() and not p.exists()


def _session(tmp_path: Path, **cfg) -> Session:
    store = Store(tmp_path)
    store.ensure()
    return Session(store, Config(**cfg), datetime(2026, 11, 19, 21, 40))


def test_empty_session_leaves_no_folder(tmp_path: Path):
    s = _session(tmp_path)
    s.add_audio(PCM, PCM, 16000)
    assert s.close({}) is None
    assert not s.dir.exists()


def test_session_close_writes_meta_and_audio(tmp_path: Path):
    s = _session(tmp_path)
    s.transcript.add("user", "hello", datetime(2026, 11, 19, 21, 40, 3))
    s.add_audio(PCM, PCM, 16000)
    d = s.close({"voices": ["zonos3", "kokoro"], "latency_ms": [800]})
    meta = json.loads((d / "meta.json").read_text())
    assert meta["started"] == "2026-11-19T21:40:00" and "ended" in meta and meta["voices"] == ["zonos3", "kokoro"]
    assert any(d.glob("user.*")) and any(d.glob("companion.*"))


def test_record_audio_off_writes_no_audio(tmp_path: Path):
    s = _session(tmp_path, record_audio=False)
    s.transcript.add("user", "hello", datetime(2026, 11, 19, 21, 40, 3))
    s.add_audio(PCM, PCM, 16000)
    d = s.close({})
    assert not any(d.glob("user.*")) and not any(d.glob("companion.*"))
    assert (d / "transcript.jsonl").exists()
