"""Reading saved transcripts. Stdlib only."""

from __future__ import annotations

import json
from pathlib import Path


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
