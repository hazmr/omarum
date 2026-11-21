import QtQuick
import Quickshell
import Quickshell.Hyprland

// The talk key, owned by the plugin (see omarum/ptt.py): double tap opens/closes Rum; hold to
// talk, and letting go of the key, Ctrl or Shift stops listening. Saying "bye" closes her.
// The key is bound at runtime (nothing written to ~/.config/hypr), bound again after
// every Hyprland config reload, and unbound when the plugin unloads.
Scope {
  id: shortcut

  required property var engine

  // From config (`talk_shortcut`), e.g. "CTRL + SHIFT + SPACE"; "" = no shortcut.
  readonly property string keys: {
    var k = String(engine.info.talk_keys !== undefined ? engine.info.talk_keys : "CTRL + SHIFT + SPACE").toUpperCase()
    return /^[A-Z0-9_]+( \+ [A-Z0-9_]+)*$/.test(k) ? k : ""
  }
  property string bound: ""

  function eval_(lua) { Quickshell.execDetached(["hyprctl", "eval", lua]) }

  // evdev codes, as Superwhisper's shortcut bridge uses them (Hyprland's Lua event gives XKB = evdev + 8).
  readonly property var keyCodes: ({
    SPACE: 57, RETURN: 28, TAB: 15, ESCAPE: 1, BACKSPACE: 14, GRAVE: 41,
    F1: 59, F2: 60, F3: 61, F4: 62, F5: 63, F6: 64, F7: 65, F8: 66, F9: 67, F10: 68, F11: 87, F12: 88,
    Q: 16, W: 17, E: 18, R: 19, T: 20, Y: 21, U: 22, I: 23, O: 24, P: 25,
    A: 30, S: 31, D: 32, F: 33, G: 34, H: 35, J: 36, K: 37, L: 38,
    Z: 44, X: 45, C: 46, V: 47, B: 48, N: 49, M: 50,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9, "9": 10, "0": 11
  })
  readonly property var modNames: ({ CTRL: "ctrl", CONTROL: "ctrl", SHIFT: "shift", ALT: "alt", SUPER: "super", WIN: "super" })

  // The shortcut as { mods: {ctrl,shift,alt,super}, code } or null when the watcher can't follow it.
  function parse(k) {
    var mods = { ctrl: false, shift: false, alt: false, super: false }, code = -1
    var parts = k.split(" + ")
    for (var i = 0; i < parts.length; i++) {
      var m = modNames[parts[i]]
      if (m) mods[m] = true
      else if (keyCodes[parts[i]] !== undefined && code < 0) code = keyCodes[parts[i]]
      else return null
    }
    return code < 0 ? null : { mods: mods, code: code }
  }

  // Watch the real key edges, the way Superwhisper does: Hyprland reports every press and release
  // of every key, so we always know whether Ctrl, Shift and the key are down. Talking starts when
  // the key goes down with the modifiers held, and stops the moment any of them comes up. Each
  // change is sent once (no doubled or lost presses from binds). A do-nothing bind on the combo
  // keeps the key from reaching the focused app. The watcher registers once per Lua state and
  // reads its settings from the omarum_talk table, so re-binding only updates that table.
  function watcherLua(k, sc) {
    var m = sc.mods
    return 'pcall(hl.unbind, "' + k + '")\n'
      + 'omarum_talk = omarum_talk or { held = {}, talking = false }\n'
      + 'local T = omarum_talk\n'
      + 'T.on, T.code = true, ' + sc.code + '\n'
      + 'T.ctrl, T.shift, T.alt, T.super = ' + m.ctrl + ', ' + m.shift + ', ' + m.alt + ', ' + m.super + '\n'
      + 'if not T.hooked then\n'
      + '  T.hooked = true\n'
      + '  hl.on("input.keyboard.key", function(code, time, state)\n'
      + '    local T = omarum_talk\n'
      + '    if state ~= 0 and state ~= 1 then return end\n'
      + '    code = code - 8\n'
      + '    T.held[code] = (state == 1) or nil\n'
      + '    if not T.on then T.talking = false; return end\n'
      + '    local function any(a, b) return T.held[a] or T.held[b] end\n'
      + '    local mods = (not T.ctrl or any(29, 97)) and (not T.shift or any(42, 54))\n'
      + '      and (not T.alt or any(56, 100)) and (not T.super or any(125, 126))\n'
      + '    local now = (mods and T.held[T.code]) and true or false\n'
      + '    if now ~= T.talking then\n'
      + '      T.talking = now\n'
      + '      hl.dispatch(hl.dsp.global(now and "omarum:talk-down" or "omarum:talk-up"))\n'
      + '    end\n'
      + '  end)\n'
      + 'end\n'
      + 'hl.bind("' + k + '", function() end, { description = "Talk to Rum (double tap: open/close, hold: talk)" })'
  }

  // Fallback for keys the watcher doesn't know: a press bind and a release bind.
  function bindsLua(k) {
    return 'pcall(hl.unbind, "' + k + '")\n'
      + 'if omarum_talk then omarum_talk.on = false end\n'
      + 'hl.bind("' + k + '", hl.dsp.global("omarum:talk-down"), '
      + '{ description = "Talk to Rum (double tap: open/close, hold: talk)" })\n'
      + 'hl.bind("' + k + '", hl.dsp.global("omarum:talk-up"), '
      + '{ description = "Talk to Rum: release", release = true, transparent = true, ignore_mods = true, non_consuming = true })'
  }

  function bind() {
    if (bound && bound !== keys) unbind()
    if (!keys) return
    var sc = parse(keys)
    eval_(sc ? watcherLua(keys, sc) : bindsLua(keys))
    bound = keys
  }
  function unbind() {
    if (bound) eval_('pcall(hl.unbind, "' + bound + '")\nif omarum_talk then omarum_talk.on = false end')
    bound = ""
  }

  onKeysChanged: if (engine.info.talk_keys !== undefined) bind()
  Component.onCompleted: bind()
  Component.onDestruction: unbind()

  GlobalShortcut {
    appid: "omarum"
    name: "talk-down"
    description: "Talk to Rum: key pressed"
    onPressed: shortcut.engine.send("ptt_down")
  }
  GlobalShortcut {
    appid: "omarum"
    name: "talk-up"
    description: "Talk to Rum: key released"
    onPressed: shortcut.engine.send("ptt_up")
  }

  // A config reload drops runtime binds: put ours back.
  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (event.name === "configreloaded") { shortcut.bound = ""; shortcut.bind() }
    }
  }
}
