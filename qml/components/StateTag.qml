// Selected entry as a tag (like libview.StateTag): click switches ✓ must ↔ ✕ exclude, small ✕ removes.
import QtQuick

Rectangle {
    id: t
    property string name
    property int state: 1
    property bool toggleable: true
    signal toggled()
    signal removed()
    readonly property bool inc: state === 1
    height: 24
    width: row.implicitWidth + 12
    radius: 12
    color: inc ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0.85, 0.3, 0.35, 0.16)
    border.width: 1
    border.color: inc ? T.line2 : "#a0505a"
    Row {
        id: row
        x: 8; anchors.verticalCenter: parent.verticalCenter
        spacing: 4
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: (t.toggleable ? (t.inc ? "✓ " : "✕ ") : "") + t.name
            color: t.inc ? T.text : "#ff9aa4"
            font.family: T.font; font.pixelSize: 12; font.bold: true
            font.strikeout: !t.inc
            HoverHandler { cursorShape: t.toggleable ? Qt.PointingHandCursor : Qt.ArrowCursor }
            TapHandler { enabled: t.toggleable; onTapped: t.toggled() }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "✕"
            color: xh.hovered ? T.text : T.muted
            font.pixelSize: 11
            HoverHandler { id: xh; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: t.removed() }
        }
    }
}
