import QtQuick
import Quickshell
import Quickshell.Io

// Rum's engine, owned by the plugin: setup on load, the daemon as a child process
// (restarted after a crash), and a socket for state, audio levels and commands.
// Unloading the plugin destroys this, which stops the daemon (and its voice server).
Item {
  id: engine
  visible: false

  // <plugin folder> (a clone from `omarchy plugin add`, or a link to the repo).
  readonly property string dir: String(Qt.resolvedUrl("..")).replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string home: Quickshell.env("HOME")
  readonly property string venv: home + "/.local/share/omarum/venv"
  readonly property string python: venv + "/bin/python"
  readonly property string socketPath: Quickshell.env("XDG_RUNTIME_DIR") + "/omarum.sock"
  // PIPEWIRE_LATENCY: a bigger playback buffer, so Rum's voice doesn't crackle when the machine is
  // busy (a screen recorder, a build); ~43 ms is not noticeable in a conversation.
  readonly property var env: ({ UV_PROJECT_ENVIRONMENT: venv, PYTHONUNBUFFERED: "1", PIPEWIRE_LATENCY: "2048/48000" })

  // checking | needs-uv | setup | starting | running | crashed | failed
  property string phase: "checking"
  property string setupMessage: ""
  property real setupProgress: 0
  property string state: "off"     // Rum's own state from the daemon
  property string reason: ""
  property var info: ({})          // `omarum summary`
  property bool stopping: false

  signal level(string who, real value)

  readonly property bool ready: phase === "running" && sock.connected

  function send(cmd) {
    if (!sock.connected) return false
    sock.write(JSON.stringify({ cmd: cmd }) + "\n")
    sock.flush()
    return true
  }
  function retry() {
    reason = ""; setupMessage = ""; phase = "checking"
    findUv.running = true
  }
  function refreshInfo() { if (phase === "running" && !summary.running) summary.running = true }
  function openSettings(tab) {
    Quickshell.execDetached(["/usr/bin/python3", dir + "/settings/omarum_settings.py"].concat(tab ? [tab] : []))
  }

  Component.onCompleted: findUv.running = true
  Component.onDestruction: { stopping = true; daemon.running = false }

  // 1. uv builds Rum's Python environment.
  Process {
    id: findUv
    command: ["sh", "-c", "command -v uv"]
    onExited: function(code) {
      if (code === 0) { engine.phase = "setup"; setup.running = true }
      else { engine.phase = "needs-uv"; engine.reason = "Omarum needs uv. Install it with: omarchy pkg add uv" }
    }
  }

  // 2. Setup: the environment, models, and tidying up an old install. Quick when all is there.
  // --reinstall-package: the engine must run *this* folder's code (the plugin may have moved
  // from a linked checkout to a clone, or been updated), not wherever it was first installed.
  Process {
    id: setup
    environment: engine.env
    command: ["sh", "-c", "uv sync --project \"$1\" --quiet --no-dev --reinstall-package omarum && exec \"$2\" -m omarum.setup", "omarum-setup", engine.dir, engine.python]
    stdout: SplitParser {
      onRead: data => {
        try {
          var msg = JSON.parse(data)
          engine.setupMessage = String(msg.message || "").slice(0, 160)
          engine.setupProgress = msg.total ? msg.done / msg.total : 0
          if (msg.step === "error") engine.reason = engine.setupMessage
        } catch (e) {}
      }
    }
    stderr: SplitParser { onRead: data => { if (data.trim()) engine.setupMessage = String(data).slice(0, 160) } }
    onRunningChanged: if (running) engine.setupMessage = "Setting up Rum…"
    onExited: function(code) {
      if (code === 0) { engine.phase = "starting"; daemon.running = true }
      else { engine.phase = "failed"; engine.reason = engine.reason || ("Setup failed: " + engine.setupMessage) }
    }
  }

  // 3. The daemon, straight from its environment (no wrapper process), restarted after a crash.
  Process {
    id: daemon
    environment: engine.env
    // exec: the shell's child *is* the daemon, so stopping the plugin stops it. Log kept for debugging.
    command: ["sh", "-c", "mkdir -p \"$HOME/.local/state/omarum\" && exec \"$1\" -m omarum.cli daemon >>\"$HOME/.local/state/omarum/daemon.log\" 2>&1", "omarum-daemon", engine.python]
    onRunningChanged: if (running) { engine.phase = "running"; connectTimer.restart(); engine.refreshInfo() }
    onExited: function(code) {
      engine.state = "off"
      if (engine.stopping) return
      engine.phase = "crashed"
      engine.reason = "Rum's engine stopped (exit " + code + "); restarting"
      restartTimer.restart()
    }
  }
  Timer { id: restartTimer; interval: 3000; onTriggered: if (!engine.stopping) daemon.running = true }

  // 4. The socket: state, levels and replies, one JSON object per line.
  Socket {
    id: sock
    path: engine.socketPath
    parser: SplitParser {
      onRead: data => {
        var msg
        try { msg = JSON.parse(data) } catch (e) { return }
        if (msg.type === "level") { engine.level(msg.who || "", Number(msg.value) || 0); return }
        if (msg.type === "state" || msg.ok !== undefined) {
          engine.state = msg.state || "idle"
          engine.reason = msg.state === "error" ? String(msg.reason || "").slice(0, 200) : ""
        }
      }
    }
    onConnectedChanged: {
      if (connected) { write(JSON.stringify({ cmd: "status" }) + "\n"); flush() }
      else { if (engine.state !== "off") engine.state = "off"; connectTimer.restart() }
    }
  }
  Timer {
    id: connectTimer
    interval: 1000
    onTriggered: if (engine.phase === "running" && !sock.connected) { sock.connected = true; restart() }
  }

  // 5. What the panel and orb show (names, engine, last talk, colors, orb, shortcut).
  Process {
    id: summary
    environment: engine.env
    command: [engine.python, "-m", "omarum.cli", "summary"]
    stdout: SplitParser { onRead: data => { try { engine.info = JSON.parse(data) } catch (e) {} } }
  }
  FileView {
    path: engine.home + "/.config/omarum/config.toml"
    watchChanges: true
    onFileChanged: { reload(); engine.refreshInfo() }
  }
  Timer { interval: 60000; repeat: true; running: engine.phase === "running"; onTriggered: engine.refreshInfo() }
  Connections {
    target: engine
    function onStateChanged() { if (["idle", "closed"].indexOf(engine.state) >= 0) engine.refreshInfo() }
  }
}
