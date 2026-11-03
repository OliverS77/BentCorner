// Selection as a list (export of lists and decks): a checkmark in front, clicking the row expands it and shows
// what's inside – like the price alarm rows. Top: search (7+ entries), All/None. Data from qform.checklist.
import QtQuick

Column {
    id: cl
    property var items: []          // [{id, name, sub, img, on, open, lines: [{text, sub}]}]
    property string placeholder: ""
    property real maxH: 420
    signal toggled(string id, bool on)
    signal setAll(bool on)
    signal expand(string id)
    spacing: 8
    property string q: ""
    readonly property var shown: {
        var t = q.trim().toLowerCase(), out = []
        for (var i = 0; i < items.length; i++)
            if (t === "" || (items[i].name + " " + (items[i].sub || "")).toLowerCase().indexOf(t) >= 0) out.push(items[i])
        return out
    }
    readonly property bool allOn: {
        if (!items.length) return false
        for (var i = 0; i < items.length; i++) if (!items[i].on) return false
        return true
    }
    Row {
        width: cl.width; spacing: 10
        SearchField {
            visible: cl.items.length >= 7
            width: Math.min(360, cl.width - allB.width - 10); height: 32
            placeholder: cl.placeholder
            text: cl.q
            onEdited: function (t) { cl.q = t }
        }
        Btn { id: allB; height: 32; compact: true; width: implicitWidth + 12
              text: cl.allOn ? shell.text("Keine") : shell.text("Alle")
              onClicked: cl.setAll(!cl.allOn) }
    }
    Rectangle {
        width: cl.width
        height: Math.min(cl.maxH, lv.contentHeight + 12)
        radius: 12
        color: Qt.darker(T.surface, 1.1)
        border.width: 1; border.color: T.line
        ListView {
            id: lv
            ScrollHint {}
            EdgeFade { color: Qt.darker(T.surface, 1.1) }
            x: 6; y: 6; width: parent.width - 12; height: parent.height - 12
            clip: true; boundsBehavior: Flickable.StopAtBounds
            spacing: 2
            model: cl.shown
            delegate: Rectangle {
                id: row
                required property var modelData
                readonly property bool open: modelData.open === true
                readonly property var lines: modelData.lines || []
                width: lv.width
                height: 46 + (open ? box.height + 8 : 0)
                radius: 10
                color: open ? Qt.lighter(T.surface, 1.25) : (rh.hovered ? T.surface2 : "transparent")
                border.width: open ? 1 : 0; border.color: T.line2
                Behavior on color { ColorAnimation { duration: 200 } }
                HoverHandler { id: rh; cursorShape: Qt.PointingHandCursor }
                TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds
                             onTapped: function (ev) { if (ev.position.y <= 46 && ev.position.x > 40) cl.expand(row.modelData.id) } }   // not on the check
                CheckBox {
                    x: 10; y: 13
                    checked: row.modelData.on === true
                    onToggled: function (v) { cl.toggled(row.modelData.id, v) }
                }
                Image {
                    id: thumb
                    visible: (row.modelData.img || "") !== ""
                    x: 42; y: 5; height: 36; width: 36 * 63 / 88
                    source: row.modelData.img || ""; sourceSize.height: 88; asynchronous: true; smooth: true
                }
                NoImage { anchors.fill: thumb; thumb: true; visible: thumb.visible && thumb.status === Image.Error }
                Text {
                    x: thumb.visible ? 74 : 42; y: 0; height: 46
                    width: row.width - x - subT.width - 46
                    verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                    text: row.modelData.name || ""
                    color: row.modelData.on ? T.text : T.text2
                    font.family: T.font; font.pixelSize: 14; font.bold: true
                }
                Text {
                    id: subT
                    anchors.right: chev.left; anchors.rightMargin: 10; y: 0; height: 46
                    verticalAlignment: Text.AlignVCenter
                    text: row.modelData.sub || ""
                    color: T.muted; font.family: T.font; font.pixelSize: 12
                }
                Text {
                    id: chev
                    anchors.right: parent.right; anchors.rightMargin: 14; y: 0; height: 46
                    verticalAlignment: Text.AlignVCenter
                    text: row.open ? "▾" : "▸"
                    color: rh.hovered ? T.text : T.dim; font.pixelSize: 13
                }
                Column {   // expanded: what's inside
                    id: box
                    visible: row.open
                    x: 42; y: 46; width: row.width - 56
                    spacing: 3
                    Text { visible: row.lines.length === 0; text: shell.text("empty"); color: T.dim; font.family: T.font; font.pixelSize: 12 }
                    Repeater {
                        model: row.open ? row.lines : []
                        Item {
                            required property var modelData
                            width: box.width; height: 20
                            Text { width: parent.width - st.width - 10; elide: Text.ElideRight
                                   text: modelData.text || ""; color: T.text2; font.family: T.font; font.pixelSize: 12 }
                            Text { id: st; anchors.right: parent.right; text: modelData.sub || ""
                                   color: T.dim; font.family: T.font; font.pixelSize: 12 }
                        }
                    }
                }
            }
        }
    }
}
