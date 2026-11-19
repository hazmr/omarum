"""Rum's brain: the user's own logged-in Claude Code CLI (Pro subscription).

One persistent `claude -p` process in stream-json mode keeps the conversation
history itself; each user turn is written as one JSON line, and text deltas are
streamed back as LLMTextFrames. Personal use only (spec §3).
"""

from __future__ import annotations

import asyncio
import json
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

from omarum.paths import DATA_DIR  # noqa: E402  (re-exported for older imports)


class BrainUnavailable(Exception):
    pass


def claude_command(model: str, system_prompt: str) -> list[str]:
    # Never --bare: it skips the subscription login. --setting-sources "" keeps
    # the user's own hooks/plugins/CLAUDE.md out of Rum's head.
    return [
        "claude", "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--include-partial-messages", "--verbose",
        "--tools", "",
        "--no-session-persistence",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--model", model,
        "--system-prompt", system_prompt,
    ]


def parse_line(line: bytes) -> tuple[str, str | None]:
    """('text', delta) | ('end', None) | ('skip', None); raises BrainUnavailable."""
    try:
        msg = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ("skip", None)
    kind = msg.get("type")
    if kind == "stream_event":
        event = msg.get("event") or {}
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            return ("text", delta.get("text", ""))
    elif kind == "result":
        if msg.get("is_error"):
            raise BrainUnavailable(str(msg.get("result") or msg.get("subtype") or "unknown error"))
        return ("end", None)
    return ("skip", None)


def last_user_text(messages: list) -> str:
    for m in reversed(messages):
        if m.get("role") != "user":
            continue
        content = m.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


class ClaudeCodeLLMService(LLMService):
    def __init__(self, *, model: str, system_prompt: str, on_error=None, **kwargs) -> None:
        # Claude Code owns sampling; declare every setting so pipecat doesn't complain.
        settings = LLMSettings(
            model=model, system_instruction=system_prompt, temperature=None, max_tokens=None,
            top_p=None, top_k=None, frequency_penalty=None, presence_penalty=None, seed=None,
            filter_incomplete_user_turns=None, user_turn_completion_config=None,
        )
        super().__init__(settings=settings, **kwargs)
        self._on_error = on_error
        self._model = model
        self._system_prompt = system_prompt
        self._proc: asyncio.subprocess.Process | None = None
        self._turns_sent = 0
        self._turns_done = 0

    async def start(self, frame) -> None:
        await super().start(frame)
        await self._prewarm()

    async def _prewarm(self) -> None:
        """Spawn claude when the session starts, so the first reply skips startup."""
        try:
            await self._ensure_process()
        except BrainUnavailable as exc:
            if self._on_error:
                self._on_error(str(exc))

    async def _ensure_process(self) -> asyncio.subprocess.Process:
        if self._proc and self._proc.returncode is None:
            return self._proc
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *claude_command(self._model, self._system_prompt),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=DATA_DIR,
                limit=1 << 22,
            )
        except FileNotFoundError as exc:
            raise BrainUnavailable("claude CLI not found") from exc
        self._turns_sent = self._turns_done = 0
        return self._proc

    async def _read_until_turn_end(self, proc, turn: int):
        """Yield text for `turn`; silently drain earlier (interrupted) turns."""
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise BrainUnavailable("claude exited (logged out or usage limit?)")
            kind, text = parse_line(line)
            if kind == "end":
                self._turns_done += 1
                if self._turns_done > turn:
                    return
            elif kind == "text" and self._turns_done == turn and text:
                yield text

    async def _respond(self, text: str) -> None:
        proc = await self._ensure_process()
        turn = self._turns_sent
        self._turns_sent += 1
        msg = {"type": "user", "message": {"role": "user", "content": text}}
        proc.stdin.write((json.dumps(msg) + "\n").encode())
        await proc.stdin.drain()
        await self.push_frame(LLMFullResponseStartFrame())
        try:
            async for chunk in self._read_until_turn_end(proc, turn):
                await self._push_llm_text(chunk)
        finally:
            await self.push_frame(LLMFullResponseEndFrame())

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            text = last_user_text(frame.context.get_messages())
            if not text.strip():
                return
            try:
                await self._respond(text)
            except BrainUnavailable as exc:
                logger.error(f"brain unavailable: {exc}")
                await self.push_error(ErrorFrame(error=str(exc)))
                if self._on_error:
                    self._on_error(str(exc))
        else:
            await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        await super().cleanup()
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
