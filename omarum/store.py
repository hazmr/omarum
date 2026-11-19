"""Where Rum keeps everything about the user (spec §6.2). Plain files, private to the user.

~/.local/share/omarum/
  persona.md
  memory/profile.md
  memory/journal/YYYY-MM-DD.md
  conversations/YYYY-MM-DD/HHMM-<id>/{user.opus, companion.opus, transcript.jsonl, meta.json}
"""

from __future__ import annotations

import os
import secrets
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from omarum.paths import DATA_DIR


class Store:
    def __init__(self, root: Path = DATA_DIR) -> None:
        self.root = Path(root)

    @property
    def persona_path(self) -> Path:
        return self.root / "persona.md"

    @property
    def profile_path(self) -> Path:
        return self.root / "memory" / "profile.md"

    @property
    def journal_dir(self) -> Path:
        return self.root / "memory" / "journal"

    @property
    def conversations_dir(self) -> Path:
        return self.root / "conversations"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(parents=True, exist_ok=True)

    def new_conversation(self, now: datetime) -> Path:
        day = self.conversations_dir / now.strftime("%Y-%m-%d")
        while True:
            d = day / f"{now.strftime('%H%M%S')}-{secrets.token_hex(3)}"  # seconds keep same-minute talks in order
            try:
                d.mkdir(parents=True)
                return d
            except FileExistsError:
                continue

    def journal_path(self, day: date) -> Path:
        return self.journal_dir / f"{day.isoformat()}.md"

    def conversations_on(self, day: date) -> list[Path]:
        folder = self.conversations_dir / day.isoformat()
        if not folder.is_dir():
            return []
        return sorted(
            d for d in folder.iterdir()
            if (d / "transcript.jsonl").is_file() and (d / "transcript.jsonl").stat().st_size > 0
        )

    def _conversation_days(self) -> list[date]:
        days = []
        if self.conversations_dir.is_dir():
            for d in self.conversations_dir.iterdir():
                try:
                    days.append(date.fromisoformat(d.name))
                except ValueError:
                    continue
        return sorted(days)

    def days_without_journal(self, before: date) -> list[date]:
        return [
            d for d in self._conversation_days()
            if d < before and not self.journal_path(d).exists() and self.conversations_on(d)
        ]

    def prune(self, retention_days: int, now: datetime) -> int:
        if retention_days <= 0:
            return 0
        cutoff = now.date() - timedelta(days=retention_days)
        removed = 0
        for d in self._conversation_days():
            if d < cutoff:
                shutil.rmtree(self.conversations_dir / d.isoformat(), ignore_errors=True)
                removed += 1
        return removed
