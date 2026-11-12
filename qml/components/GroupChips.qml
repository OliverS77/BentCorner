// Group by in the chip row (Oliver, 30.10.): always the last chip of the row, left after the filter chips (Oliver, 05.11.;
// before: at the right end), as soon as the grouping filters something – also with the strip closed. "Group by │ Enchantments 48 ─ Common 21 ─ Mana value 3 7": one chip per picked
// level with its number, a thin line in the gaps (a branch, no arrows). Click = back to that level. Hover shows two
// small keys: × takes only this level away, "Disable" switches it off (grey: stays in the path, doesn't filter) –
// "Enable" = on again.
// Grey for all chips while the whole grouping is off (the switch in the strip). No darkening on hover.
// Its place in the row: the width at rest plus room for the two keys – the keys open into that room, so the chip never
// wraps into the next line under the mouse (and nothing else in the row moves on hover).
import QtQuick

Item {
    id: grc
    property var g                                   // lib.group
    readonly property var chips: g ? g.chips : []
    readonly property bool shown: chips.length > 0
    property real restWidth: 0                       // box width without hover (kept while the mouse is on it)
    readonly property real keysRoom: 18 + 2 + Math.max(tmOn.advanceWidth, tmOff.advanceWidth) + 12 + 4
    implicitWidth: shown ? restWidth + keysRoom : 0
    implicitHeight: shown ? 30 : 0
    width: implicitWidth; height: implicitHeight
    visible: shown

    TextMetrics { id: tmOn; font.family: T.font; font.pixelSize: 11; text: shell.text("Enable") }
    TextMetrics { id: tmOff; font.family: T.font; font.pixelSize: 11; text: shell.text("Disable") }
    Rectangle {
        id: box
        height: 30; radius: 15
        width: row.implicitWidth + 16
        onWidthChanged: if (!boxHover.hovered) grc.restWidth = width
        Component.onCompleted: grc.restWidth = width
        HoverHandler { id: boxHover; onHoveredChanged: if (!hovered) grc.restWidth = box.width }
        color: Qt.darker(T.surface, 1.05)
        border.width: 1; border.color: T.line2
        Row {
            id: row
            x: 8; anchors.verticalCenter: parent.verticalCenter
            spacing: 0
            Text {   // the category
                anchors.verticalCenter: parent.verticalCenter
                text: shell.text("Group by"); rightPadding: 4
                color: grc.g && !grc.g.on ? Qt.rgba(0.67, 0.67, 0.67, 0.45) : T.muted
                font.family: T.font; font.pixelSize: 12; font.bold: true
            }
            Rectangle { width: 1; height: 16; color: T.line2; anchors.verticalCenter: parent.verticalCenter }
            Item { width: 4; height: 1 }
            Repeater {
                model: grc.chips
                Row {
                    id: one
                    required property var modelData
                    required property int index
                    anchors.verticalCenter: parent.verticalCenter
                    Rectangle {   // the branch between two chips: a thin line in the gap
                        visible: one.index > 0
                        width: 10; height: 1; anchors.verticalCenter: parent.verticalCenter
                        color: T.line2
                    }
                    Item {
                        id: chip
                        readonly property bool grey: one.modelData.grey
                        readonly property bool hov: ch.hovered || xh.hovered || dh.hovered
                        height: 22
                        width: lbl.implicitWidth + 18 + (hov ? keys.width + 4 : 0)
                        Behavior on width { enabled: shell.animate; NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                        clip: true
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            anchors.fill: parent; radius: 11
                            color: chip.hov ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, chip.grey ? 0.03 : 0.07)
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }
                        Text {
                            id: lbl
                            x: 9; anchors.verticalCenter: parent.verticalCenter
                            text: one.modelData.label + (one.modelData.cards !== "" && !chip.grey ? "  " + one.modelData.cards : "")
                            color: chip.grey ? Qt.rgba(0.67, 0.67, 0.67, 0.45) : T.text
                            font.family: T.font; font.pixelSize: 12; font.bold: true
                        }
                        HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor }
                        TapHandler {   // back to this level – a grey one comes back on first
                            onTapped: one.modelData.disabled ? grc.g.toggleLevel(one.modelData.i) : grc.g.toLevel(one.modelData.i)
                        }
                        Row {   // the two small keys on hover
                            id: keys
                            x: lbl.x + lbl.implicitWidth + 6; anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            opacity: chip.hov ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: 120 } }
                            Rectangle {
                                width: 18; height: 18; radius: 9
                                color: xh.hovered ? Qt.rgba(1, 1, 1, 0.18) : "transparent"
                                Text { anchors.centerIn: parent; text: "×"; color: T.text2; font.pixelSize: 13; font.bold: true }
                                HoverHandler { id: xh; cursorShape: Qt.PointingHandCursor
                                    onHoveredChanged: hovered ? grc.tipAt(this.parent, shell.text("Remove only this level"))
                                                              : shell.tip("", 0, 0) }
                                TapHandler { onTapped: { shell.tip("", 0, 0); grc.g.removeLevel(one.modelData.i) } }
                            }
                            Rectangle {
                                width: dt.implicitWidth + 12; height: 18; radius: 9
                                color: dh.hovered ? Qt.rgba(1, 1, 1, 0.18) : "transparent"
                                border.width: 1; border.color: T.line2
                                Text { id: dt; anchors.centerIn: parent; font.family: T.font; font.pixelSize: 11
                                       text: one.modelData.disabled ? shell.text("Enable") : shell.text("Disable")
                                       color: T.text2 }
                                HoverHandler { id: dh; cursorShape: Qt.PointingHandCursor
                                    onHoveredChanged: hovered ? grc.tipAt(this.parent, one.modelData.disabled
                                                                         ? shell.text("Turn this level on again")
                                                                         : shell.text("Turn this level off – it stays in the path"))
                                                              : shell.tip("", 0, 0) }
                                TapHandler { onTapped: { shell.tip("", 0, 0); grc.g.toggleLevel(one.modelData.i) } }
                            }
                        }
                    }
                }
            }
        }
    }
    function tipAt(item, text) {
        var q = item.mapToItem(null, item.width / 2, item.height + 4)
        shell.tip(text, q.x, q.y)
    }
}
