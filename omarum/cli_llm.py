"""Subscription brains: Codex, Gemini CLI, Kimi and Qwen Code, through the user's own logged-in CLI.

These CLIs have no persistent chat mode we can rely on, so every turn runs one command
with the persona and the conversation so far in the prompt. Each runs in an empty folder
in its most restricted mode (read-only / plan, no session saved). Personal use (spec §3).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from loguru import logger
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.settings import LLMSettings

from omarum.brains import PROVIDERS
from omarum.claude_code_llm import BrainUnavailable

SANDBOX = Path.home() / ".local" / "state" / "omarum" / "brain"
AUTH_WORDS = ("401", "unauthorized", "not logged in", "login", "log in", "sign in", "no auth",
              "auth type", "no model configured", "api key", "credentials")


def cli_command(provider_id: str, model: str, prompt: str) -> tuple[list[str], str | None]:
    """(argv, stdin text or None)."""
    m = ["-m", model] if model else []
    if provider_id == "codex":
        return ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "--color", "never", *m], prompt
    if provider_id == "gemini-cli":
        return ["gemini", "--approval-mode", "default", "-o", "text", *m, "-p", " "], prompt
    if provider_id == "qwen":
        return ["qwen", "--approval-mode", "plan", "-o", "text", *m], prompt
    if provider_id == "kimi":
        return ["kimi", "-p", prompt, "--output-format", "text", *m], None
    raise KeyError(provider_id)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p.get("text", "") if p.get("type") == "text"
                 else "[They showed you a screenshot, but you can't see images with this brain: tell them so.]"
                 for p in content if isinstance(p, dict) and p.get("type") in ("text", "image_url")]
        return " ".join(parts)
    return ""


def build_prompt(system: str, messages: list, user: str, companion: str) -> str:
    names = {"user": user, "assistant": companion}
    lines = [f"{names[m['role']]}: {_text(m.get('content')).strip()}"
             for m in messages if m.get("role") in names and _text(m.get("content")).strip()]
    return (
        f"{system}\n\n"
        f"This is a spoken conversation. Reply as {companion} with only the words to say out loud: "
        f"no markdown, no lists, no stage directions, and don't use any tools.\n\n"
        + "\n".join(lines) + f"\n{companion}:"
    )


def error_reason(provider_id: str, stderr: str, code: int) -> str:
    p = PROVIDERS[provider_id]
    low = stderr.lower()
    if any(w in low for w in AUTH_WORDS):
        return f"{p.label} is not logged in. Run: {p.login_hint}"
    last = next((l.strip() for l in reversed(stderr.splitlines()) if l.strip()), "")
    return f"{p.label} failed: {last[:160]}" if last else f"{p.label} failed (exit {code})"


async def run_streaming(cmd: list[str], stdin: str | None, cwd: Path, provider_id: str):
    """Yield stdout as it arrives (line by line); raise BrainUnavailable on failure.

    Closing the generator early (an interruption) kills the process.
    """
    cwd.mkdir(parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1"}, limit=1 << 22,
        )
    except FileNotFoundError as exc:
        raise BrainUnavailable(f"{PROVIDERS[provider_id].label} is not installed ({cmd[0]} not found)") from exc
    stderr_task = asyncio.create_task(proc.stderr.read())
    finished = False
    try:
        if stdin is not None:
            proc.stdin.write(stdin.encode())
            await proc.stdin.drain()
            proc.stdin.close()
        while line := await proc.stdout.readline():
            yield line.decode(errors="replace")
        code = await proc.wait()
        finished = True
        err = (await stderr_task).decode(errors="replace")
        if code != 0:
            raise BrainUnavailable(error_reason(provider_id, err, code))
    finally:
        if not finished and proc.returncode is None:
            proc.kill()
            await proc.wait()
        if not stderr_task.done():
            stderr_task.cancel()


async def pump(cmd: list[str], stdin: str | None, cwd: Path, provider_id: str, sink) -> None:
    """Hand every chunk to `sink`; however this ends (done, error, interruption), the CLI is gone."""
    from contextlib import aclosing

    async with aclosing(run_streaming(cmd, stdin, cwd, provider_id)) as chunks:
        async for chunk in chunks:
            await sink(chunk)


class CliLLMService(LLMService):
    reports_own_errors = True  # through on_error, with a better reason

    def __init__(self, *, provider_id: str, model: str, system_prompt: str, user: str, companion: str,
                 on_error=None, **kwargs) -> None:
        settings = LLMSettings(
            model=model or provider_id, system_instruction=system_prompt, temperature=None, max_tokens=None,
            top_p=None, top_k=None, frequency_penalty=None, presence_penalty=None, seed=None,
            filter_incomplete_user_turns=None, user_turn_completion_config=None,
        )
        super().__init__(settings=settings, **kwargs)
        self._provider_id = provider_id
        self._model = model
        self._system = system_prompt
        self._user = user
        self._companion = companion
        self._on_error = on_error

    async def _respond(self, messages: list) -> None:
        prompt = build_prompt(self._system, messages, self._user, self._companion)
        cmd, stdin = cli_command(self._provider_id, self._model, prompt)
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            await pump(cmd, stdin, SANDBOX, self._provider_id, self._push_llm_text)
        finally:
            await self.push_frame(LLMFullResponseEndFrame())

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            messages = frame.context.get_messages()
            if not any(m.get("role") == "user" and _text(m.get("content")).strip() for m in messages):
                return
            try:
                await self._respond(messages)
            except BrainUnavailable as exc:
                logger.error(f"brain unavailable: {exc}")
                await self.push_error(ErrorFrame(error=str(exc)))
                if self._on_error:
                    self._on_error(str(exc))
        else:
            await self.push_frame(frame, direction)
