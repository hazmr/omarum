from omarum.config import Config
from omarum.shortcuts import conflicts, normalize, to_lua

BINDS = [
    {"modmask": 4, "key": "space", "description": "Direct input for the terminal prefix"},
    {"modmask": 5, "key": "space", "description": "Talk to Rum (hold) / hands-free (tap)"},
    {"modmask": 12, "key": "space", "description": "Superwhisper: toggle"},
]


def test_normalize_orders_modifiers_and_uppercases():
    assert normalize("shift+ctrl+space") == "CTRL + SHIFT + SPACE"
    assert normalize("  Super + h ") == "SUPER + H"
    assert normalize("") == ""


def test_conflicts_with_hyprland_and_apps_but_not_ourselves():
    assert conflicts("CTRL + SPACE", BINDS) == ["Direct input for the terminal prefix"]
    assert conflicts("CTRL + SHIFT + SPACE", BINDS) == ["IntelliJ: smart code completion"]
    assert conflicts("CTRL + ALT + V", BINDS) == []


def test_lua_has_push_to_talk_and_optional_settings_key():
    lua = to_lua(Config(), "/bin/omarum")
    assert 'o.bind_hold("CTRL + SHIFT + SPACE"' in lua
    assert '"/bin/omarum ptt_down"' in lua and '"/bin/omarum ptt_up"' in lua
    assert "settings" not in lua.split("\n", 1)[1]  # no settings key by default
    lua2 = to_lua(Config(settings_shortcut="ctrl+alt+o"), "/bin/omarum")
    assert 'o.bind("CTRL + ALT + O", "Omarum settings", "/bin/omarum settings")' in lua2


def test_disabled_talk_shortcut_writes_no_bind():
    assert "bind_hold" not in to_lua(Config(talk_shortcut=""), "/bin/omarum")
