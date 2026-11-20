import QtQuick
import Quickshell
import Quickshell.Hyprland

// The talk key, owned by the plugin: a walkie-talkie (see omarum/ptt.py). Hold to talk,
// let go and Rum answers; holding while she talks stops her. Saying "bye" closes her.
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
  // Like Omarchy's o.bind_hold: a press bind, and a release bind that ignores modifiers
  // (letting go of Ctrl first must still count) and only fires after its own press.
  function bind() {
    if (bound && bound !== keys) unbind()
    if (!keys) return
    // The keys send the two shortcut events straight away: no Lua functions with a shared "held"
    // flag (those stopped firing after the first press while Ctrl+Shift stayed down). Unbind
    // first: after a shell or plugin reload the old binds are still in Hyprland. The release bind
    // ignores modifiers, so letting go of Space counts even with Ctrl+Shift still held; a stray
    // release without a press is ignored by the daemon.
    eval_('pcall(hl.unbind, "' + keys + '")\n'
      + 'hl.bind("' + keys + '", hl.dsp.global("omarum:talk-down"), '
      + '{ description = "Talk to Rum (hold to talk, let go to hear her)" })\n'
      + 'hl.bind("' + keys + '", hl.dsp.global("omarum:talk-up"), '
      + '{ description = "Talk to Rum: release", release = true, transparent = true, ignore_mods = true, non_consuming = true })')
    bound = keys
  }
  function unbind() {
    if (bound) eval_('hl.unbind("' + bound + '")')
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
