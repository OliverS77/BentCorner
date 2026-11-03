// Compare decks: A on the left, B on the right (switch at the top), in the middle assessment, strength comparison
// and properties as bars. Bright = only in this deck. Logic: cv (qdeckmore.CompareBackend).
import QtQuick

Item {
    id: root
    property var cv
    readonly property color colA: T.hi
    readonly property color colB: "#9a9a9a"

    Row {
        id: head
        x: 20; y: 12; spacing: 14
        Btn { height: 38; width: 150; backDir: -1; text: shell.text("All decks"); onClicked: cv.back() }
        Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Compare decks")
               color: T.text; font.family: T.font; font.pixelSize: 22; font.bold: true }
        Text { anchors.verticalCenter: parent.verticalCenter
               text: shell.text("One deck on each side – switch at the top. Bright: only in this deck.")
               color: T.dim; font.family: T.font; font.pixelSize: 13 }
    }

    component Side: Rectangle {
        id: side
        property string which
        property string label
        property color col
        property var rows: []
        property string info
        radius: 14
        color: Qt.darker(T.surface, 1.1)
        border.width: 1; border.color: Qt.rgba(col.r, col.g, col.b, 0.55)
        Item {
            id: sh
            x: 12; y: 10; width: side.width - 24; height: 36
            Text { id: tag; anchors.verticalCenter: parent.verticalCenter; text: side.label; color: side.col
                   font.family: T.font; font.pixelSize: 22; font.bold: true }
            DropList {
                x: tag.width + 12; width: parent.width - x - openB.width - 10; height: 36
                items: root.cv.decks
                current: side.which === "a" ? root.cv.a : root.cv.b
                onPicked: function (k) { root.cv.pick(side.which, k) }
            }
            Btn { id: openB; anchors.right: parent.right; height: 34; compact: true; text: shell.text("Open in editor")
                  onClicked: root.cv.openEditor(side.which) }
        }
        Text { id: inf; x: 14; y: sh.y + sh.height + 8; width: side.width - 28; wrapMode: Text.Wrap
               text: side.info; textFormat: Text.StyledText; color: T.text2; font.family: T.font; font.pixelSize: 13 }
        ListView {
            ScrollHint {}
            x: 8; y: inf.y + inf.height + 10
            width: side.width - 16; height: side.height - y - 8
            clip: true; boundsBehavior: Flickable.StopAtBounds
            model: side.rows
            delegate: Item {
                id: cr
                required property var modelData
                width: ListView.view.width; height: modelData.head ? 32 : 26
                Text { visible: cr.modelData.head; x: 6; anchors.verticalCenter: parent.verticalCenter; text: cr.modelData.name
                       color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true }
                Text { visible: !cr.modelData.head; x: 2; width: 30; anchors.verticalCenter: parent.verticalCenter
                       horizontalAlignment: Text.AlignRight; text: cr.modelData.count
                       color: T.muted; font.family: T.font; font.pixelSize: 13 }
                Text { visible: !cr.modelData.head; x: 42; width: parent.width - 42 - 80; anchors.verticalCenter: parent.verticalCenter
                       elide: Text.ElideRight; text: cr.modelData.name
                       color: cr.modelData.kind === "only" ? side.col : (cr.modelData.kind === "diff" ? T.text : T.dim)
                       font.family: T.font; font.pixelSize: 13; font.bold: cr.modelData.kind === "only" }
                Text { visible: !cr.modelData.head; anchors.right: parent.right; anchors.rightMargin: 6
                       anchors.verticalCenter: parent.verticalCenter; text: cr.modelData.price
                       color: T.muted; font.family: T.font; font.pixelSize: 12 }
                HoverHandler { enabled: cr.modelData.tip !== ""
                    onHoveredChanged: if (hovered) { var p = cr.mapToItem(null, cr.width / 2, cr.height); shell.tip(cr.modelData.tip, p.x, p.y) } else shell.tip("", 0, 0) }
            }
        }
    }

    component Bars: Column {
        id: bars
        property var rows: []
        spacing: 10
        Repeater {
            model: bars.rows
            delegate: Item {
                id: br
                required property var modelData
                width: bars.width; height: 32
                readonly property real half: width / 2 - 80
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: br.modelData.label
                       color: T.text2; font.family: T.font; font.pixelSize: 12; font.bold: true }
                Text { y: 12; width: 74; text: br.modelData.ta; color: root.colA; opacity: br.modelData.sa ? 1 : 0.55
                       font.family: T.font; font.pixelSize: 14; font.bold: true }
                Text { y: 12; x: parent.width - 74; width: 74; horizontalAlignment: Text.AlignRight; text: br.modelData.tb
                       color: root.colB; opacity: br.modelData.sb ? 1 : 0.55; font.family: T.font; font.pixelSize: 14; font.bold: true }
                Rectangle { y: 18; height: 10; radius: 5; width: br.half * br.modelData.fa * 0.9; x: br.width / 2 - width
                            color: root.colA; opacity: br.modelData.sa ? 0.9 : 0.35
                            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } } }
                Rectangle { y: 18; height: 10; radius: 5; width: br.half * br.modelData.fb * 0.9; x: br.width / 2
                            color: root.colB; opacity: br.modelData.sb ? 0.9 : 0.35
                            Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } } }
            }
        }
    }

    Item {
        id: body
        x: 20; y: head.y + head.height + 14
        width: root.width - 40; height: root.height - y - 12
        readonly property real sideW: (width - 28) * 5 / 14
        Side { width: body.sideW; height: body.height; which: "a"; label: "A"; col: root.colA; rows: root.cv.rowsA; info: root.cv.infoA }
        Flickable {
            ScrollHint {}
            x: body.sideW + 14; width: body.width - 2 * body.sideW - 28; height: body.height
            contentHeight: mid.implicitHeight + 10
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: mid
                width: parent.width - 8; x: 4
                spacing: 12
                Rectangle {
                    width: parent.width; height: verdictT.implicitHeight + 24; radius: 14
                    color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
                    Text { id: verdictT; x: 12; y: 12; width: parent.width - 24; horizontalAlignment: Text.AlignHCenter
                           text: root.cv.verdict; textFormat: Text.RichText; wrapMode: Text.Wrap
                           color: T.text; font.family: T.font; font.pixelSize: 14 }
                }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: shell.text("Strength comparison (estimate)")
                       color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true }
                Bars { width: parent.width; rows: root.cv.power }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: shell.text("Properties")
                       color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true }
                Bars { width: parent.width; rows: root.cv.stats }
                Text { width: parent.width; wrapMode: Text.Wrap; text: root.cv.note; color: T.dim; font.family: T.font; font.pixelSize: 12 }
            }
        }
        Side { x: body.width - body.sideW; width: body.sideW; height: body.height; which: "b"; label: "B"; col: root.colB
               rows: root.cv.rowsB; info: root.cv.infoB }
    }
}
