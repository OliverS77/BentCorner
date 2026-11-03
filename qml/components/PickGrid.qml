// Selection as tiles (decks, lists …): image, below it name and extra. Click = on / off – you don't go inside.
// Off = slightly dimmed, hover = almost normal, on = normal (no checkmarks: the brightness IS the indicator –
// that's how every selection in the app works). Search on top, „All“, „None“; no folders, all in one grid.
// items: [{id, name, sub, img, on}] (order comes sorted from Python); toggled(id, an); setAll(an).
import QtQuick

Item {
    id: g
    property var items: []
    property string placeholder: ""
    property real tileW: 124
    property real maxH: 360
    signal toggled(string id, bool on)
    signal setAll(bool on)
    property string q: ""
    readonly property var shown: {
        var t = q.toLowerCase().trim(), out = []
        for (var i = 0; i < items.length; i++)
            if (!t || (items[i].name + " " + (items[i].sub || "")).toLowerCase().indexOf(t) >= 0) out.push(items[i])
        return out
    }
    readonly property int nOn: { var n = 0; for (var i = 0; i < items.length; i++) if (items[i].on) n++; return n }
    implicitHeight: head.height + 10 + Math.min(maxH, flow.implicitHeight + 4)

    Row {
        id: head
        width: parent.width; spacing: 10
        SearchField {
            id: sf
            width: Math.min(360, parent.width - info.width - allBtn.width - noneBtn.width - 40); height: 32
            placeholder: g.placeholder
            onEdited: function (t) { g.q = t }
        }
        Btn { id: allBtn; height: 32; compact: true; width: implicitWidth + 16; text: shell.text("Alle")
              enabled: g.nOn < g.items.length; onClicked: g.setAll(true) }
        Btn { id: noneBtn; height: 32; compact: true; width: implicitWidth + 16; text: shell.text("Keine")
              enabled: g.nOn > 0; onClicked: g.setAll(false) }
        Text { id: info; anchors.verticalCenter: parent.verticalCenter
               text: g.nOn + " / " + g.items.length + " " + shell.text("selected")
               color: T.muted; font.family: T.font; font.pixelSize: 12 }
    }
    Flickable {
        ScrollHint {}
        y: head.height + 10
        width: parent.width; height: Math.min(g.maxH, flow.implicitHeight + 4)
        contentWidth: width; contentHeight: flow.implicitHeight; clip: true
        boundsBehavior: Flickable.StopAtBounds
        Flow {
            id: flow
            width: parent.width; spacing: 10
            Repeater {
                model: g.shown
                Item {
                    id: tl
                    required property var modelData
                    width: g.tileW; height: art.height + 40
                    readonly property bool on: modelData.on === true
                    opacity: on ? 1 : (th.hovered ? 0.92 : 0.62)
                    Behavior on opacity { NumberAnimation { duration: 160 } }
                    Rectangle {
                        id: art
                        width: parent.width; height: width * 88 / 63; radius: 7
                        color: Qt.darker(T.surface, 1.3)
                        border.width: 1; border.color: tl.on ? T.line2 : T.line
                        clip: true
                        Image {
                            anchors.fill: parent; anchors.margins: 1
                            source: tl.modelData.img || ""; visible: source !== ""
                            fillMode: Image.PreserveAspectCrop; asynchronous: true; smooth: true
                            sourceSize.width: 260
                        }
                        NavIcon { visible: !(tl.modelData.img || ""); anchors.centerIn: parent; s: 1.2
                                  key: tl.modelData.icon || "decks"; color: T.line2 }
                    }
                    Text { y: art.height + 5; width: parent.width; elide: Text.ElideRight; text: tl.modelData.name || ""
                           color: T.text; font.family: T.font; font.pixelSize: 12; font.bold: true }
                    Text { y: art.height + 21; width: parent.width; elide: Text.ElideRight; text: tl.modelData.sub || ""
                           color: T.muted; font.family: T.font; font.pixelSize: 11 }
                    HoverHandler { id: th; cursorShape: Qt.PointingHandCursor }
                    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: g.toggled(tl.modelData.id, !tl.on) }
                }
            }
        }
    }
    Text {
        visible: g.shown.length === 0
        y: head.height + 18
        text: g.items.length ? shell.text("Nothing found.") : shell.text("Nothing here yet.")
        color: T.dim; font.family: T.font; font.pixelSize: 13
    }
}
