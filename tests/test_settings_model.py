from dataclasses import fields

from omarum import settings_model as sm
from omarum.config import Config
from omarum.settings_model import FOOTERS, ROWS, TABS, display, row, rows_for, step

CONFIG_KEYS = {f.name for f in fields(Config)}
CODEX = {"brain": "codex", "voice_primary": "zonos3"}


def labels(values, **kw):
    return [r.label for r in rows_for("Settings", values, **kw)]


def test_every_key_row_is_a_config_field_or_secret():
    for r in ROWS:
        if r.key is None or r.kind == "voice":
            continue
        assert r.key in CONFIG_KEYS or (r.kind == "secret" and r.key.isupper()), r


def test_tabs_and_footers():
    assert TABS == ("Settings", "Models", "Memory", "Conversations")
    assert all(FOOTERS[t] for t in TABS)
    assert FOOTERS["Settings"] == ["↑/↓ Select", "←/→ or Space Change", "Enter Edit", "Q Close"]
    assert rows_for("Settings", CODEX)[0].key == "companion_name"


def test_old_tab_names_open_settings():
    assert sm.tab_index("companion") == 0 and sm.tab_index("engine") == 0
    assert sm.tab_index("models") == 1 and sm.tab_index("conversations") == 3
    assert sm.tab_index("") == 0 and sm.tab_index("nope") == 0


def test_settings_tab_has_13_rows_for_codex_with_zonos3_voice():
    got = labels(CODEX)
    assert got == ["Name", "Your name", "Brain", "Model", "Voice", "Volume", "Processing",
                   "Response speed", "Talk key", "Style", "Position", "Look when I ask", "See my code"]
    groups = []
    for r in rows_for("Settings", CODEX):
        if r.group not in groups:
            groups.append(r.group)
    assert groups == ["General", "Voice", "Speech to text", "Talking", "Orb", "Screen"]


def test_conditional_rows():
    assert "ElevenLabs key" in labels({"brain": "codex", "voice_primary": "elevenlabs"})
    assert "ElevenLabs key" not in labels({"brain": "codex", "voice_primary": "kokoro"})
    assert "API key" in labels({"brain": "anthropic", "voice_primary": "kokoro"})
    assert "API key" not in labels({"brain": "codex", "voice_primary": "kokoro"})
    assert "Model" not in labels({"brain": "kimi", "voice_primary": "kokoro"})  # no model choices
    assert labels({"brain": "custom", "voice_primary": "kokoro"})[2:6] == ["Brain", "Endpoint", "API key", "Voice"]


def test_removed_rows_are_gone():
    keys = {r.key for t in TABS for r in rows_for(t, {"brain": "codex", "voice_primary": "kokoro"})}
    assert keys.isdisjoint({"orb_colors", "orb_size", "vad_stop_secs", "idle_timeout_secs",
                            "interrupt_min_words", "mute_while_speaking", "record_audio"})
    assert [r.label for r in rows_for("Memory", CODEX)] == ["Keep conversations"]
    assert rows_for("Models", CODEX) == [] and rows_for("Conversations", CODEX) == []


def test_every_settings_row_has_a_footer_hint_or_is_obvious():
    for r in rows_for("Settings", {"brain": "anthropic", "voice_primary": "elevenlabs"}):
        if r.label in ("Processing", "Response speed", "Talk key", "Look when I ask", "See my code"):
            assert r.hint, r.label


def test_voice_merge_and_updates():
    opts = sm.voice_options(zonos3=False, eleven_voices=[("abc", "Jessica", "premade")])
    assert opts[0] == ("elevenlabs:abc", "ElevenLabs · Jessica")
    assert not any(v.startswith("zonos3:") for v, _ in opts)
    assert ("kokoro:af_bella", "Kokoro · Bella") in opts and opts[-1] == ("piper:amy", "Piper · Amy")
    with_z = sm.voice_options(zonos3=True, eleven_voices=[])
    assert ("zonos3:Savannah", "ZONOS3 · Savannah") in with_z
    assert any(v.startswith("elevenlabs:") for v, _ in with_z)  # default voices, so the key row can appear
    assert sm.voice_updates("kokoro:af_bella") == {"voice_primary": "kokoro", "kokoro_voice": "af_bella"}
    assert sm.voice_updates("elevenlabs:abc") == {"voice_primary": "elevenlabs", "elevenlabs_voice_id": "abc"}
    assert sm.voice_updates("zonos3:Willow") == {"voice_primary": "zonos3", "zonos3_voice": "Willow"}
    assert sm.voice_updates("piper:amy") == {"voice_primary": "piper"}
    assert sm.voice_value({"voice_primary": "kokoro", "kokoro_voice": "af_bella"}) == "kokoro:af_bella"
    assert sm.voice_value({"voice_primary": "piper"}) == "piper:amy"


def test_voice_row_steps_through_the_merged_list():
    r = next(r for r in rows_for("Settings", CODEX, zonos3=True) if r.label == "Voice")
    assert r.kind == "voice" and r.options[0].startswith("elevenlabs:")
    assert display(r, "kokoro:af_bella") == "Kokoro · Bella"
    i = r.options.index("kokoro:af_heart")
    assert step(r, "kokoro:af_heart", +1) == r.options[i + 1]


def test_processing_labels_and_display_capitalized():
    rows = {r.label: r for r in rows_for("Settings", CODEX)}
    p = rows["Processing"]
    assert p.key == "whisper_device" and p.options == ("cpu", "auto")
    assert display(p, "auto") == "Accurate" and display(p, "cpu") == "Fast"
    assert display(rows["Position"], "top-right") == "Top right"
    assert display(rows["Style"], "glow") == "Glow" and display(rows["Response speed"], "fast") == "Fast"


def test_cycle_wraps():
    r = row("orb_position")
    assert step(r, "bottom-center", +1) == "top-right"
    assert step(r, "top-right", -1) == "bottom-center"


def test_seg_clamps():
    r = row("orb_style")
    assert step(r, "ring", +1) == "ring" and step(r, "glow", -1) == "glow" and step(r, "glow", +1) == "lines"


def test_volume_slider_steps_within_bounds():
    r = row("voice_volume")
    assert r.label == "Volume"
    assert display(r, 150) == "150%" and step(r, 300, +1) == 300 and step(r, 150, +1) == 160


def test_toggle_flips():
    assert step(row("screen_look"), True, +1) is False


def test_retention_display():
    r = row("retention_days")
    assert display(r, 0) == "Forever" and display(r, 30) == "30 days" and step(r, 0, +1) == 7


def test_secret_display():
    r = row("ELEVENLABS_API_KEY")
    assert r.label == "ElevenLabs key"
    assert display(r, True) == "set ✓" and display(r, False) == "not set"


def test_shortcut_rows_and_display():
    r = row("talk_shortcut")
    assert r.kind == "shortcut" and r.tab == "Settings"
    assert display(r, "CTRL + SHIFT + SPACE") == "Ctrl + Shift + Space"
    assert display(r, "") == "none"
    assert step(r, "CTRL + SHIFT + SPACE", +1) == "CTRL + SHIFT + SPACE"


def test_brain_rows_follow_the_provider():
    def brain(b):
        return [r for r in rows_for("Settings", {"brain": b, "voice_primary": "kokoro"}, brain_status=lambda p: "ready")
                if r.key in ("brain", "brain_model", "brain_url") or (r.kind == "secret" and r.key != "ELEVENLABS_API_KEY")]

    rows = brain("claude-code")
    assert [r.label for r in rows] == ["Brain", "Model"]
    assert "codex" in rows[0].options and rows[1].options == ("haiku", "sonnet", "opus")
    rows = brain("gemini")
    assert [r.label for r in rows] == ["Brain", "Model", "API key"] and rows[2].key == "GEMINI_API_KEY"


def test_brain_and_model_display_and_step():
    rows = {r.label: r for r in rows_for("Settings", CODEX, brain_status=lambda p: "not installed")}
    assert display(rows["Brain"], "codex") == "Codex (subscription)"
    assert "not installed" in rows["Brain"].hint
    assert display(rows["Model"], "") == "default"
    assert step(rows["Model"], "", +1) == "gpt-5"
    assert step(rows["Brain"], "codex", +1) == "gemini-cli"


def test_once_never_asks_glib_to_repeat():
    calls = []
    cb = sm.once(lambda: calls.append(1) or True)
    assert cb() is False and calls == [1]


def test_keys_while_editing_act_like_a_form():
    assert sm.edit_key("Escape") == ("cancel", 0)
    assert sm.edit_key("Down") == ("save", +1) and sm.edit_key("Up") == ("save", -1)
    assert sm.edit_key("Tab") == ("save", +1) and sm.edit_key("ISO_Left_Tab") == ("save", -1)
    assert sm.edit_key("a") is None and sm.edit_key("Left") is None


def test_response_speed_presets():
    r = row("response_speed")
    assert r.kind == "seg" and r.options == ("fast", "balanced", "patient") and r.tab == "Settings"
    assert sm.SPEED_PRESETS["fast"] == {"vad_stop_secs": 0.3, "whisper_cpu_model": "tiny.en"}
    assert sm.SPEED_PRESETS["balanced"] == {"vad_stop_secs": 0.5, "whisper_cpu_model": "base.en"}
    assert Config().response_speed == "balanced" and Config().vad_stop_secs == 0.5
    assert sm.speed_of({"vad_stop_secs": 0.7, "whisper_cpu_model": "base.en"}) == "custom"


def test_human_size():
    assert sm.human_size(1_620_000_000) == "1.6 GB" and sm.human_size(464_000_000) == "464 MB"
    assert sm.human_size(63_000_000) == "63 MB" and sm.human_size(0) == "—"


def test_model_status_text_matches_the_spec():
    base = {"done": 680_000_000, "total": 1_620_000_000, "error": "", "in_use": False}
    assert sm.model_status({**base, "state": "missing"}) == "↓ Download"
    assert sm.model_status({**base, "state": "downloading"}) == "↓ 42%  680 MB of 1.6 GB"
    assert sm.model_status({**base, "state": "partial"}) == "Paused  680 MB of 1.6 GB"
    assert sm.model_status({**base, "state": "ready"}) == "✓ Ready"
    assert sm.model_status({**base, "state": "ready", "in_use": True}) == "✓ Ready  (in use)"
    assert sm.model_status({**base, "state": "failed", "error": "timed out"}) == "✗ Failed: timed out  Enter to retry"


def test_old_values_show_as_the_nearest_button():
    """config.toml from before the redesign: whisper_device="cuda", response_speed="custom" (0.6 s)."""
    rows = {r.label: r for r in rows_for("Settings", CODEX)}
    assert sm.shown_value(rows["Processing"], {"whisper_device": "cuda"}) == "auto"
    assert sm.shown_value(rows["Processing"], {"whisper_device": "cpu"}) == "cpu"
    old = {"response_speed": "custom", "vad_stop_secs": 0.6}
    assert sm.shown_value(rows["Response speed"], old) == "balanced"
    assert sm.shown_value(rows["Response speed"], {"response_speed": "custom", "vad_stop_secs": 1.5}) == "patient"
    assert sm.shown_value(rows["Style"], {"orb_style": "ring"}) == "ring"


def test_download_runs_the_code_next_to_the_window():
    """The engine venv may hold an older omarum (before the plugin updates); the download child
    must run the same code as the window, so PYTHONPATH points at the window's own checkout."""
    argv, env = sm.download_command("/venv/bin/python", "/plugins/omarum.panel", "gpu", {"PATH": "/usr/bin"})
    assert argv == ["/venv/bin/python", "-m", "omarum.cli", "models", "download", "gpu"]
    assert env["PYTHONPATH"] == "/plugins/omarum.panel" and env["PATH"] == "/usr/bin"
