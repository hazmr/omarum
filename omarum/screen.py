"""What code the user is looking at: the file open in the focused editor. Stdlib only.

Each time the user speaks, Rum checks the focused window. If it's an editor (JetBrains IDEs
such as IntelliJ, or VS Code), it finds that file in the project and gives Rum its code, so
"what does this do?" is about what's on screen. The code is sent again only when the file
changes or the user switches files.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

SKIP_DIRS = {".git", "target", "build", "out", "dist", "node_modules", ".idea", ".gradle", ".venv",
             "venv", "__pycache__", ".next", "bin", "obj"}
MAX_LINES = 400
MAX_BYTES = 24000
_FILE = re.compile(r"[\w.-]+\.[A-Za-z0-9]{1,10}$")


def active_window(run=subprocess.run) -> tuple[str, str] | None:
    try:
        out = run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=2).stdout
        w = json.loads(out or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return (w.get("class", ""), w.get("title", "")) if w else None


def parse_editor(cls: str, title: str) -> tuple[str, str] | None:
    """(project name, file name) from an editor window, or None."""
    cls = cls.lower()
    title = title.lstrip("● *").strip()
    if cls.startswith("jetbrains-") and " – " in title:
        project, rest = title.split(" – ", 1)
        name = rest.split(" [")[0].strip().rsplit("/", 1)[-1]
        return (project.strip(), name) if _FILE.search(name) else None
    if cls in ("code", "code-oss", "vscodium", "codium", "code - oss") and " - " in title:
        parts = [p.strip() for p in title.split(" - ")]
        if len(parts) >= 3 and _FILE.search(parts[0]):
            return parts[1], parts[0]
    return None


def editor_label(cls: str) -> str:
    cls = cls.lower()
    if cls.startswith("jetbrains-"):
        return {"idea": "IntelliJ IDEA", "pycharm": "PyCharm", "webstorm": "WebStorm", "goland": "GoLand",
                "clion": "CLion", "rider": "Rider", "rustrover": "RustRover"}.get(cls[10:], "a JetBrains IDE")
    return "VS Code"


def project_dir(project: str, home: Path = Path.home()) -> Path | None:
    """The project's folder: from IntelliJ's recent projects, else the usual places."""
    for xml in sorted(home.glob(".config/JetBrains/*/options/recentProjects.xml"), reverse=True):
        try:
            text = xml.read_text()
        except OSError:
            continue
        for key in re.findall(r'key="([^"]+)"', text):
            path = Path(key.replace("$USER_HOME$", str(home)))
            if path.name == project and path.is_dir():
                return path
    for base in ("Projects", "IdeaProjects", "Work", "projects", "code", "src", ""):
        path = home / base / project
        if path.is_dir():
            return path
    return None


def find_file(root: Path, name: str) -> Path | None:
    """The file in the project (build output and tool folders skipped); the shortest path wins."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if name in filenames:
            found.append(Path(dirpath) / name)
    return min(found, key=lambda p: (len(p.parts), str(p))) if found else None


class Seen:
    """Which version of which file Rum has already been shown in this conversation."""

    def __init__(self) -> None:
        self.key: tuple[str, float] | None = None


def note_for(path: Path, root: Path, editor: str, seen: Seen) -> str:
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    key = (str(path), path.stat().st_mtime)
    if seen.key == key:
        return f"[Still on screen: {rel} in {editor} (you've seen its code above).]"
    seen.key = key
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    trimmed = len(lines) > MAX_LINES or len(text) > MAX_BYTES
    body = "\n".join(lines[:MAX_LINES])[:MAX_BYTES]
    numbered = "\n".join(f"{i + 1:4} {l}" for i, l in enumerate(body.splitlines()))
    more = f"\n(trimmed: the file has {len(lines)} lines)" if trimmed else ""
    return (f"[On screen: {rel} from the project '{root.name}', open in {editor}. "
            f"Use it only if what they say is about it.]\n{numbered}{more}\n[End of file]")


def current_note(seen: Seen, run=subprocess.run, home: Path = Path.home()) -> str:
    """The note for this turn, or "" when the focused window isn't a code file we can find."""
    win = active_window(run)
    if not win:
        return ""
    parsed = parse_editor(*win)
    if not parsed:
        return ""
    root = project_dir(parsed[0], home)
    path = find_file(root, parsed[1]) if root else None
    if not path:
        return ""
    try:
        return note_for(path, root, editor_label(win[0]), seen)
    except OSError:
        return ""


_LOOK = re.compile(
    r"\b(look(ing)? at (my |the |this |that )?(screen|this|that|it)\b"
    r"|what (do|can|could) you see|(can|could|do) you see (this|that|it|my screen|the screen|what)"
    r"|what('?s| is) on (my|the) screen|(take|grab) a screenshot|screenshot"
    r"|(check|see|about) (my|the) screen)",
    re.IGNORECASE)


def wants_screenshot(said: str) -> bool:
    """Did they ask Rum to look at their screen?"""
    return bool(_LOOK.search(said or ""))


def capture_screenshot(run=subprocess.run) -> bytes | None:
    """A JPEG of the monitor they're on (about 100 KB), or None."""
    try:
        mons = json.loads(run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3).stdout or "[]")
        name = next((m["name"] for m in mons if m.get("focused")), mons[0]["name"] if mons else None)
        cmd = ["grim"] + (["-o", name] if name else []) + ["-t", "jpeg", "-q", "70", "-s", "0.8", "-"]
        r = run(cmd, capture_output=True, timeout=5)
    except (OSError, ValueError, KeyError, IndexError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None
