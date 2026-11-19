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


def test_once_never_asks_glib_to_repeat():
    """GLib repeats an idle callback while it returns True; grab_focus() returns True, so
    idle_add(entry.grab_focus) re-selected the whole field forever (each key replaced the text)."""
    from omarum.settings_model import once

    calls = []
    cb = once(lambda: calls.append(1) or True)
    assert cb() is False and calls == [1]


def test_keys_while_editing_act_like_a_form():
    from omarum.settings_model import edit_key

    assert edit_key("Escape") == ("cancel", 0)
    assert edit_key("Down") == ("save", +1)
    assert edit_key("Up") == ("save", -1)
    assert edit_key("Tab") == ("save", +1)
    assert edit_key("ISO_Left_Tab") == ("save", -1)
    assert edit_key("a") is None and edit_key("Left") is None  # typing and moving the cursor stay in the field


def test_wait_before_answering_is_a_setting():
    from omarum.config import Config
    from omarum.settings_model import display, row, step

    r = row("vad_stop_secs")
    assert r.tab == "Companion" and r.kind == "slider" and r.label == "Wait before answering"
    assert Config().vad_stop_secs == 0.8  # a breath or "hmm" no longer ends your turn
    assert display(r, 0.8) == "0.8s"
    assert step(r, 0.8, +1) == 0.9 and step(r, 2.0, +1) == 2.0 and step(r, 0.3, -1) == 0.3


def test_elevenlabs_key_sits_right_under_the_voice_engine():
    from omarum.settings_model import rows_for

    voice = [r for r in rows_for("Engine") if r.group == "Voice"]
    assert [r.label for r in voice][:2] == ["Engine", "ElevenLabs API key"]
    key = voice[1]
    assert key.kind == "secret" and key.key == "ELEVENLABS_API_KEY"
    assert "Enter" in key.hint and "paste" in key.hint
