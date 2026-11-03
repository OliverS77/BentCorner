// One column in the „Trade“ tab (tradelib.CardBrowser): search, grid/list, filter chips, total, all on/off and
// the cards with checkmarks. br: qtrade.BrowserBackend. No frame of its own (content next to the rail).
import QtQuick

Rectangle {
    id: box
    property var br
    property int cols: 3
    signal cardClicked(int i)
    color: "transparent"

    Text {
        id: title
        x: 14; y: 12
        text: box.br.title
        color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true
    }
    Item {
        id: top
        x: 12; y: title.y + title.height + 10
        width: box.width - 24; height: 34
        SearchField {
            width: parent.width - 2 * 44 - 12; height: 34
            placeholder: shell.text("Search (name, set) …")
            text: box.br.search
            onEdited: function (t) { box.br.setSearch(t) }
        }
        Btn { x: parent.width - 86; width: 40; height: 34; compact: true; glyph: "library"
              checkable: true; checked: box.br.mode === "grid"; tip: shell.text("As a grid with images")
              onClicked: box.br.setMode("grid") }
        Btn { x: parent.width - 40; width: 40; height: 34; compact: true; text: "☰"
              checkable: true; checked: box.br.mode === "list"; tip: shell.text("As list")
              onClicked: box.br.setMode("list") }
    }
    Flow {
        id: chips
        x: 12; width: box.width - 24
        anchors.top: top.bottom; anchors.topMargin: box.br.filters.length ? 8 : 0
        height: box.br.filters.length ? implicitHeight : 0
        spacing: 6
        Repeater {
            model: box.br.filters
            delegate: Rectangle {
                required property var modelData
                height: 28; radius: 14
                width: ct.implicitWidth + (modelData.pin ? 44 : 28)
                color: modelData.on ? "#d9d9d9" : (ch.hovered ? T.surface2 : T.surface)
                border.width: 1; border.color: modelData.on ? "#d9d9d9" : (ch.hovered ? T.text2 : T.line2)
                NavIcon { visible: modelData.pin; x: 12; anchors.verticalCenter: parent.verticalCenter
                          width: 14; height: 14; key: "pinOn"; color: modelData.on ? T.onHi : T.text2 }
                Text { id: ct; x: modelData.pin ? 30 : 14; anchors.verticalCenter: parent.verticalCenter
                       text: modelData.text; color: modelData.on ? T.onHi : T.text2
                       font.family: T.font; font.pixelSize: 13; font.bold: true }
                HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: box.br.toggleFilter(modelData.key) }
            }
        }
    }
    Item {
        id: infoRow
        x: 12; width: box.width - 24; height: 32
        anchors.top: chips.bottom; anchors.topMargin: 8
        Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - (box.br.checkable ? 190 : 0)
               text: box.br.info; elide: Text.ElideRight; color: T.muted; font.family: T.font; font.pixelSize: 13 }
        Row {
            visible: box.br.checkable
            anchors.right: parent.right; spacing: 6
            Btn { width: 88; height: 30; compact: true; text: shell.text("Alle an"); onClicked: box.br.checkAll(true) }
            Btn { width: 88; height: 30; compact: true; text: shell.text("Alle ab"); onClicked: box.br.checkAll(false) }
        }
    }
    Item {
        id: content
        x: 6; width: box.width - 12
        anchors.top: infoRow.bottom; anchors.topMargin: 6
        anchors.bottom: parent.bottom; anchors.bottomMargin: 8
        Text {
            anchors.centerIn: parent; width: parent.width - 60
            visible: box.br.emptyText !== ""
            text: box.br.emptyText
            wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
            color: T.dim; font.family: T.font; font.pixelSize: 15
        }
        GridView {
            ScrollHint {}
            id: grid
            anchors.fill: parent
            visible: box.br.mode === "grid" && box.br.emptyText === ""
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: box.br.rows
            cellWidth: Math.floor((width - 8) / Math.max(1, box.cols))
            readonly property real cw: cellWidth - 16
            readonly property int npx: Math.max(10, Math.min(15, Math.round(cw / 13)))
            cellHeight: Math.round(cw * 88 / 63) + Math.round(npx * 2.8) + 14
            delegate: CardTile {
                required property var modelData
                width: grid.cellWidth; height: grid.cellHeight
                name: modelData.name
                price: modelData.price
                setLine: modelData.setLine + (modelData.tags ? " · " + modelData.tags : "")
                chips: modelData.chips
                img: modelData.img
                checkable: box.br.checkable
                calm: true
                checked: modelData.checked
                dim: box.br.checkable && !modelData.checked
                onClicked: box.cardClicked(modelData.i)
                onCheckToggled: box.br.toggle(modelData.i)
            }
        }
        ListView {
            ScrollHint {}
            id: list
            anchors.fill: parent
            visible: box.br.mode === "list" && box.br.emptyText === ""
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: box.br.rows
            delegate: Rectangle {
                id: lr
                required property var modelData
                width: list.width; height: 40
                radius: 8
                color: lh.hovered ? T.surface2 : "transparent"
                readonly property color ink: box.br.checkable && !modelData.checked ? T.dim : T.text
                Rectangle {
                    visible: box.br.checkable
                    x: 8; anchors.verticalCenter: parent.verticalCenter
                    width: 20; height: 20; radius: 5
                    color: lr.modelData.checked ? T.hi : "transparent"
                    border.width: 1.5; border.color: lr.modelData.checked ? T.hi : T.line2
                    Text { anchors.centerIn: parent; text: "✓"; visible: lr.modelData.checked; color: T.onHi
                           font.pixelSize: 13; font.bold: true }
                    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: box.br.toggle(lr.modelData.i) }
                }
                Text { x: box.br.checkable ? 38 : 10; anchors.verticalCenter: parent.verticalCenter
                       width: parent.width * 0.42; elide: Text.ElideRight
                       text: lr.modelData.count + "×  " + lr.modelData.name; color: lr.ink
                       font.family: T.font; font.pixelSize: 14; font.bold: true }
                Text { x: parent.width * 0.48; anchors.verticalCenter: parent.verticalCenter
                       width: parent.width * 0.34; elide: Text.ElideRight
                       text: lr.modelData.setLine + (lr.modelData.tags ? " · " + lr.modelData.tags : "")
                       color: T.muted; font.family: T.font; font.pixelSize: 13 }
                Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                       text: lr.modelData.price; color: lr.ink; font.family: T.font; font.pixelSize: 13 }
                HoverHandler { id: lh; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: box.cardClicked(lr.modelData.i) }
            }
        }
    }
}
