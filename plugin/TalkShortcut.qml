import QtQuick
import Quickshell
import Quickshell.Hyprland

// The talk shortcut, owned by the plugin: hold = talk, tap = hands-free.
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
    eval_('local held = false\n'
      + 'hl.bind("' + keys + '", function() held = true; hl.dispatch(hl.dsp.global("omarum:talk-down")) end, '
      + '{ description = "Talk to Rum (hold) / hands-free (tap)" })\n'
      + 'hl.bind("' + keys + '", function() if held then held = false; hl.dispatch(hl.dsp.global("omarum:talk-up")) end end, '
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
