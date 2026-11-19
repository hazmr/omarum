"""Omarum settings: a keyboard-first window in Omarchy's style (mockup settings-window-v2).

Runs on the system Python with GTK4. All logic lives in stdlib modules that are unit-tested:
omarum.settings_model (rows), omarum.configio (saving), omarum.library (memory, conversations).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

from omarum import library, settings_model as sm  # noqa: E402
from omarum.config import load_config  # noqa: E402
from omarum.configio import has_secret, save_config, set_secret  # noqa: E402
from omarum.ipc import DaemonNotRunning, send_command  # noqa: E402
from omarum.models import MODELS_DIR  # noqa: E402
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
        self.armed: str | None = None  # "forget:3" / "delete:<dir>" waiting for a second d
        self.player: subprocess.Popen | None = None
        self.message = ""

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
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.connect("close-request", lambda *_: self.stop_playback() or False)
        self.render()

    # -- data -----------------------------------------------------------------
    def build_items(self) -> list[Item]:
        tab = sm.TABS[self.tab]
        items: list[Item] = []
        group = None
        for r in sm.rows_for(tab):
            if r.group != group:
                group = r.group
                items.append(Item("group", group))
            items.append(Item("setting", r.label, r, hint=r.hint))
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

    def status(self) -> list[tuple[str, bool, str]]:
        whisper = sorted(p.name for p in (MODELS_DIR / "whisper").glob("*") if (p / "model.bin").exists()) \
            if (MODELS_DIR / "whisper").is_dir() else []
        return [
            ("Claude CLI", shutil.which("claude") is not None, "your subscription is the brain"),
            ("ZONOS3 voice", zonos3_installed(), "local voice server"),
            ("Kokoro voice", (MODELS_DIR / "kokoro" / "kokoro-v1.0.onnx").exists(), "always-there fallback"),
            ("Whisper models", bool(whisper), ", ".join(whisper) or "downloaded on first use"),
            ("ElevenLabs key", has_secret("ELEVENLABS_API_KEY"), "optional cloud voice"),
        ]

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
            w = self.render_item(it, focused=(i == self.index))
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

    def render_item(self, it: Item, focused: bool) -> Gtk.Widget:
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
            row.append(self.render_value(it.row, focused))
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

    def render_value(self, r: sm.Row, focused: bool) -> Gtk.Widget:
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
                box.append(s)
            return box
        if r.kind == "slider":
            lo, hi, _inc, _unit = r.options
            filled = round((value - lo) / (hi - lo) * 20) if hi > lo else 0
            bar = "━" * filled + "●" + "─" * (20 - filled)
            v = Gtk.Label(label=f"{bar}  {sm.display(r, value)}")
            v.add_css_class("value")
            return v
        if r.kind == "toggle":
            v = Gtk.Label(label=("[■■  on ]" if value else "[ off ■■]"))
            v.add_css_class("value")
            return v
        if r.kind == "cycle":
            box = Gtk.Box(spacing=8)
            for text, cls in (("‹", "arrow"), (sm.display(r, value).center(18), "value"), ("›", "arrow")):
                lab = Gtk.Label(label=text)
                lab.add_css_class(cls)
                box.append(lab)
            return box
        v = Gtk.Label(label=sm.display(r, value) if r.kind in ("secret", "text") else "")
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
        if it.kind != "setting" or it.row.kind in ("text", "secret", "action"):
            return
        new = sm.step(it.row, self.value_of(it.row), direction)
        if new != self.value_of(it.row):
            self.save(it.row.key, new)
        self.render()

    def activate(self) -> None:
        it = self.items[self.index]
        if it.kind == "setting" and it.row.kind in ("text", "secret"):
            self.start_edit(it.row)
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
        self.editing = entry
        self.render()
        GLib.idle_add(entry.grab_focus)

    def finish_edit(self, r: sm.Row, text: str) -> None:
        self.editing = None
        if r.kind == "secret":
            set_secret(r.key, text.strip())
            self.flash("Key saved" if text.strip() else "Key removed")
        elif text.strip():
            self.save(r.key, text.strip())
        self.render()

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
        self.index = i
        self.render()
        self.activate()

    def on_key(self, _ctrl, keyval, _code, state) -> bool:
        if self.editing is not None:
            if keyval == Gdk.KEY_Escape:
                self.editing = None
                self.render()
                return True
            return False  # typing goes to the entry
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
    app.connect("activate", lambda a: Settings(a).present())
    app.run([])


if __name__ == "__main__":
    main()
