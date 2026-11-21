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
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from omarum import brains, catalog, library, modelcmd, settings_model as sm  # noqa: E402
from omarum.config import load_config  # noqa: E402
from omarum import elevenlabs  # noqa: E402
from omarum.configio import get_secret, has_secret, save_config, set_secret  # noqa: E402
from omarum.ipc import DaemonNotRunning, send_command  # noqa: E402
from omarum.models import MODELS_DIR  # noqa: E402
from omarum.paths import DATA_DIR  # noqa: E402
from omarum.shortcuts import conflicts, current_binds, normalize  # noqa: E402
from omarum.store import Store  # noqa: E402
from omarum.theme import ui_colors  # noqa: E402
from omarum.zonos3_tts import is_installed as zonos3_installed  # noqa: E402


def css(c: dict) -> str:
    # Sizes measured from Superwhisper's settings window: 12px text, 28px rows, the value column
    # ~180px in, small bold section titles, compact capitalized buttons, hints only in the footer.
    return f"""
    window, .root {{ background: {c['background']}; color: {c['foreground']};
        font-family: "JetBrainsMono Nerd Font", "JetBrains Mono", monospace; font-size: 12px; }}
    .header {{ border-bottom: 1px solid alpha({c['muted']}, 0.6); min-height: 44px; }}
    .brand {{ color: {c['accent']}; padding: 0 20px 0 16px; }}
    .tab {{ color: {c['light_foreground']}; padding: 0 14px; border-bottom: 2px solid transparent; opacity: 0.6; }}
    .tab.on {{ color: {c['foreground']}; border-bottom-color: {c['accent']}; opacity: 1; }}
    .group {{ color: {c['foreground']}; font-weight: bold; font-size: 11px; padding: 22px 0 8px 0; }}
    .row {{ min-height: 28px; padding: 2px 15px; margin-bottom: 2px; }}
    .row.focus {{ background: alpha({c['selection']}, 0.45); }}
    .row.focus .label {{ color: {c['accent']}; }}
    .value {{ color: {c['light_foreground']}; }}
    .row.focus .value {{ color: {c['foreground']}; }}
    .arrow {{ color: alpha({c['light_foreground']}, 0.5); }}
    .seg {{ border: 1px solid {c['muted']}; padding: 1px 9px; color: alpha({c['light_foreground']}, 0.75); font-size: 11px; }}
    .seg.on {{ background: alpha({c['muted']}, 0.8); color: {c['foreground']}; border-color: {c['light_foreground']}; font-weight: bold; }}
    .hint {{ color: alpha({c['light_foreground']}, 0.5); font-size: 11px; }}
    .size {{ color: alpha({c['light_foreground']}, 0.6); }}
    .keyhelp {{ padding: 4px 15px 10px 195px; }}
    .ok {{ color: #87a9b0; }} .bad {{ color: #c38b7b; }}
    .footer {{ border-top: 1px solid alpha({c['muted']}, 0.6); padding: 8px 16px; color: {c['light_foreground']}; font-size: 11px; }}
    entry {{ background: {c['background']}; color: {c['foreground']}; border: 1px solid {c['accent']}; border-radius: 0; min-height: 0; padding: 1px 6px; }}
    """


def rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def venv_python() -> str:
    """Rum's engine Python (has the download code's dependencies and is what setup uses)."""
    for p in (DATA_DIR / "venv" / "bin" / "python", Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"):
        if p.exists():
            return str(p)
    return sys.executable


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
        self.colors = ui_colors()
        self.downloads: dict[str, Gio.Subprocess] = {}  # model id → running `omarum models download`
        self.live: dict[str, dict] = {}  # model id → its latest progress line
        self.pending_voice: str | None = None  # a voice whose model isn't downloaded yet
        self.zonos3 = zonos3_installed()

        provider = Gtk.CssProvider()
        provider.load_from_string(css(self.colors))
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.add_css_class("root")
        self.header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.header.add_css_class("header")
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.list.set_margin_start(20)
        self.list.set_margin_end(20)
        self.list.set_margin_top(4)
        self.list.set_margin_bottom(20)
        self.scroller = Gtk.ScrolledWindow(vexpand=True)
        self.scroller.set_child(self.list)
        self.footer = Gtk.Box(spacing=16)
        self.footer.add_css_class("footer")
        self.footer_hint = Gtk.Label(xalign=0, hexpand=True)
        self.footer_hint.add_css_class("hint")
        self.footer_hint.set_ellipsize(Pango.EllipsizeMode.END)
        self.footer_keys = Gtk.Label(xalign=1)
        self.footer.append(self.footer_hint)
        self.footer.append(self.footer_keys)
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
        GLib.timeout_add(1000, self.tick)  # downloads started elsewhere show up within a second

    # -- data -----------------------------------------------------------------
    def build_items(self) -> list[Item]:
        tab = sm.TABS[self.tab]
        items: list[Item] = []
        group = None
        for r in sm.rows_for(tab, self.values, brain_status=self.brain_status,
                             eleven_voices=self.eleven_voices, zonos3=self.zonos3):
            if r.group != group:
                group = r.group
                items.append(Item("group", group))
            hint = r.hint
            if r.key == "ELEVENLABS_API_KEY":
                hint = self.eleven_status or ("no key yet: until then Rum uses the next voice · " + r.hint
                                              if not has_secret(r.key) else r.hint)
            items.append(Item("setting", r.label, r, hint=hint))
        if tab == "Models":
            for g in ("Speech to text", "Voices"):
                items.append(Item("group", g))
                items += [Item("model", s["title"], data=s) for s in self.model_states() if s["group"] == g]
            items.append(Item("zonos3", "ZONOS3", data=self.zonos3,
                              hint="Installed" if self.zonos3 else "Not installed: build it, see README"))
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

    def model_states(self) -> list[dict]:
        """Every model with its state (live progress from our own downloads wins)."""
        used = modelcmd.in_use(self.dataclass_cfg())
        out = []
        for m in catalog.CATALOG:
            st = {**catalog.state(m, MODELS_DIR), "size": m.approx_bytes, "in_use": m.id in used,
                  "removable": m.removable}
            live = self.live.get(m.id)
            if live and m.id in self.downloads:
                st.update(state="downloading", done=live.get("done", 0), total=live.get("total") or st["total"])
            out.append(st)
        return out

    def model_state(self, model_id: str) -> dict:
        return next(s for s in self.model_states() if s["id"] == model_id)

    def dataclass_cfg(self):
        from omarum.config import Config

        return Config(**self.values)

    def value_of(self, r: sm.Row):
        if r.kind == "voice":
            return self.pending_voice or sm.voice_value(self.values)
        if r.kind == "secret":
            return has_secret(r.key)
        return sm.shown_value(r, self.values)

    @staticmethod
    def voice_model(choice: str) -> str | None:
        """The model a voice needs downloaded (Kokoro, Piper), or None (cloud / built separately)."""
        return modelcmd.VOICE_MODELS.get(choice.partition(":")[0])

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
                if it.kind == "setting" and it.row.kind == "secret" and sm.key_help(it.row.key):
                    help_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                    help_box.add_css_class("keyhelp")
                    for line in sm.key_help(it.row.key):
                        lab = Gtk.Label(label=line, xalign=0, wrap=True)
                        lab.add_css_class("hint")
                        help_box.append(lab)
            if it.selectable:
                click = Gtk.GestureClick()
                click.connect("released", lambda *_a, i=i: self.click(i))
                w.add_controller(click)
            self.list.append(w)
            if i == self.index and it.kind == "setting" and it.row.kind == "secret" and sm.key_help(it.row.key):
                self.list.append(help_box)  # how to get this key, right under it

        self.footer_keys.set_text("  ·  ".join(sm.FOOTERS[sm.TABS[self.tab]]))
        current = self.items[self.index] if 0 <= self.index < len(self.items) else None
        hint = current.hint if current is not None and current.kind in ("setting", "zonos3") else ""
        if current is not None and current.kind == "model" and current.data.get("in_use") and not self.message:
            hint = "in use: Rum needs it with your current settings"
        self.footer_hint.set_text(self.message or hint)
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
            label.set_size_request(165, -1)
        row.append(label)
        if it.kind == "setting":
            row.append(self.render_value(it.row, focused, index))
            return row  # its hint shows in the footer while selected
        if it.kind == "model":
            size = Gtk.Label(label=sm.human_size(it.data["size"]), xalign=1)
            size.add_css_class("size")
            size.set_size_request(70, -1)
            state = Gtk.Label(label=sm.model_status(it.data), xalign=0)
            state.add_css_class("value")
            if it.data["state"] == "failed":
                state.add_css_class("bad")
            row.append(size)
            row.append(state)
            return row
        if it.kind == "zonos3":
            v = Gtk.Label(label=it.hint, xalign=0)
            v.add_css_class("value")
            row.append(v)
            return row
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
                s = Gtk.Label(label=sm.display(r, opt))
                s.add_css_class("seg")
                if opt == value:
                    s.add_css_class("on")
                box.append(self.clickable(s, lambda o=opt: self.pick(index, r, o)))
            if r.key == "whisper_device":
                note = self.processing_note()
                if note:
                    n = Gtk.Label(label=note)
                    n.add_css_class("hint")
                    box.append(n)
            return box
        if r.kind == "slider":
            lo, hi, _inc, _unit = r.options
            frac = (value - lo) / (hi - lo) if hi > lo else 0
            box = Gtk.Box(spacing=10)
            box.append(self.drawing(180, 14, lambda cr, w, h: self.draw_slider(cr, w, h, frac)))
            v = Gtk.Label(label=sm.display(r, value))
            v.add_css_class("value")
            box.append(v)
            return box
        if r.kind == "toggle":
            return self.clickable(self.drawing(26, 14, lambda cr, w, h: self.draw_switch(cr, w, h, bool(value))),
                                  lambda: self.pick(index, r, not value))
        if r.kind == "voice":
            v = Gtk.Label(label=sm.display(r, value).center(24))
            v.add_css_class("value")
            box = self.arrows(index, v)
            note = self.voice_note(value)
            if note:
                n = Gtk.Label(label=note)
                n.add_css_class("hint")
                box.append(n)
            return box
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

    def drawing(self, w: int, h: int, draw) -> Gtk.DrawingArea:
        area = Gtk.DrawingArea(content_width=w, content_height=h, valign=Gtk.Align.CENTER)
        area.set_draw_func(lambda _a, cr, width, height: draw(cr, width, height))
        return area

    def draw_switch(self, cr, w: int, h: int, on: bool) -> None:
        """A small switch like Superwhisper's: an outlined box with a square knob."""
        line = rgb(self.colors["light_foreground"])
        cr.set_source_rgba(*line, 0.7)
        cr.set_line_width(1)
        cr.rectangle(0.5, 0.5, w - 1, h - 1)
        cr.stroke()
        knob = h - 6
        cr.set_source_rgb(*(rgb(self.colors["foreground"]) if on else line))
        cr.rectangle(w - 3 - knob if on else 3, 3, knob, knob)
        cr.fill()

    def draw_slider(self, cr, w: int, h: int, frac: float) -> None:
        """A thin track with a tick at the value."""
        cr.set_source_rgba(*rgb(self.colors["light_foreground"]), 0.45)
        cr.rectangle(0, h / 2 - 0.5, w, 1)
        cr.fill()
        x = max(1, min(w - 2, frac * w))
        cr.set_source_rgb(*rgb(self.colors["foreground"]))
        cr.rectangle(x - 1, h / 2 - 5, 2, 10)
        cr.fill()

    def progress(self, model_id: str) -> str:
        st = self.model_state(model_id)
        if st["state"] == "downloading":
            return f"↓ {round(st['done'] * 100 / st['total']) if st['total'] else 0}%"
        return ""

    def voice_note(self, choice: str) -> str:
        model_id = self.voice_model(choice)
        if not model_id:
            return ""
        st = self.model_state(model_id)
        if st["state"] == "ready":
            return ""
        return self.progress(model_id) or f"({sm.human_size(st['size'])} · Enter to download)"

    def processing_note(self) -> str:
        if self.values.get("whisper_device") not in ("auto", "cuda"):
            return ""
        if not shutil.which("nvidia-smi"):
            return "no NVIDIA GPU: Rum uses Fast"
        missing = [i for i in ("gpu", "whisper-large-turbo") if self.model_state(i)["state"] != "ready"]
        if not missing:
            return ""
        running = [self.progress(i) for i in missing if self.progress(i)]
        if running:
            return "downloading " + running[0].lstrip("↓ ") + " · Rum uses Fast until it's ready"
        size = sum(self.model_state(i)["size"] for i in missing)
        return f"needs {sm.human_size(size)} · Enter to download"

    def start_download(self, model_id: str, then=None) -> None:
        """Run `omarum models download <id>` in the background; redraw on each progress line."""
        if model_id in self.downloads:
            return
        argv, env = sm.download_command(venv_python(), str(Path(__file__).resolve().parent.parent),
                                        model_id, dict(os.environ))
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE)
        launcher.set_environ([f"{k}={v}" for k, v in env.items()])
        proc = launcher.spawnv(argv)
        self.downloads[model_id] = proc
        self.live[model_id] = {"done": 0, "total": catalog.by_id(model_id).approx_bytes}
        stream = Gio.DataInputStream.new(proc.get_stdout_pipe())

        def on_line(src, res) -> None:
            try:
                line, _len = src.read_line_finish_utf8(res)
            except GLib.Error:
                line = None
            if line is None:
                return
            try:
                import json

                self.live[model_id] = json.loads(line)
            except ValueError:
                pass
            if self.editing is None:
                self.render()
            src.read_line_async(GLib.PRIORITY_DEFAULT, None, on_line)

        def on_exit(p, res) -> None:
            try:
                p.wait_finish(res)
            except GLib.Error:
                pass
            ok = p.get_exit_status() == 0
            self.downloads.pop(model_id, None)
            self.live.pop(model_id, None)
            title = catalog.by_id(model_id).title
            if ok and then:
                then()
            self.flash(f"{title} is ready" if ok else (f"{title}: paused" if p.get_exit_status() == 2
                                                       else f"{title}: download failed (Models tab says why)"))

        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, on_line)
        proc.wait_async(None, on_exit)
        self.render()

    def model_action(self, st: dict) -> None:
        """Enter on a Models row: download (or resume / retry), or cancel a running download."""
        if st["state"] == "downloading":
            modelcmd.main(["cancel", st["id"]], models_dir=MODELS_DIR, cfg=self.dataclass_cfg())
            self.flash(f"Pausing {st['title']}… Enter again resumes")
        elif st["state"] != "ready":
            self.start_download(st["id"])
        else:
            self.flash(f"{st['title']} is ready · D twice removes it")

    def remove_model(self, st: dict) -> None:
        import contextlib
        import io

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = modelcmd.main(["remove", st["id"]], models_dir=MODELS_DIR, cfg=self.dataclass_cfg())
        self.flash(f"Removed {st['title']}" if code == 0 else err.getvalue().strip())

    def tick(self) -> bool:
        """Every second: redraw the Models tab while anything downloads, even started elsewhere."""
        if self.editing is None and self.capturing is None and (
                self.downloads or (sm.TABS[self.tab] == "Models"
                                   and any(s["state"] == "downloading" for s in self.model_states()))):
            self.render()
        return True

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
        if it.row.kind == "voice":
            self.change_voice(sm.step(it.row, self.value_of(it.row), direction))
            return
        new = sm.step(it.row, self.value_of(it.row), direction)
        if new != self.value_of(it.row):
            self.save(it.row.key, new)
            if it.row.key == "elevenlabs_voice_id":
                self.check_elevenlabs()
            if it.row.key == "response_speed":  # a preset sets the wait and the speech model together
                for key, value in sm.SPEED_PRESETS[new].items():
                    self.save(key, value)
            elif it.row.key in ("vad_stop_secs", "whisper_cpu_model"):
                self.save("response_speed", sm.speed_of(self.values))
            if it.row.key == "brain":
                self.save("brain_model", "")  # the old model name belongs to the old brain
            if it.row.key == "whisper_device" and new == "auto" and shutil.which("nvidia-smi"):
                self.get_accurate()
        self.render()

    def get_accurate(self) -> None:
        """Accurate needs Large v3 Turbo and GPU support; fetch whatever is missing."""
        for model_id in ("gpu", "whisper-large-turbo"):
            if self.model_state(model_id)["state"] != "ready":
                self.start_download(model_id)

    def change_voice(self, choice: str) -> None:
        """A downloaded (or cloud) voice is saved at once; one that needs a download waits for Enter."""
        model_id = self.voice_model(choice)
        if model_id and self.model_state(model_id)["state"] != "ready":
            self.pending_voice = choice  # shown, not saved: Rum keeps the current voice
        else:
            self.pending_voice = None
            for key, value in sm.voice_updates(choice).items():
                self.save(key, value)
            if choice.startswith("elevenlabs:"):
                self.check_elevenlabs()
        self.render()

    def activate(self) -> None:
        it = self.items[self.index]
        if it.kind == "model":
            self.model_action(it.data)
            return
        if it.kind == "setting" and it.row.kind == "voice":
            choice = self.pending_voice
            if choice and self.voice_model(choice):
                self.start_download(self.voice_model(choice), then=lambda c=choice: self.change_voice(c))
            else:
                self.change_voice(sm.step(it.row, self.value_of(it.row), +1))
            return
        if it.kind == "setting" and it.row.key == "whisper_device" and self.processing_note().startswith("needs"):
            self.get_accurate()
            return
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
        if it.kind == "model":
            token = f"remove:{it.data['id']}"
            if it.data["state"] != "ready":
                self.flash(f"{it.data['title']} isn't downloaded")
            elif self.armed == token:
                self.armed = None
                self.remove_model(it.data)
            else:
                self.armed = token
                self.flash(f"Press D again to remove {it.data['title']}")
            return
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
                self.flash("Conversation moved to the trash (~/.local/share/omarum/trash)")
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
        self.pending_voice = None
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
