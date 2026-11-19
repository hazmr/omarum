"""Omarchy integration edits used by scripts/install.sh and scripts/uninstall.sh. Stdlib only.

Every edit is idempotent and reversible: Omarum adds whole lines of its own and
removes exactly those lines, never touching anyone else's.

    python -m omarum.integration menu-add|menu-remove FILE
    python -m omarum.integration unit TEMPLATE OUT REPO OMARUM_BIN
    python -m omarum.integration unrequire BINDINGS_LUA
"""

from __future__ import annotations

import sys
from pathlib import Path

MENU_KEYS = ("omarum", "omarum.talk", "omarum.settings", "omarum.restart")
MENU_LINES = [
    '  "omarum": {"icon":"󰪥","label":"Omarum"},',
    '  "omarum.talk": {"icon":"󰍬","label":"Talk to Rum","action":"omarum tap"},',
    '  "omarum.settings": {"icon":"󰒓","label":"Settings","action":"omarum settings"},',
    '  "omarum.restart": {"icon":"󰜉","label":"Restart","action":"systemctl --user restart omarum omarum-orb"},',
]
REQUIRE_LINES = ("-- Omarum voice companion", 'pcall(require, "hypr.omarum")')


def _is_ours(line: str) -> bool:
    s = line.strip()
    return any(s.startswith(f'"{key}":') for key in MENU_KEYS)


def add_menu_entries(jsonc: str) -> str:
    """Put Omarum's submenu right after the opening `{`.

    Each line ends with a comma; Omarchy's menu reader drops trailing commas, so
    nothing else in the file has to change.
    """
    if any(_is_ours(line) for line in jsonc.splitlines()):
        return jsonc
    if not jsonc.strip():
        jsonc = "{\n}\n"
    lines = jsonc.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip().startswith("{"):
            break
    else:
        raise ValueError("not a JSONC object: no opening '{'")
    if not lines[i].endswith("\n"):
        lines[i] += "\n"
    return "".join(lines[: i + 1] + [m + "\n" for m in MENU_LINES] + lines[i + 1 :])


def remove_menu_entries(jsonc: str) -> str:
    return "".join(line for line in jsonc.splitlines(keepends=True) if not _is_ours(line))


def render_unit(template: str, repo: Path, omarum_bin: str) -> str:
    return template.replace("@REPO@", str(repo)).replace("@OMARUM@", omarum_bin)


def remove_require(bindings_lua: str) -> str:
    """Drop the block shortcuts.apply appended (with the blank line before it), nothing else."""
    lines = bindings_lua.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].rstrip("\n") == REQUIRE_LINES[0] and i + 1 < len(lines) and lines[i + 1].strip() == REQUIRE_LINES[1]:
            if out and not out[-1].strip():
                out.pop()
            i += 2
            continue
        if lines[i].strip() == REQUIRE_LINES[1]:
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def _edit(path: Path, fn) -> None:
    old = path.read_text() if path.exists() else ""
    new = fn(old)
    if new != old:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new)


def main(argv: list[str]) -> int:
    match argv:
        case ["menu-add", f]:
            _edit(Path(f), add_menu_entries)
        case ["menu-remove", f]:
            if Path(f).exists():
                _edit(Path(f), remove_menu_entries)
        case ["unit", tpl, out, repo, omarum_bin]:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(render_unit(Path(tpl).read_text(), Path(repo), omarum_bin))
        case ["unrequire", f]:
            if Path(f).exists():
                _edit(Path(f), remove_require)
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
