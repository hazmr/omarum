"""Saving settings: config.toml (keeps comments and unknown keys) and secrets in env (mode 600). Stdlib only."""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path

from omarum.config import CONFIG_PATH

ENV_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarum" / "env"


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def _atomic_write(path: Path, text: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def save_config(updates: dict, path: Path = CONFIG_PATH) -> None:
    try:
        old_text = path.read_text()
    except FileNotFoundError:
        old_text = ""
    try:
        current = tomllib.loads(old_text)
    except tomllib.TOMLDecodeError:
        current = {}
    header = []
    for line in old_text.splitlines():
        if line.startswith("#") or (header and not line.strip()):
            header.append(line)
        else:
            break
    merged = {**current, **updates}
    body = [f"{k} = {_toml_value(v)}" for k, v in merged.items() if not isinstance(v, (dict, list))]
    text = "\n".join([*(l for l in header if l.strip()), *body]) + "\n"
    _atomic_write(path, text)


def _env_lines(path: Path) -> list[str]:
    try:
        return path.read_text().splitlines()
    except OSError:
        return []


def set_secret(name: str, value: str, path: Path = ENV_PATH) -> None:
    lines = [l for l in _env_lines(path) if not l.startswith(f"{name}=")]
    if value:
        lines.append(f"{name}={value}")
    _atomic_write(path, "\n".join(lines) + ("\n" if lines else ""), mode=0o600)


def has_secret(name: str, path: Path = ENV_PATH) -> bool:
    return any(l.startswith(f"{name}=") and len(l) > len(name) + 1 for l in _env_lines(path))


def get_secret(name: str, path: Path = ENV_PATH) -> str:
    for line in _env_lines(path):
        if line.startswith(f"{name}="):
            return line[len(name) + 1:].strip()
    return ""
