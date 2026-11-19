from omarum.shortcuts import conflicts, normalize

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
