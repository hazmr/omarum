import asyncio
import sys

import pytest

from omarum.cli_llm import build_prompt, cli_command, error_reason, run_streaming


def test_commands_are_isolated():
    codex, stdin = cli_command("codex", "gpt-5", "PROMPT")
    assert codex[:2] == ["codex", "exec"]
    for flag in ("--skip-git-repo-check", "--ephemeral", "read-only"):
        assert flag in codex
    assert codex[codex.index("-m") + 1] == "gpt-5" and stdin == "PROMPT"
    assert "-m" not in cli_command("codex", "", "P")[0]

    qwen, stdin = cli_command("qwen", "", "PROMPT")
    assert qwen[0] == "qwen" and "plan" in qwen and stdin == "PROMPT"

    gemini, stdin = cli_command("gemini-cli", "gemini-2.5-flash", "PROMPT")
    assert gemini[0] == "gemini" and "gemini-2.5-flash" in gemini and stdin == "PROMPT"

    kimi, stdin = cli_command("kimi", "", "PROMPT")
    assert kimi == ["kimi", "-p", "PROMPT", "--output-format", "text"] and stdin is None

    with pytest.raises(KeyError):
        cli_command("claude-code", "", "P")  # Claude Code has its own persistent service


def test_build_prompt_carries_history():
    messages = [
        {"role": "system", "content": "ignored, the persona comes separately"},
        {"role": "user", "content": "My cat is called Miso."},
        {"role": "assistant", "content": "Miso is a lovely name."},
        {"role": "user", "content": [{"type": "text", "text": "What's my cat called?"}]},
    ]
    p = build_prompt("You are Rum.", messages, user="Hazem", companion="Rum")
    assert p.startswith("You are Rum.")
    assert "Hazem: My cat is called Miso." in p
    assert "Rum: Miso is a lovely name." in p
    assert "Hazem: What's my cat called?" in p
    assert p.rstrip().endswith("Rum:")
    assert "ignored" not in p


def test_auth_error_reason():
    assert error_reason("codex", "ERROR: unexpected status 401 Unauthorized: Missing bearer", 1) == \
        "Codex is not logged in. Run: codex login"
    assert error_reason("kimi", "error: failed to run prompt: No model configured. Run `kimi` and use /login", 1) == \
        "Kimi is not logged in. Run: kimi  (then /login)"
    assert error_reason("qwen", "boom\nsomething else broke\n", 2) == "Qwen Code failed: something else broke"
    assert error_reason("qwen", "", 3) == "Qwen Code failed (exit 3)"


def _script(tmp_path, body: str):
    f = tmp_path / "fake.py"
    f.write_text(body)
    return [sys.executable, str(f)]


def test_run_streaming_yields_lines(tmp_path):
    cmd = _script(tmp_path, "import sys\nprint('Hello there.', flush=True)\nprint('How are you?', flush=True)\n")

    async def go():
        return [chunk async for chunk in run_streaming(cmd, None, tmp_path, "codex")]

    assert "".join(asyncio.run(go())) == "Hello there.\nHow are you?\n"


def test_run_streaming_failure_raises_reason(tmp_path):
    from omarum.claude_code_llm import BrainUnavailable

    cmd = _script(tmp_path, "import sys\nsys.stderr.write('401 Unauthorized\\n')\nsys.exit(1)\n")

    async def go():
        return [chunk async for chunk in run_streaming(cmd, None, tmp_path, "codex")]

    with pytest.raises(BrainUnavailable, match="Codex is not logged in"):
        asyncio.run(go())


def test_run_streaming_kills_on_cancel(tmp_path):
    pidfile = tmp_path / "pid"
    cmd = _script(tmp_path, f"import os,time\nopen({str(pidfile)!r},'w').write(str(os.getpid()))\n"
                            "print('first', flush=True)\ntime.sleep(30)\n")

    async def go():
        gen = run_streaming(cmd, None, tmp_path, "codex")
        assert (await gen.__anext__()) == "first\n"
        await gen.aclose()  # what an interruption does

    asyncio.run(go())
    import os

    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
