import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy-airdrop"

  property string state: "off" // off | running | peers
  property int peerCount: 0
  property string detail: "airdrop not running"

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
    stdout: StdioCollector {
      onStreamFinished: {
        var running = false
        var iface = "none"
        var peers = 0
        var lines = text.split("\n")
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i]
          if (line.startsWith("receiver:")) running = line.indexOf("running") >= 0
        }
        peersProc.running = true
      }
    }
  }

  Process {
    id: peersProc
    command: [Quickshell.env("HOME") + "/.local/bin/airdrop", "peers", "--timeout", "1.0"]
    stdout: StdioCollector {
      onStreamFinished: {
        var lines = text.trim().split("\n")
        root.peerCount = Math.max(0, lines.length - 1)
        root.state = running && root.peerCount > 0 ? "peers" : (running ? "running" : "off")
        root.detail = running ? ("receiver up" + (root.peerCount > 0 ? " — " + root.peerCount + " peer(s)" : "")) : "airdrop not running"
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
    text: root.state === "off" ? "\uf0e0" : "\uf0f0"
    slotSize: Style.bar.statusSlot
    fontSize: Style.font.caption
    tooltipText: root.detail
    onPressed: {
      if (root.state === "off") {
        root.bar.run("omarchy-launch-floating-terminal airdrop receive --prompt")
      } else {
        root.bar.run("omarchy-launch-floating-terminal airdrop peers")
      }
    }
  }
}
