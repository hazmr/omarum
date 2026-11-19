from dataclasses import fields

from omarum.config import Config
from omarum.settings_model import FOOTERS, ROWS, TABS, display, row, rows_for, step

CONFIG_KEYS = {f.name for f in fields(Config)}


def test_every_key_row_is_a_config_field_or_secret():
    for r in ROWS:
        if r.key is None:
            continue
        assert r.key in CONFIG_KEYS or (r.kind == "secret" and r.key.isupper()), r


def test_cycle_wraps():
    r = row("orb_position")
    assert step(r, "bottom-center", +1) == "top-right"
    assert step(r, "top-right", -1) == "bottom-center"


def test_seg_clamps():
    r = row("orb_style")
    assert step(r, "ring", +1) == "ring"
    assert step(r, "glow", -1) == "glow"
    assert step(r, "glow", +1) == "lines"


def test_slider_steps_within_bounds():
    r = row("orb_size")
    assert step(r, 320, +1) == 320
    assert step(r, 160, -1) == 144
    assert step(r, 96, -1) == 96


def test_toggle_flips():
    assert step(row("record_audio"), True, +1) is False


def test_retention_display():
    r = row("retention_days")
    assert display(r, 0) == "Forever" and display(r, 30) == "30 days"
    assert step(r, 0, +1) == 7


def test_secret_display():
    r = row("ELEVENLABS_API_KEY")
    assert display(r, True) == "set ✓" and display(r, False) == "not set"


def test_tabs_in_order_and_have_footers():
    assert TABS == ("Companion", "Engine", "Memory", "Conversations")
    assert all(FOOTERS[t] for t in TABS)
    assert rows_for("Companion")[0].key == "companion_name"


def test_shortcut_rows_and_display():
    r = row("talk_shortcut")
    assert r.kind == "shortcut" and r.tab == "Companion"
    assert display(r, "CTRL + SHIFT + SPACE") == "Ctrl + Shift + Space"
    assert display(r, "") == "none"
    assert step(r, "CTRL + SHIFT + SPACE", +1) == "CTRL + SHIFT + SPACE"  # changed only by recording


def test_voice_volume_row():
    r = row("voice_volume")
    assert display(r, 150) == "150%" and step(r, 300, +1) == 300 and step(r, 150, +1) == 160


def test_tab_index_by_name():
    from omarum.settings_model import tab_index

    assert tab_index("conversations") == 3
    assert tab_index("Engine") == 1
    assert tab_index("") == 0
    assert tab_index("nope") == 0


def test_brain_rows_follow_the_provider():
    from omarum.settings_model import rows_for

    def brain_rows(brain):
        return [r for r in rows_for("Engine", brain=brain, brain_status=lambda p: "ready") if r.group == "Brain"]

    rows = brain_rows("claude-code")
    assert [r.label for r in rows] == ["Brain", "Model"]
    assert rows[0].key == "brain" and "codex" in rows[0].options and "ollama" in rows[0].options
    assert rows[1].kind == "model" and rows[1].options == ("haiku", "sonnet", "opus")

    rows = brain_rows("gemini")
    assert [r.label for r in rows] == ["Brain", "Model", "API key"]
    assert rows[2].key == "GEMINI_API_KEY" and rows[2].kind == "secret"

    rows = brain_rows("custom")
    assert [r.label for r in rows] == ["Brain", "Model", "Endpoint", "API key"]
    assert rows[2].key == "brain_url" and rows[2].kind == "text"

    assert [r.label for r in brain_rows("ollama")] == ["Brain", "Model"]


def test_brain_and_model_display_and_step():
    from omarum.settings_model import display, rows_for, step

    rows = {r.label: r for r in rows_for("Engine", brain="codex", brain_status=lambda p: "not installed")}
    assert display(rows["Brain"], "codex") == "Codex (subscription)"
    assert "not installed" in rows["Brain"].hint
    assert display(rows["Model"], "") == "default"
    assert step(rows["Model"], "", +1) == "gpt-5"
    assert step(rows["Model"], "my-own", +1) == ""  # unknown → back to the first suggestion
    assert step(rows["Brain"], "codex", +1) == "gemini-cli"
