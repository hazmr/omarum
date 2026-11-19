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
  function bind() {
    if (bound && bound !== keys) unbind()
    if (!keys) return
    eval_('hl.bind("' + keys + '", hl.dsp.global("omarum:talk"), { description = "Talk to Rum (hold) / hands-free (tap)" })')
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
    name: "talk"
    description: "Talk to Rum (hold) / hands-free (tap)"
    onPressed: shortcut.engine.send("ptt_down")
    onReleased: shortcut.engine.send("ptt_up")
  }

  // A config reload drops runtime binds: put ours back.
  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (event.name === "configreloaded") { shortcut.bound = ""; shortcut.bind() }
    }
  }
}
