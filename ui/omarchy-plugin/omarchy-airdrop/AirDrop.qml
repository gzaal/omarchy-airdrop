import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy-airdrop"

  property string receiverState: "off" // off | running | peers
  property bool receiverRunning: false
  property int peerCount: 0
  property string detail: "airdrop not installed"

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  IpcHandler {
    target: "omarchy-airdrop"

    function refresh(): void {
      root.broadcast("refresh")
    }
  }

  Process {
    id: statusProc
    command: [Quickshell.env("HOME") + "/.local/bin/airdrop", "status"]
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.receiverRunning = false
        root.detail = "airdrop not installed"
        root.receiverState = "off"
        root.peerCount = 0
      }
    }
    stdout: StdioCollector {
      onStreamFinished: {
        var running = false
        var lines = text.split("\n")
        for (var i = 0; i < lines.length; i++) {
          if (lines[i].startsWith("receiver:")) running = lines[i].indexOf("running") >= 0
        }
        root.receiverRunning = running
        peersProc.running = true
      }
    }
  }

  Process {
    id: peersProc
    command: [Quickshell.env("HOME") + "/.local/bin/airdrop", "peers", "--timeout", "1.0"]
    stdout: StdioCollector {
      onStreamFinished: {
        var count = 0
        var trimmed = text.trim()
        if (trimmed.length > 0 && !trimmed.startsWith("no peers")) {
          count = Math.max(0, trimmed.split("\n").length - 1)
        }
        root.peerCount = count
        root.receiverState = root.receiverRunning && count > 0 ? "peers" : (root.receiverRunning ? "running" : "off")
        root.detail = root.receiverRunning
            ? ("receiver up" + (count > 0 ? " — " + count + " peer(s)" : ""))
            : "airdrop not running"
      }
    }
  }

  Timer {
    interval: 10000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.receiverState === "off" ? "\uf0e0" : "\uf0f0"
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.detail
    onPressed: {
      if (root.receiverState === "off") {
        root.bar.run("omarchy-launch-floating-terminal airdrop receive --prompt")
      } else {
        root.bar.run("omarchy-launch-floating-terminal airdrop peers")
      }
    }
  }
}
