// List for choice fields, menus and suggestions of the old widgets (qpopups.Popups) – inside the window instead of
// a separate small window. Click outside or Esc closes.
import QtQuick

Item {
    id: popLayer   // not „layer“ (built-in Item property shadows the id)
    property var pops
    anchors.fill: parent
    visible: pops && pops.items.length > 0

    MouseArea {   // click outside closes
        anchors.fill: parent
        preventStealing: true
        onPressed: function (m) { popLayer.pops.close() }
    }
    Rectangle {
        id: list
        readonly property real wantH: Math.min(col.implicitHeight + 10, popLayer.height * 0.6)
        x: Math.max(6, Math.min(popLayer.width - width - 6, popLayer.pops ? popLayer.pops.px : 0))
        y: popLayer.pops && popLayer.pops.py + wantH > popLayer.height - 6 ? Math.max(6, popLayer.pops.py - wantH - 40) : (popLayer.pops ? popLayer.pops.py : 0)
        width: Math.max(popLayer.pops ? popLayer.pops.pw : 200, 220)
        height: wantH
        radius: 10
        color: T.surface2
        border.width: 1; border.color: T.line2
        clip: true
        scale: popLayer.visible ? 1 : 0.96
        Behavior on scale { NumberAnimation { duration: 120 } }
        Flickable {
            ScrollHint {}
            anchors.fill: parent; anchors.margins: 5
            contentHeight: col.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: col
                width: parent.width
                Repeater {
                    model: popLayer.pops ? popLayer.pops.items : []
                    delegate: Item {
                        required property var modelData
                        required property int index
                        width: col.width
                        height: modelData.sep ? 9 : 30
                        Rectangle { visible: modelData.sep === true; anchors.centerIn: parent; width: parent.width - 12; height: 1; color: T.line }
                        Rectangle {
                            visible: !modelData.sep
                            anchors.fill: parent; radius: 7
                            color: h.hovered && modelData.enabled ? T.button : "transparent"
                        }
                        Text {
                            id: t
                            visible: !modelData.sep
                            x: 12; anchors.verticalCenter: parent.verticalCenter
                            text: (modelData.on ? "✓  " : "") + modelData.text
                            color: modelData.enabled ? (modelData.on ? T.text : T.text2) : T.dim
                            font.family: T.font; font.pixelSize: 13; font.bold: modelData.on
                        }
                        HoverHandler { id: h; cursorShape: modelData.enabled && !modelData.sep ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        TapHandler { enabled: modelData.enabled && !modelData.sep; grabPermissions: PointerHandler.TakeOverForbidden
                                     onTapped: popLayer.pops.pick(index) }
                    }
                }
            }
        }
    }
    Keys.onEscapePressed: pops.close()
}
