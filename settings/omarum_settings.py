"""Omarum settings: a keyboard-first window in Omarchy's style (mockup settings-window-v2).

Runs on the system Python with GTK4. All logic lives in stdlib modules that are unit-tested:
omarum.settings_model (rows), omarum.configio (saving), omarum.library (memory, conversations).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from omarum import brains, library, settings_model as sm  # noqa: E402
from omarum.config import load_config  # noqa: E402
from omarum import elevenlabs  # noqa: E402
from omarum.configio import get_secret, has_secret, save_config, set_secret  # noqa: E402
from omarum.ipc import DaemonNotRunning, send_command  # noqa: E402
from omarum.models import MODELS_DIR  # noqa: E402
from omarum.shortcuts import conflicts, current_binds, normalize  # noqa: E402
from omarum.store import Store  # noqa: E402
from omarum.theme import ui_colors  # noqa: E402
from omarum.zonos3_tts import is_installed as zonos3_installed  # noqa: E402


def css(c: dict) -> str:
    return f"""
    window, .root {{ background: {c['background']}; color: {c['foreground']};
        font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", monospace; font-size: 14px; }}
    .header {{ border-bottom: 1px solid alpha({c['muted']}, 0.6); min-height: 50px; }}
    .brand {{ color: {c['accent']}; padding: 0 22px 0 18px; }}
    .tab {{ color: {c['light_foreground']}; padding: 0 18px; border-bottom: 2px solid transparent; opacity: 0.6; }}
    .tab.on {{ color: {c['foreground']}; border-bottom-color: {c['accent']}; opacity: 1; }}
    .group {{ color: alpha({c['light_foreground']}, 0.6); font-size: 13px; padding: 14px 0 6px 0; }}
    .row {{ padding: 7px 15px; border-left: 2px solid transparent; }}
    .row.focus {{ background: alpha({c['selection']}, 0.45); border-left-color: {c['accent']}; }}
    .row.focus .label {{ color: {c['accent']}; }}
    .value {{ color: {c['light_foreground']}; }}
    .row.focus .value {{ color: {c['accent']}; }}
    .arrow {{ color: alpha({c['light_foreground']}, 0.5); }}
    .seg {{ border: 1px solid {c['muted']}; padding: 2px 11px; color: alpha({c['light_foreground']}, 0.7); font-size: 13px; }}
    .seg.on {{ background: alpha({c['muted']}, 0.8); color: {c['foreground']}; border-color: {c['light_foreground']}; font-weight: bold; }}
    .hint {{ color: alpha({c['light_foreground']}, 0.45); font-size: 12px; }}
    .ok {{ color: #87a9b0; }} .bad {{ color: #c38b7b; }}
    .footer {{ border-top: 1px solid alpha({c['muted']}, 0.6); padding: 9px 16px; color: {c['light_foreground']}; font-size: 13px; }}
    entry {{ background: {c['background']}; color: {c['foreground']}; border: 1px solid {c['accent']}; border-radius: 0; min-height: 0; padding: 2px 6px; }}
    """


class Item:
    """One line in the list: a group header, a setting, or a memory/conversation entry."""

    def __init__(self, kind: str, label: str = "", row: sm.Row | None = None, data=None, hint: str = "") -> None:
        self.kind, self.label, self.row, self.data, self.hint = kind, label, row, data, hint

    @property
    def selectable(self) -> bool:
        return self.kind != "group"


class Settings(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Omarum")
        self.set_default_size(900, 780)
        self.store = Store()
        self.store.ensure()
        self.values = vars(load_config()).copy()
        self.tab = 0
        self.index = 0
        self.items: list[Item] = []
        self.editing: Gtk.Entry | None = None
        self.editing_row: sm.Row | None = None
        self.eleven_voices = elevenlabs.load_cache()
        self.eleven_status = ""  # "✓ works" or why ElevenLabs can't speak
        self.eleven_ok = False
        self.armed: str | None = None  # "forget:3" / "delete:<dir>" waiting for a second d
        self.player: subprocess.Popen | None = None
        self.message = ""
        self.capturing: sm.Row | None = None  # recording a new shortcut for this row

        provider = Gtk.CssProvider()
        provider.load_from_string(css(ui_colors()))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("root")
        self.header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.header.add_css_class("header")
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.list.set_margin_start(20)
        self.list.set_margin_end(20)
        self.list.set_margin_top(6)
        self.scroller = Gtk.ScrolledWindow(vexpand=True)
        self.scroller.set_child(self.list)
        self.footer = Gtk.Label(xalign=1)
        self.footer.add_css_class("footer")
        root.append(self.header)
        root.append(self.scroller)
        root.append(self.footer)
        self.set_child(root)

        keys = Gtk.EventControllerKey()
        # Capture: see keys before a text field does (Esc/↑/↓/Tab while editing); anything
        # the handler doesn't take still reaches the field.
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.connect("close-request", lambda *_: self.stop_playback() or False)
        self.render()
        self.check_elevenlabs()  # fresh voice list and a plain-words status each time settings opens

    # -- data -----------------------------------------------------------------
    def build_items(self) -> list[Item]:
        tab = sm.TABS[self.tab]
        items: list[Item] = []
        group = None
        for r in sm.rows_for(tab, brain=self.values.get("brain", "claude-code"), brain_status=self.brain_status,
                             eleven_voices=self.eleven_voices, eleven_status=self.eleven_status):
            if r.group != group:
                group = r.group
                items.append(Item("group", group))
            hint = r.hint
            if r.key == "voice_primary" and self.values.get("voice_primary") == "elevenlabs" \
                    and not has_secret("ELEVENLABS_API_KEY"):
                hint = "⚠ no ElevenLabs API key yet: add it on the next line (until then Rum uses ZONOS3)"
            items.append(Item("setting", r.label, r, hint=hint))
        if tab == "Engine":
            items.append(Item("group", "Status"))
            for label, ok, detail in self.status():
                items.append(Item("info", label, data=ok, hint=detail))
        elif tab == "Memory":
            name = self.values["companion_name"]
            items.append(Item("group", f"What {name} knows about you"))
            facts = library.facts(self.store)
            items += [Item("fact", f, data=i) for i, f in enumerate(facts)] or [Item("info", "Nothing yet", data=None)]
            items.append(Item("group", "Journal"))
            journals = library.journals(self.store)
            items += [Item("journal", f"{d:%a %d %b}", data=(d, text), hint=text[:70]) for d, text in journals] \
                or [Item("info", "No entries yet (written the day after you talk)", data=None)]
        elif tab == "Conversations":
            day = None
            for t in library.talks(self.store):
                if t.day != day:
                    day = t.day
                    items.append(Item("group", f"{t.day:%A %d %B}"))
                length = f"{t.seconds // 60}m {t.seconds % 60:02d}s" if t.seconds is not None else ""
                items.append(Item("talk", f"{t.time}  {length:>8}", data=t, hint=t.first_line))
            if day is None:
                items.append(Item("info", "No conversations yet", data=None))
        return items

    def brain_env(self) -> dict:
        keys = {p.env_key for p in brains.PROVIDERS.values() if p.env_key}
        return {**os.environ, **{k: "set" for k in keys if has_secret(k)}}

    def brain_status(self, p) -> str:
        return brains.status(p, self.brain_env(), shutil.which, self.values.get("brain_url", ""))

    def status(self) -> list[tuple[str, bool, str]]:
        whisper = sorted(p.name for p in (MODELS_DIR / "whisper").glob("*") if (p / "model.bin").exists()) \
            if (MODELS_DIR / "whisper").is_dir() else []
        return [
            ("Brain", brains.not_ready_reason(self.dataclass_cfg(), self.brain_env()) is None,
             brains.not_ready_reason(self.dataclass_cfg(), self.brain_env()) or brains.label(self.dataclass_cfg())),
            ("ZONOS3 voice", zonos3_installed(), "local voice server"),
            ("Kokoro voice", (MODELS_DIR / "kokoro" / "kokoro-v1.0.onnx").exists(), "always-there fallback"),
            ("Whisper models", bool(whisper), ", ".join(whisper) or "downloaded on first use"),
            ("ElevenLabs", self.eleven_ok, self.eleven_status or ("checking…" if has_secret("ELEVENLABS_API_KEY") else "optional cloud voice: add a key above")),
        ]

    def dataclass_cfg(self):
        from omarum.config import Config

        return Config(**self.values)

    def value_of(self, r: sm.Row):
        return has_secret(r.key) if r.kind == "secret" else self.values.get(r.key)

    # -- rendering ------------------------------------------------------------
    def render(self) -> None:
        self.items = self.build_items()
        selectable = [i for i, it in enumerate(self.items) if it.selectable]
        if selectable and self.index not in selectable:
            self.index = min(selectable, key=lambda i: abs(i - self.index))

        child = self.header.get_first_child()
        while child:
            self.header.remove(child)
            child = self.header.get_first_child()
        brand = Gtk.Label(label="◉ omarum")
        brand.add_css_class("brand")
        self.header.append(brand)
        for i, name in enumerate(sm.TABS):
            tab = Gtk.Label(label=name)
            tab.add_css_class("tab")
            if i == self.tab:
                tab.add_css_class("on")
            click = Gtk.GestureClick()
            click.connect("released", lambda *_a, i=i: self.switch_tab(i))
            tab.add_controller(click)
            self.header.append(tab)

        child = self.list.get_first_child()
        while child:
            self.list.remove(child)
            child = self.list.get_first_child()
        focus_widget = None
        for i, it in enumerate(self.items):
            w = self.render_item(it, focused=(i == self.index), index=i)
            if i == self.index:
                focus_widget = w
            if it.selectable:
                click = Gtk.GestureClick()
                click.connect("released", lambda *_a, i=i: self.click(i))
                w.add_controller(click)
            self.list.append(w)

        hints = sm.FOOTERS[sm.TABS[self.tab]]
        text = "   ·   ".join(hints)
        self.footer.set_text(self.message or text)
        if focus_widget is not None:
            GLib.idle_add(self.scroll_to, focus_widget)

    def scroll_to(self, widget) -> bool:
        adj = self.scroller.get_vadjustment()
        ok, rect = widget.compute_bounds(self.list)
        if ok:
            top, bottom = rect.get_y(), rect.get_y() + rect.get_height()
            if top < adj.get_value():
                adj.set_value(top - 20)
            elif bottom > adj.get_value() + adj.get_page_size():
                adj.set_value(bottom - adj.get_page_size() + 20)
        return False

    def render_item(self, it: Item, focused: bool, index: int = 0) -> Gtk.Widget:
        if it.kind == "group":
            g = Gtk.Label(label=it.label, xalign=0)
            g.add_css_class("group")
            return g
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("row")
        if focused:
            row.add_css_class("focus")
        label = Gtk.Label(label=it.label, xalign=0)
        label.add_css_class("label")
        if it.kind == "fact":  # long sentences wrap instead of running off the window
            label.set_wrap(True)
            label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_hexpand(True)
            label.set_max_width_chars(80)
        else:
            label.set_size_request(260, -1)
        row.append(label)
        if it.kind == "setting":
            row.append(self.render_value(it.row, focused, index))
        elif it.kind == "info" and it.data is not None:
            mark = Gtk.Label(label="● ok" if it.data else "○ missing")
            mark.add_css_class("ok" if it.data else "bad")
            row.append(mark)
        if it.hint:
            hint = Gtk.Label(label=it.hint, xalign=0)
            hint.add_css_class("hint")
            hint.set_ellipsize(Pango.EllipsizeMode.END)
            hint.set_hexpand(True)
            row.append(hint)
        return row

    def clickable(self, widget: Gtk.Widget, action) -> Gtk.Widget:
        """A click on this part of a row does `action` (and not the row's own click)."""
        g = Gtk.GestureClick()
        g.connect("pressed", lambda gesture, *_a: gesture.set_state(Gtk.EventSequenceState.CLAIMED))
        g.connect("released", lambda *_a: action())
        widget.add_controller(g)
        widget.set_cursor_from_name("pointer")
        return widget

    def pick(self, i: int, r: sm.Row, value) -> None:
        """Clicked one option of a row: select the row and set exactly that value."""
        if self.editing is not None:
            self.finish_edit(self.editing_row, self.editing.get_text())
        self.index = i
        if value != self.value_of(r):
            self.save(r.key, value)
        self.render()

    def nudge(self, i: int, direction: int) -> None:
        """Clicked ‹ or › on a row: select it and step its value back or forward."""
        if self.editing is not None:
            self.finish_edit(self.editing_row, self.editing.get_text())
        self.index = i
        self.change(direction)

    def arrows(self, i: int, middle: Gtk.Widget) -> Gtk.Box:
        box = Gtk.Box(spacing=8)
        for text, direction in (("‹", -1), (None, 0), ("›", +1)):
            if text is None:
                box.append(middle)
                continue
            lab = Gtk.Label(label=text)
            lab.add_css_class("arrow")
            box.append(self.clickable(lab, lambda d=direction: self.nudge(i, d)))
        return box

    def render_value(self, r: sm.Row, focused: bool, index: int = 0) -> Gtk.Widget:
        value = self.value_of(r)
        if focused and self.editing is not None:
            return self.editing
        if r.kind == "seg":
            box = Gtk.Box(spacing=6)
            for opt in r.options:
                s = Gtk.Label(label=str(opt))
                s.add_css_class("seg")
                if opt == value:
                    s.add_css_class("on")
                box.append(self.clickable(s, lambda o=opt: self.pick(index, r, o)))
            return box
        if r.kind == "slider":
            lo, hi, _inc, _unit = r.options
            filled = round((value - lo) / (hi - lo) * 20) if hi > lo else 0
            bar = "━" * filled + "●" + "─" * (20 - filled)
            v = Gtk.Label(label=f"{bar}  {sm.display(r, value)}")
            v.add_css_class("value")
            return self.arrows(index, v)
        if r.kind == "toggle":
            v = Gtk.Label(label=("[■■  on ]" if value else "[ off ■■]"))
            v.add_css_class("value")
            return v
        if r.kind in ("cycle", "model"):
            v = Gtk.Label(label=sm.display(r, value).center(18))
            v.add_css_class("value")
            return self.arrows(index, v)  # clicking the value itself: next value, or type a model
        if r.kind == "shortcut" and focused and self.capturing is r:
            v = Gtk.Label(label="press the new keys…")
            v.add_css_class("value")
            return v
        v = Gtk.Label(label=sm.display(r, value) if r.kind in ("secret", "text", "shortcut") else "")
        v.add_css_class("value")
        return v

    # -- actions ----------------------------------------------------------------
    def save(self, key: str, value) -> None:
        self.values[key] = value
        save_config({key: value})
        try:
            send_command("reload", timeout=1.0)
        except (DaemonNotRunning, OSError):
            pass  # applied next time the daemon starts

    def change(self, direction: int) -> None:
        it = self.items[self.index]
        if it.kind != "setting" or it.row.kind in ("text", "secret", "action", "shortcut"):
            return
        if it.row.key == "elevenlabs_voice_id" and not self.eleven_voices:
            self.flash("No voices yet: save a working ElevenLabs key first (it starts with sk_)")
            return
        new = sm.step(it.row, self.value_of(it.row), direction)
        if new != self.value_of(it.row):
            self.save(it.row.key, new)
            if it.row.key == "elevenlabs_voice_id":
                self.check_elevenlabs()
            if it.row.key == "brain":
                self.save("brain_model", "")  # the old model name belongs to the old brain
        self.render()

    def activate(self) -> None:
        it = self.items[self.index]
        if it.kind == "setting" and it.row.kind in ("text", "secret", "model"):
            self.start_edit(it.row)
        elif it.kind == "setting" and it.row.kind == "shortcut":
            self.capturing = it.row
            self.message = "Press the new shortcut   ·   Esc cancel   ·   Backspace remove"
            self.render()
        elif it.kind == "setting" and it.row.kind == "action":
            out = library.export(self.store, Path.home())
            self.flash(f"Exported to {out}")
        elif it.kind == "setting":
            self.change(+1)
        elif it.kind == "journal":
            self.show_text(f"Journal · {it.data[0]:%A %d %B %Y}", it.data[1])
        elif it.kind == "talk":
            self.play(it.data)

    def start_edit(self, r: sm.Row) -> None:
        entry = Gtk.Entry()
        entry.set_hexpand(True)
        if r.kind == "secret":
            entry.set_visibility(False)
            entry.set_placeholder_text("paste the key, Enter to save, empty to remove")
        else:
            entry.set_text(str(self.values.get(r.key, "")))
        entry.connect("activate", lambda e: self.finish_edit(r, e.get_text()))
        self.editing, self.editing_row = entry, r
        self.render()
        GLib.idle_add(sm.once(entry.grab_focus))

    def check_elevenlabs(self) -> None:
        """In the background: load this key's voices, keep a voice it can use, test it, say why not."""
        import threading

        key, voice, model = (get_secret("ELEVENLABS_API_KEY"), self.values.get("elevenlabs_voice_id", ""),
                             self.values.get("elevenlabs_model", "eleven_flash_v2_5"))
        if not key:
            self.eleven_ok, self.eleven_status = False, ""
            return
        self.eleven_status = "checking…"

        def work() -> None:
            voices, pick, note = self.eleven_voices, voice, ""
            try:
                voices, note = elevenlabs.voices_for(key)  # default voices if the key can't list its own
                elevenlabs.save_cache(voices)
                if voices and voice not in {v[0] for v in voices}:
                    pick = voices[0][0]  # a default voice the account can use
            except elevenlabs.ElevenLabsError as e:
                why = str(e)  # `e` is gone once the except block ends; the callback runs later
                GLib.idle_add(sm.once(lambda: self._eleven_done(voices, voice, False, why)))
                return
            why = elevenlabs.check(key, pick, model)
            status = why or ("✓ works · " + note if note else "✓ works")
            GLib.idle_add(sm.once(lambda: self._eleven_done(voices, pick, why is None, status)))

        threading.Thread(target=work, daemon=True).start()

    def _eleven_done(self, voices, voice, ok: bool, status: str) -> None:
        self.eleven_voices, self.eleven_ok, self.eleven_status = voices, ok, status
        if voice and voice != self.values.get("elevenlabs_voice_id"):
            self.save("elevenlabs_voice_id", voice)
        self.render()

    def finish_edit(self, r: sm.Row, text: str) -> None:
        self.editing = None
        if r.kind == "secret":
            set_secret(r.key, text.strip())
            self.flash("Key saved" if text.strip() else "Key removed")
            if r.key == "ELEVENLABS_API_KEY":
                self.check_elevenlabs()
        elif text.strip() or r.kind == "model":  # an empty model means "the provider's default"
            self.save(r.key, text.strip())
        self.render()

    MODIFIER_KEYS = {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
                     "Meta_L", "Meta_R", "ISO_Level3_Shift", "Hyper_L", "Hyper_R"}

    def capture(self, keyval, state) -> None:
        name = Gdk.keyval_name(keyval) or ""
        if name in self.MODIFIER_KEYS:
            return  # wait for the real key
        r, self.capturing = self.capturing, None
        if keyval == Gdk.KEY_Escape and not state & Gdk.ModifierType.MODIFIER_MASK:
            self.message = ""
            self.render()
            return
        if keyval == Gdk.KEY_BackSpace and not state & Gdk.ModifierType.MODIFIER_MASK:
            combo = ""
        else:
            mods = [m for m, mask in (("SUPER", Gdk.ModifierType.SUPER_MASK), ("CTRL", Gdk.ModifierType.CONTROL_MASK),
                                      ("ALT", Gdk.ModifierType.ALT_MASK), ("SHIFT", Gdk.ModifierType.SHIFT_MASK))
                    if state & mask]
            key = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or name
            combo = normalize("+".join(mods + [key]))
        self.values[r.key] = combo
        save_config({r.key: combo})  # the plugin sees the change and binds the new keys itself
        clash = conflicts(combo, current_binds())
        self.message = ""
        self.flash(f"Saved. Also used by: {', '.join(clash)}" if clash else ("Saved" if combo else "Shortcut removed"))

    def play(self, talk) -> None:
        self.stop_playback()
        cmd = library.play_command(talk)
        if not cmd or shutil.which(cmd[0]) is None:
            self.flash("No audio for this conversation")
            return
        self.player = subprocess.Popen(cmd)
        self.flash("Playing… Space to stop")

    def stop_playback(self) -> None:
        if self.player and self.player.poll() is None:
            self.player.terminate()
        self.player = None

    def press_d(self) -> None:
        it = self.items[self.index]
        if it.kind == "fact":
            token = f"forget:{it.data}"
            if self.armed == token:
                library.forget(self.store, it.data)
                self.armed = None
                self.flash("Forgotten (a backup is in profile.md.bak)")
            else:
                self.armed = token
                self.flash("Press d again to forget this")
        elif it.kind == "talk":
            token = f"delete:{it.data.dir}"
            if self.armed == token:
                self.stop_playback()
                library.delete_talk(self.store, it.data)
                self.armed = None
                self.flash("Conversation deleted")
            else:
                self.armed = token
                self.flash("Press d again to delete this conversation")

    def show_text(self, title: str, text: str) -> None:
        dialog = Gtk.Window(transient_for=self, modal=True, title=title)
        dialog.set_default_size(620, 360)
        label = Gtk.Label(label=text, wrap=True, xalign=0, yalign=0, selectable=True)
        label.set_margin_start(20)
        label.set_margin_end(20)
        label.set_margin_top(16)
        dialog.set_child(label)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, k, *_: (dialog.close(), True)[1] if k in (Gdk.KEY_Escape, Gdk.KEY_q, Gdk.KEY_Return) else False)
        dialog.add_controller(keys)
        dialog.present()

    def flash(self, text: str) -> None:
        self.message = text
        self.render()
        GLib.timeout_add(2500, self.clear_flash, text)

    def clear_flash(self, text: str) -> bool:
        if self.message == text:
            self.message = ""
            self.render()
        return False

    # -- navigation -------------------------------------------------------------
    def move(self, direction: int) -> None:
        selectable = [i for i, it in enumerate(self.items) if it.selectable]
        if not selectable:
            return
        pos = selectable.index(self.index) if self.index in selectable else 0
        self.index = selectable[max(0, min(len(selectable) - 1, pos + direction))]
        self.armed = None
        self.render()

    def switch_tab(self, i: int) -> None:
        self.tab = i % len(sm.TABS)
        self.index = 0
        self.armed = None
        self.editing = None
        self.render()

    def click(self, i: int) -> None:
        if self.editing is not None:  # clicking elsewhere saves what was typed
            if i == self.index:
                return  # a click inside the open field (placing the cursor)
            self.finish_edit(self.editing_row, self.editing.get_text())
        self.index = i
        self.render()
        self.activate()

    def on_key(self, _ctrl, keyval, _code, state) -> bool:
        if self.capturing is not None:
            self.capture(keyval, state)
            return True
        if self.editing is not None:
            what = sm.edit_key(Gdk.keyval_name(keyval) or "")
            if what is None:
                return False  # typing and cursor keys stay in the field
            action, move = what
            if action == "cancel":
                self.editing = None
                self.render()
            else:  # save, then go to the next/previous row like a form
                self.finish_edit(self.editing_row, self.editing.get_text())
                self.move(move)
            return True
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        k = keyval
        if k in (Gdk.KEY_q, Gdk.KEY_Escape):
            self.stop_playback()
            self.close()
        elif k in (Gdk.KEY_Down, Gdk.KEY_j):
            self.move(+1)
        elif k in (Gdk.KEY_Up, Gdk.KEY_k):
            self.move(-1)
        elif k in (Gdk.KEY_Right, Gdk.KEY_l):
            self.change(+1)
        elif k in (Gdk.KEY_Left, Gdk.KEY_h):
            self.change(-1)
        elif k == Gdk.KEY_space:
            if sm.TABS[self.tab] == "Conversations":
                self.stop_playback()
                self.flash("Stopped")
            else:
                self.change(+1)
        elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.activate()
        elif k in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            self.switch_tab(self.tab + (-1 if shift or k == Gdk.KEY_ISO_Left_Tab else 1))
        elif Gdk.KEY_1 <= k <= Gdk.KEY_4:
            self.switch_tab(k - Gdk.KEY_1)
        elif k == Gdk.KEY_d:
            self.press_d()
        else:
            return False
        return True


def main() -> None:
    app = Gtk.Application(application_id="org.omarchy.omarum.settings")
    start_tab = sm.tab_index(sys.argv[1]) if len(sys.argv) > 1 else 0

    def activate(a: Gtk.Application) -> None:
        win = a.get_active_window() or Settings(a)
        if start_tab:
            win.switch_tab(start_tab)
        win.present()

    app.connect("activate", activate)
    app.run([])


if __name__ == "__main__":
    main()
