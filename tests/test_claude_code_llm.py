import json
from pathlib import Path

import pytest

from omarum.claude_code_llm import BrainUnavailable, claude_command, parse_line

FIXTURE = Path(__file__).parent / "fixtures" / "claude_stream_ok.jsonl"


def test_claude_stream_parser():
    parsed = [parse_line(l) for l in FIXTURE.read_bytes().splitlines()]
    texts = [v for kind, v in parsed if kind == "text"]
    assert "".join(texts) == "Hi there! How can I help you today?"
    assert parsed[-1] == ("end", None)


def test_error_result_raises():
    line = json.dumps({"type": "result", "subtype": "error", "is_error": True,
                       "result": "Claude usage limit reached"}).encode()
    with pytest.raises(BrainUnavailable, match="usage limit"):
        parse_line(line)


def test_garbage_line_is_skipped():
    assert parse_line(b"not json") == ("skip", None)


def test_command_never_uses_bare_and_isolates_settings():
    cmd = claude_command("haiku", "be nice")
    assert "--bare" not in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "haiku"
    assert cmd[cmd.index("--system-prompt") + 1] == "be nice"


async def test_start_prewarms_claude_process(monkeypatch):
    from pipecat.frames.frames import StartFrame

    from omarum.claude_code_llm import ClaudeCodeLLMService

    spawned = []

    class FakeProc:
        returncode = None

    async def fake_exec(*args, **kwargs):
        spawned.append(args)
        return FakeProc()

    monkeypatch.setattr("omarum.claude_code_llm.asyncio.create_subprocess_exec", fake_exec)
    svc = ClaudeCodeLLMService(model="haiku", system_prompt="hi")
    await svc._prewarm()
    assert len(spawned) == 1 and spawned[0][0] == "claude"
