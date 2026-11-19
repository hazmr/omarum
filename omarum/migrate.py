"""Remove what the old installer (phase 5) put outside the plugin. Idempotent; stdlib only.

Each item is removed only when it is recognisably Omarum's, so a user's own files stay.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from omarum.integration import remove_menu_entries, remove_require


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, capture_output=True, timeout=60)


def _has(path: Path, marker: str) -> bool:
    try:
        return path.is_file() and marker in path.read_text()
    except (OSError, UnicodeDecodeError):
        return False


def run(home: Path = Path.home(), run=_run) -> list[str]:
    cfg, share = home / ".config", home / ".local" / "share"
    done: list[str] = []

    units = [cfg / "systemd/user" / u for u in ("omarum.service", "omarum-orb.service")]
    if any(_has(u, "Omarum") for u in units):
        run(["systemctl", "--user", "disable", "--now", "omarum-orb.service", "omarum.service"])
        for u in units:
            if _has(u, "Omarum"):
                u.unlink()
        run(["systemctl", "--user", "daemon-reload"])
        done.append("stopped and removed the old systemd services")

    lua = cfg / "hypr/omarum.lua"
    if _has(lua, "Written by Omarum"):
        lua.unlink()
        done.append("removed ~/.config/hypr/omarum.lua")
    bindings = cfg / "hypr/bindings.lua"
    if _has(bindings, "hypr.omarum"):
        bindings.write_text(remove_require(bindings.read_text()))
        done.append("removed the Omarum line from bindings.lua")
    if done and any("hypr" in d or "bindings" in d for d in done):
        run(["hyprctl", "reload"])

    menu = cfg / "omarchy/extensions/omarchy-menu.jsonc"
    if _has(menu, '"omarum'):
        new = remove_menu_entries(menu.read_text())
        if new != menu.read_text():
            menu.write_text(new)
            done.append("removed the Omarum menu entries")

    hook = cfg / "omarchy/hooks/theme-set.d/50-omarum"
    if _has(hook, "Added by Omarum"):
        hook.unlink()
        done.append("removed the theme hook")

    old_link = cfg / "omarchy/plugins/omarum"
    if old_link.is_symlink():
        old_link.unlink()
        done.append("removed the old plugins/omarum link")

    desktop = share / "applications/omarum.desktop"
    if _has(desktop, "Exec=omarum settings"):
        desktop.unlink()
        done.append("removed the app launcher entry")

    if (share / "uv/tools/omarum").exists():
        run(["uv", "tool", "uninstall", "omarum"])
        done.append("removed the old omarum command")
    return done


if __name__ == "__main__":
    for line in run():
        print(line)
