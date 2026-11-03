// All prints as a strip of small cards (like libview.PrintStrip): click = compare to the left of it. Marking:
// light border = detail view, dashed light = comparison. Mouse wheel scrolls sideways.
import QtQuick
import QtQuick.Effects

ListView {
    ScrollHint {}
    EdgeFade { color: s.fadeColor }   // fade cards out softly at the edge instead of cutting them off hard
    id: s
    property var prints: []
    property color fadeColor: T.bg   // colour behind the strip
    signal picked(string id)
    orientation: ListView.Horizontal
    height: 212   // space at the bottom for the scroll bar (gap to the prices)
    spacing: 8
    clip: true
    model: prints
    boundsBehavior: Flickable.StopAtBounds
    WheelHandler { onWheel: function (ev) { s.flick(ev.angleDelta.y * 12, 0) } }
    delegate: Item {
        required property var modelData
        width: 116; height: s.height
        property real hv: h.hovered ? 1 : 0
        Behavior on hv { NumberAnimation { duration: 150 } }
        Item {
            id: card
            x: 2; y: 6 - 4 * parent.hv
            width: 112; height: 156
            Image {
                id: im
                anchors.fill: parent
                source: modelData.img
                asynchronous: true; smooth: true; mipmap: true
                sourceSize.width: 240
                fillMode: Image.PreserveAspectFit
                visible: false
            }
            MultiEffect {
                anchors.fill: im; source: im
                maskEnabled: true; maskSource: m
                visible: im.status === Image.Ready && GraphicsInfo.api !== GraphicsInfo.Software
            }
            Image {
                anchors.fill: parent; source: im.source; fillMode: Image.PreserveAspectFit
                visible: im.status === Image.Ready && GraphicsInfo.api === GraphicsInfo.Software
            }
            Item { id: m; anchors.fill: parent; layer.enabled: true; visible: false
                   Rectangle { anchors.fill: parent; radius: 6; color: "black" } }
            NoImage { anchors.fill: parent; radius: 6; thumb: true
                      visible: (modelData.img || "") === "" || im.status === Image.Error }   // set + number below
            Rectangle {   // still loading
                anchors.fill: parent; radius: 6
                visible: im.status === Image.Loading
                color: T.button; border.width: 1; border.color: T.line
                Text { anchors.centerIn: parent; text: modelData.set; color: T.dim; font.family: T.font; font.pixelSize: 12 }
            }
            Rectangle {
                anchors.fill: parent; anchors.margins: -3
                radius: 9
                visible: modelData.mark !== ""
                color: "transparent"
                border.width: 2
                border.color: modelData.mark === "main" ? T.accent : T.text2
                opacity: modelData.mark === "main" ? 1 : 0.6
            }
        }
        Text {
            y: 168; width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: modelData.set + " #" + modelData.number
            color: T.text2; font.family: T.font; font.pixelSize: 11; font.bold: true
            elide: Text.ElideRight
        }
        Text {
            y: 182; width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: modelData.price
            color: T.muted; font.family: T.font; font.pixelSize: 11
        }
        HoverHandler { id: h; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: s.picked(modelData.id) }
    }
}
