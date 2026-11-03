// Game button at the far left of the bar: shows the open game. Click slides out a row with the games below it:
// first the loaded ones (by cards in the collection), a dot as divider, then greyed out the ones not yet
// loaded. Clicking a loaded game opens it and closes the row. Clicking a not-loaded one: next to it
// a framed field „Download? approx. … MB · Yes · No“ slides open (like the advanced search chips);
// „Yes“ shows the progress in the same place. It does not switch automatically.
// Top right before the icons: the download circle (button like the icons next to it) – slides in while loading
// (only real downloads, never on game switch); click expands the list.
import QtQuick

Item {
    id: gp
    property real navY: 0          // top edge of the bar
    property real navH: 56
    property bool shown: true      // bar visible?
    property bool open: false
    property string asking: ""     // game for which „Download?“ is currently open
    property bool listOpen: false  // list of the download circle
    readonly property real btnW: 150
    readonly property real panelH: 62
    readonly property real leftW: btnW                    // space on the left of the bar
    property real ringRight: width - 16                   // right edge of the circle (Main.qml)
    readonly property real ringW: 76   // like the icons on the right (statistics, settings …)
    // 0 … 1: circle slides in – the bar makes room on the right accordingly
    // circle: while something is loading, while a finished download hasn't been looked at yet (check + lamp), while
    // the list is open – and with a downloaded update, until restart
    property real ringK: gp.shown && (shell.jobsActive || gp.unseen || gp.listOpen || shell.updateReady) ? 1 : 0
    Behavior on ringK { NumberAnimation { duration: 260 * Math.max(0.01, shell.speed); easing.type: Easing.OutCubic } }
    readonly property real rightW: ringK * (ringW + 8)
    onRingKChanged: if (ringK === 0) listOpen = false   // otherwise the list would keep the scan bar open

    // clicking beside it closes (only while open – otherwise the area takes no clicks)
    MouseArea {
        anchors.fill: parent
        visible: gp.open || gp.listOpen
        onClicked: { gp.open = false; gp.listOpen = false; gp.asking = "" }
    }

    Btn {
        id: knob
        visible: gp.shown
        x: 16; y: gp.navY + 8
        width: gp.btnW; height: gp.navH - 18
        text: shell.gameLabel + "  " + (gp.open ? "▴" : "▾")
        iconSource: shell.gameIcon
        active: gp.open
        badgeText: shell.allGames ? "∞" : ""   // price alarms: all games are on, the current one stays open
        tip: shell.allGames ? shell.text("Price alerts show all games") : shell.text("Choose game")
        Connections { target: shell; function onAllGamesChanged() { if (shell.allGames) knob.blinkBadge() } }
        onClicked: { gp.open = !gp.open; gp.listOpen = false; gp.asking = "" }
    }

    // ---------- Download circle ----------
    // done: check + lamp until clicked (then the lamp goes out); a downloaded update keeps the button
    // until restart („Restart“ in the list)
    property bool unseen: false
    property string updSeen: ""   // update whose lamp was already clicked
    readonly property bool doneFlash: !shell.jobsActive || shell.updateReady
    Connections {
        target: shell
        function onJobsChanged() {
            if (shell.jobsActive && !shell.updateReady) { gp.unseen = false; ring.wasActive = true }
            else if (ring.wasActive) { ring.wasActive = false; gp.unseen = true }
        }
    }
    Btn {
        id: ring
        property bool wasActive: false
        visible: gp.ringK > 0.01
        width: gp.ringW; height: gp.navH - 18
        x: gp.ringRight - width * gp.ringK
        y: gp.navY + 8
        opacity: gp.ringK
        active: gp.listOpen
        badge: gp.unseen || (shell.updateReady && gp.updSeen !== shell.updateVersion)
        tip: shell.updateReady ? shell.text("Update downloaded – click shows “Restart”")
             : gp.doneFlash ? shell.text("All downloaded – click to look")
             : shell.jobsPaused ? shell.text("Downloads paused – click to see the list")
             : shell.text("Downloads – click to see what's loading")
        onClicked: { gp.listOpen = !gp.listOpen; gp.open = false; gp.unseen = false
                     if (shell.updateReady) gp.updSeen = shell.updateVersion }
        Canvas {   // circle that fills radially
            id: arc
            anchors.centerIn: parent
            width: 24; height: 24
            property real p: shell.jobsProgress
            property bool done: gp.doneFlash
            property bool paused: shell.jobsPaused
            property color ink: ring.ink
            onPChanged: requestPaint()
            onDoneChanged: requestPaint()
            onPausedChanged: requestPaint()
            onInkChanged: requestPaint()
            onAvailableChanged: if (available) requestPaint()
            onPaint: {
                var g = getContext("2d"), r = 10, c = width / 2
                g.reset()
                g.lineWidth = 2.2; g.lineCap = "round"
                g.strokeStyle = Qt.rgba(1, 1, 1, 0.14)
                g.beginPath(); g.arc(c, c, r, 0, Math.PI * 2); g.stroke()
                g.strokeStyle = String(ink)
                g.beginPath(); g.arc(c, c, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (done ? 1 : Math.max(0.03, p))); g.stroke()
                if (done) {          // check
                    g.lineWidth = 2; g.beginPath(); g.moveTo(c - 4, c); g.lineTo(c - 1, c + 3); g.lineTo(c + 4.5, c - 3.5); g.stroke()
                } else if (paused) { // paused: ‖
                    g.lineWidth = 2; g.beginPath(); g.moveTo(c - 2.5, c - 4); g.lineTo(c - 2.5, c + 4)
                    g.moveTo(c + 2.5, c - 4); g.lineTo(c + 2.5, c + 4); g.stroke()
                } else {             // arrow down
                    g.lineWidth = 1.9; g.beginPath(); g.moveTo(c, c - 4.5); g.lineTo(c, c + 3.5); g.moveTo(c - 3.2, c + 0.4)
                    g.lineTo(c, c + 3.5); g.lineTo(c + 3.2, c + 0.4); g.stroke()
                }
            }
        }
    }
    Rectangle {   // list: what is loading, what is waiting – each with remaining time and cancel
        id: list
        z: 3   // above the games row
        visible: gp.listOpen && gp.shown && gp.ringK > 0.01   // circle gone: list too
        x: Math.max(16, gp.ringRight - width); y: gp.navY + gp.navH + 6
        width: 380; height: listCol.implicitHeight + 24
        radius: 12; color: T.surface; border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent }
        Column {
            id: listCol
            x: 14; y: 12; width: parent.width - 28
            spacing: 10
            Text { visible: shell.jobsList.length === 0; text: shell.text("All done ✓"); color: T.text2
                   font.family: T.font; font.pixelSize: 13 }
            Repeater {
                model: shell.jobsList
                Item {
                    required property var modelData
                    required property int index
                    width: listCol.width; height: 40
                    Text { width: parent.width - 76; elide: Text.ElideRight; text: modelData.name
                           color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: modelData.running }
                    Text { y: 18; width: parent.width - 76; elide: Text.ElideRight
                           text: modelData.state + (modelData.pct >= 0 ? " · " + modelData.pct + " %" : "") + (modelData.est ? " · " + modelData.est : "")
                           color: T.muted; font.family: T.font; font.pixelSize: 11 }
                    Rectangle { visible: modelData.running; y: 36; width: (parent.width - 76) * Math.max(0, modelData.pct) / 100; height: 2; radius: 1; color: T.hi }
                    Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                          visible: modelData.ready === true; height: 28; compact: true; primary: true; width: implicitWidth
                          text: shell.text("Restart"); tip: shell.text("Saves everything and restarts with the new version")
                          onClicked: shell.installUpdate() }
                    Btn { anchors.right: parent.right; anchors.rightMargin: modelData.kind === "update" ? 0 : 36
                          anchors.verticalCenter: parent.verticalCenter
                          width: 30; height: 28; compact: true; visible: modelData.pausable
                          glyph: modelData.paused ? "play" : "pause"
                          tip: modelData.paused ? shell.text("Continue") : shell.text("Pause – continues from here later")
                          onClicked: shell.pauseJob(index) }
                    Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 30; height: 28; compact: true
                          visible: modelData.kind !== "update"
                          text: "×"; tip: shell.text("Cancel"); onClicked: shell.cancelJob(index) }
                }
            }
        }
    }

    // ---------- Row with the games ----------
    Item {
        id: panel
        y: gp.navY + gp.navH
        width: parent.width
        height: gp.open ? gp.panelH : 0
        clip: true
        visible: height > 0.5
        Behavior on height { NumberAnimation { duration: 180 * Math.max(0.01, shell.speed); easing.type: Easing.OutCubic } }
        Loader {   // the games only while the row is open or closing
            anchors.fill: parent
            active: gp.open || panel.visible
            sourceComponent: Item {
            MouseArea { anchors.fill: parent; onClicked: gp.asking = "" }   // clicks on the row don't close it
            Rectangle { anchors.fill: parent; color: T.bg }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: T.line2; opacity: 0.6 }

            Row {
                x: 16; y: (gp.panelH - 40) / 2 - 1
                spacing: 10
                Repeater {
                    model: shell.gameChoices
                    delegate: Row {
                        id: cell
                        required property var modelData
                        required property int index
                        readonly property bool firstMissing: !modelData.installed && index > 0 && shell.gameChoices[index - 1].installed
                        spacing: 10
                        Rectangle {   // divider between loaded and not-loaded games (as in the main menu)
                            visible: cell.firstMissing
                            anchors.verticalCenter: parent.verticalCenter
                            width: 5; height: 5; radius: 2.5; color: T.line2
                        }
                        Item {   // button + lamp (the lamp is not greyed out along with it – all equally bright)
                            id: gcell
                            width: gbtn.width; height: 40
                            visible: !modelData.loading
                            // drag onto the edge of another game = order (as with the decks); otherwise by card count
                            readonly property string gkey: modelData.key
                            Drag.active: gdrag.active
                            Drag.keys: ["game"]
                            Drag.source: gcell
                            Drag.hotSpot.x: gdrag.centroid.pressPosition.x; Drag.hotSpot.y: height / 2   // drop target = under the mouse
                            DragHandler { id: gdrag; enabled: modelData.installed; xAxis.enabled: true; yAxis.enabled: false
                                          onActiveChanged: if (!active) { gcell.Drag.drop(); gcell.x = 0 } }
                            z: gdrag.active ? 50 : 0
                            DropArea { id: gl; x: 0; width: parent.width / 2; height: parent.height; keys: ["game"]
                                       enabled: modelData.installed && !gdrag.active
                                       onDropped: function (ev) { var s = drag.source; if (s && s !== gcell)
                                           Qt.callLater(shell.reorderGames, s.gkey, gcell.gkey, false) } }
                            DropArea { id: gr; x: parent.width / 2; width: parent.width / 2; height: parent.height; keys: ["game"]
                                       enabled: modelData.installed && !gdrag.active
                                       onDropped: function (ev) { var s = drag.source; if (s && s !== gcell)
                                           Qt.callLater(shell.reorderGames, s.gkey, gcell.gkey, true) } }
                            Rectangle { visible: gl.containsDrag; x: -7; y: 4; width: 3; height: parent.height - 8; radius: 1.5; color: "#e6e6e6" }
                            Rectangle { visible: gr.containsDrag; x: parent.width + 4; y: 4; width: 3; height: parent.height - 8; radius: 1.5; color: "#e6e6e6" }
                            Btn {
                                id: gbtn
                                width: Math.max(118, implicitWidth); height: 40
                                text: modelData.name
                                iconSource: modelData.icon || ""
                                opacity: !modelData.installed ? 0.38 + 0.3 * h : (modelData.on ? 1 : 0.45 + 0.4 * h)
                                tip: modelData.later ? shell.text("Coming with the next update")
                                     : !modelData.installed ? shell.text("Not downloaded yet – click to download")
                                     : (modelData.active ? shell.text("Currently open") : shell.text("Open this game"))
                                onClicked: {
                                    if (!modelData.installed) { gp.asking = gp.asking === modelData.key ? "" : modelData.key; return }
                                    gp.asking = ""
                                    if (!modelData.active) shell.pickGame(modelData.key)
                                    gp.open = false   // entering a game: row closes
                                }
                            }
                            Lamp { visible: shell.allGames && modelData.installed   // price alarms: every game is on
                                   x: gbtn.width - 15; y: 3.5; z: 5 }
                        }
                        Rectangle {   // „Download? approx. … MB · Yes · No“ – slides open next to it
                            id: ask
                            readonly property bool on: gp.asking === modelData.key && !modelData.loading
                            anchors.verticalCenter: parent.verticalCenter
                            height: 40; radius: 10; clip: true
                            width: on ? askRow.implicitWidth + 20 : 0
                            visible: width > 0.5
                            Behavior on width { NumberAnimation { duration: 180 * Math.max(0.01, shell.speed); easing.type: Easing.OutCubic } }
                            color: "transparent"; border.width: 1; border.color: T.line2
                            Row {
                                id: askRow
                                x: 10; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                                Text { anchors.verticalCenter: parent.verticalCenter
                                       text: modelData.later ? shell.text("The card data comes with the next update.")
                                             : shell.text("Download?") + " " + (modelData.mb > 0 ? "ca. " + modelData.mb + " MB" : "")
                                       color: T.text; font.family: T.font; font.pixelSize: 13 }
                                Btn { visible: !modelData.later; height: 30; compact: true; text: shell.text("Yes"); primary: true
                                      onClicked: { gp.asking = ""; shell.downloadGame(modelData.key) } }
                                Btn { height: 30; compact: true; text: shell.text(modelData.later ? "OK" : "No"); onClicked: gp.asking = "" }
                            }
                        }
                        Rectangle {   // loading: in place of the button name, progress and bar
                            visible: modelData.loading
                            anchors.verticalCenter: parent.verticalCenter
                            width: 220; height: 40; radius: 10; color: "transparent"; border.width: 1; border.color: T.line
                            Text { x: 12; y: 5; text: modelData.name; color: T.text2; font.family: T.font; font.pixelSize: 12; font.bold: true }
                            Text { anchors.right: parent.right; anchors.rightMargin: 12; y: 5
                                   text: modelData.progress > 0 ? Math.round(modelData.progress * 100) + " %" : shell.text("waiting …")
                                   color: T.muted; font.family: T.font; font.pixelSize: 12 }
                            Rectangle { x: 12; y: 26; width: parent.width - 24; height: 4; radius: 2; color: Qt.rgba(1, 1, 1, 0.1)
                                Rectangle { width: parent.width * modelData.progress; height: parent.height; radius: 2; color: T.hi } }
                        }
                    }
                }
                Text {   // emergency switch (games/offswitch.py): which game is gone – the reason as tooltip
                    id: offNote
                    visible: shell.gamesOffNote !== ""
                    anchors.verticalCenter: parent.verticalCenter
                    leftPadding: 8
                    text: shell.gamesOffNote
                    color: T.muted; font.family: T.font; font.pixelSize: 12
                    HoverHandler {
                        id: offHover
                        onHoveredChanged: {
                            if (hovered) { var p = offNote.mapToItem(null, offNote.width / 2, offNote.height); shell.tip(shell.gamesOffWhy, p.x, p.y) }
                            else shell.tip("", 0, 0)
                        }
                    }
                }
            }
            Text {
                anchors.right: parent.right; anchors.rightMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                text: shell.text("Each game has its own data")
                color: T.muted; font.family: T.font; font.pixelSize: 12
                visible: parent.width > 1300 && gp.asking === ""
            }
            }
        }
    }
}
