// Advanced search (like libview.SearchBox): two rows of sections in the saved order. Checkbox in the header =
// section on/off (selection stays), „Reset“ = clear the section. adv = qadvsearch.AdvBackend.
import QtQuick

Item {
    id: a
    property var adv
    property real openH: adv.open ? adv.panelHeight : 0
    property real dragH: -1
    height: (dragH >= 0 ? dragH : openH) + bar.height
    Behavior on openH { enabled: a.dragH < 0; NumberAnimation { id: openAnim; duration: 300 * Math.max(0.01, shell.speed); easing.type: Easing.OutCubic } }
    // for the Library: final height and „is sliding“ – meanwhile the grid below is only shifted, not re-laid out
    readonly property bool animating: openAnim.running
    readonly property real targetH: (dragH >= 0 ? dragH : (adv.open ? adv.panelHeight : 0)) + bar.height

    Flickable {
        ScrollHint {}
        id: fl
        opacity: shell.advReady ? 1 : 0.14   // game without its own filters: greyed out, „Coming soon“ on top
        width: parent.width
        height: Math.max(0, a.height - bar.height)
        clip: true
        contentWidth: Math.max(width, rowsLoader.item ? rowsLoader.item.implicitWidth : 0)
        contentHeight: rowsLoader.item ? rowsLoader.item.implicitHeight : 0
        boundsBehavior: Flickable.StopAtBounds
        visible: height > 1
        // sections only exist while the panel is (nearly) open – then kept 60 s, so re-opening is instant
        property bool warm: false
        onVisibleChanged: if (visible) { warm = true; coolDown.stop() } else coolDown.restart()
        Timer { id: coolDown; interval: 60000; onTriggered: fl.warm = false }
        Loader {
            id: rowsLoader
            asynchronous: true   // built over a few frames while the panel slides open (it is still nearly closed then)
            active: fl.visible || fl.warm
            sourceComponent: rowsComp
        }
    }
    Component {
        id: rowsComp
        Column {
            id: rows
            width: fl.contentWidth
            spacing: 10
            readonly property var secs: a.adv.sections
            readonly property int half: Math.ceil(secs.length / 2)
            // height from the target (on expand/collapse the boxes keep their size, only dragging makes them follow)
            readonly property real rowH: Math.max(240, ((a.dragH >= 0 ? a.dragH : a.adv.panelHeight) - 10) / 2 - 2)
            Repeater {
                model: 2
                Row {
                    id: srow
                    required property int index
                    readonly property var mine: rows.secs.slice(index === 0 ? 0 : rows.half, index === 0 ? rows.half : rows.secs.length)
                    readonly property real totalStretch: { var t = 0; for (var i = 0; i < mine.length; i++) t += mine[i].stretch; return Math.max(1, t) }
                    spacing: 10
                    width: rows.width
                    height: rows.rowH
                    Repeater {
                        model: srow.mine
                        delegate: SectionCard {
                            required property var modelData
                            sec: modelData
                            adv: a.adv
                            height: srow.height
                            width: Math.max(150, (srow.width - 10 * (srow.mine.length - 1)) * modelData.stretch / srow.totalStretch)
                        }
                    }
                }
            }
        }
    }

    // bar: click = open/close, drag = height (or drag open/closed)
    Item {
        id: bar
        width: parent.width
        height: 16
        y: a.height - height
        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 1; color: T.line; opacity: 0.8 }
        Rectangle {
            anchors.centerIn: parent
            width: 46; height: 10; radius: 5
            color: T.bg
            Row {
                anchors.centerIn: parent; spacing: 4
                Repeater { model: 3; Rectangle { width: 4; height: 4; radius: 2; color: bh.hovered || bd.active ? T.text : T.dim } }
            }
        }
        HoverHandler { id: bh; cursorShape: Qt.SizeVerCursor }
        TapHandler { onTapped: a.adv.setOpen(!a.adv.open) }
        DragHandler {
            id: bd
            target: null; xAxis.enabled: false
            property real start: 0
            onActiveChanged: {
                if (active) { start = a.adv.open ? a.adv.panelHeight : 0; a.dragH = start }
                else {
                    var close = a.dragH < (a.adv.open ? 240 - 60 : 60)
                    if (!close) a.adv.setPanelHeight(Math.round(Math.max(240, a.dragH)))
                    a.adv.setOpen(!close)
                    a.dragH = -1
                }
            }
            onTranslationChanged: if (active) {   // (dragging the grip also works with „Coming soon“)
                var v = Math.max(0, start + translation.y)
                if (a.adv.open && v < 240) v = 240 - (240 - v) * 0.45   // below the minimum size: stiff like rubber
                a.dragH = v
            }
        }
    }
    // „Coming soon“ over the filters while the game has none of its own (clicks don't pass through)
    Item {
        visible: !shell.advReady && fl.height > 1
        width: fl.width; height: fl.height
        z: 5
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function (w) { w.accepted = true } }
        Rectangle {
            anchors.centerIn: parent
            width: 340; height: 132; radius: 14
            color: T.bg; border.width: 1; border.color: T.line
        }
        Column {
            anchors.centerIn: parent
            spacing: 8
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("Advanced search")
                   color: T.text; font.family: T.display; font.pixelSize: 30 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("Coming soon")
                   color: T.muted; font.family: T.font; font.pixelSize: 15; font.letterSpacing: 3 }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.gameLabel
                   color: T.muted; font.family: T.font; font.pixelSize: 12 }
        }
    }
}
