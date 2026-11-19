import json
import re
from pathlib import Path

from omarum.integration import add_menu_entries, remove_menu_entries, remove_require, render_unit


def parse_like_omarchy(raw: str) -> dict:
    """What Omarchy's MenuModel.js stripJsonc + JSON.parse does."""
    stripped = re.sub(r"^\s*//[^\n]*(\n|$)", "", raw, flags=re.M)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
    return json.loads(stripped) if stripped.strip() else {}

MENU = """{
  // Extend the Quickshell Omarchy menu with JSONC.
  // "personal": {"icon":"","label":"Personal"},
  "work": {"icon":"","label":"Work"},
  "work.notes": {"icon":"","label":"Notes","action":"omarchy-launch-editor ~/notes"}
}
"""

EMPTY = """{
  // Extend the Quickshell Omarchy menu with JSONC.
  // "about": {"icon":"","label":"About"},
}
"""


def test_menu_entries_added_once():
    once = add_menu_entries(MENU)
    assert once.count('"omarum":') == 1
    for key in ("omarum.talk", "omarum.settings", "omarum.restart"):
        assert once.count(f'"{key}":') == 1
    assert '"action":"omarum tap"' in once
    assert '"action":"omarum settings"' in once
    assert '"action":"systemctl --user restart omarum omarum-orb"' in once
    # Nobody else's line is edited: every original line is still there as it was.
    for line in MENU.splitlines():
        assert line in once.splitlines()
    assert add_menu_entries(once) == once
    menu = parse_like_omarchy(once)
    assert menu["omarum"]["label"] == "Omarum"
    assert menu["omarum.talk"]["action"] == "omarum tap"
    assert menu["work.notes"]["label"] == "Notes"


def test_menu_entries_into_empty_extension_file():
    out = add_menu_entries(EMPTY)
    assert out.count('"omarum.talk":') == 1
    # Comments stay as they were; no comma is added to a comment line.
    assert '  // "about": {"icon":"","label":"About"},\n' in out
    assert "// Extend the Quickshell Omarchy menu with JSONC." in out
    assert add_menu_entries(out) == out
    assert set(parse_like_omarchy(out)) == {"omarum", "omarum.talk", "omarum.settings", "omarum.restart"}


def test_menu_entries_with_trailing_comma_already():
    text = MENU.replace('~/notes"}\n', '~/notes"},\n')
    out = add_menu_entries(text)
    assert ",," not in out
    assert out.count('~/notes"},') == 1
    assert "work.notes" in parse_like_omarchy(out)


def test_menu_entries_into_missing_or_blank_file():
    out = add_menu_entries("")
    assert set(parse_like_omarchy(out)) == {"omarum", "omarum.talk", "omarum.settings", "omarum.restart"}
    assert remove_menu_entries(out) == "{\n}\n"


def test_menu_entries_removed_cleanly():
    assert remove_menu_entries(add_menu_entries(MENU)) == MENU
    assert remove_menu_entries(add_menu_entries(EMPTY)) == EMPTY
    assert remove_menu_entries(MENU) == MENU


def test_render_unit():
    tpl = "ExecStart=@OMARUM@ daemon\nWorkingDirectory=@REPO@\nExecStart=@REPO@/bin/omarum-orb\n"
    out = render_unit(tpl, Path("/home/u/omarum"), "/home/u/.local/bin/omarum")
    assert out == (
        "ExecStart=/home/u/.local/bin/omarum daemon\n"
        "WorkingDirectory=/home/u/omarum\n"
        "ExecStart=/home/u/omarum/bin/omarum-orb\n"
    )
    assert "@" not in out


def test_remove_require_only_ours():
    lua = (
        'o.bind("SUPER + SHIFT + L", "Lock screen explorer", "omarchy-shell lock explore")\n'
        "\n"
        "-- Omarum voice companion\n"
        'pcall(require, "hypr.omarum")\n'
        "\n"
        "-- Mine\n"
        'pcall(require, "hypr.mine")\n'
    )
    out = remove_require(lua)
    assert "hypr.omarum" not in out
    assert "Omarum voice companion" not in out
    assert 'pcall(require, "hypr.mine")' in out
    assert "-- Mine" in out
    assert 'o.bind("SUPER + SHIFT + L"' in out
    assert remove_require(out) == out
    # What shortcuts.apply appends to a file is removed exactly.
    base = 'o.bind("A", "a", "a")\n'
    assert remove_require(base + '\n-- Omarum voice companion\npcall(require, "hypr.omarum")\n') == base
