// Binder: double page (two pages with cols × rows pockets each) to flip through – like a real collector's binder.
// Missing cards are greyed out („still missing“), empty pockets dashed. bd = qbinder.BinderBackend.
// Everything with the mouse, no menu:
//   click                    view card (detail view next to it) · empty pocket: insert card
//   drag card onto card      the two swap places
//   between two pockets      insert: the card takes the slot, everything after moves one on (gaps included)
//   drag out of the binder   remove (Ctrl+Z brings it back)
// On the right the Library (as in deck building): drag cards into a pocket or between two pockets, double click =
// next free pocket. Below the binder: flip, pages, cards, value. Grip between binder and Library: width.
import QtQuick
import "."

Item {
    id: v
    property var bd
    focus: visible
    Keys.onLeftPressed: bd.prev()
    Keys.onRightPressed: bd.next()

    // ---- Header ----
    Row {
        id: head
        x: 0; y: 0
        spacing: 10
        Btn { text: "←  " + shell.text("Back"); height: 36; width: implicitWidth; onClicked: v.bd.close() }
        RenameField {   // name – click = rename right here (review .101)
            id: bname
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, 420); height: 32
            text: v.bd.title; family: T.display; pixelSize: 22
            canEdit: !v.bd.readOnly
            commit: function (t) { return v.bd.renameTo(t) }
        }
        Btn { visible: v.bd.canEdit; glyph: "pen"; text: v.bd.editText; height: 36; width: implicitWidth
              tip: shell.text("Insert cards, move them, rename …"); onClicked: v.bd.edit() }
    }
    // „Lists“ sits left-aligned above the Library – the lists expand there, the binder stays left
    Btn { visible: !v.bd.readOnly; navIcon: "lists"; text: shell.text("Lists"); height: 36; width: implicitWidth
          x: Math.min(v.bookW + 22, tools.x - width - 10); y: 0   // narrow: to the left of the tools instead of below
          active: v.listsShown; tip: shell.text("Open your lists next to the library")
          onClicked: v.listsShown = !v.listsShown }
    Row {
        id: tools
        anchors.right: parent.right; y: 0
        spacing: 8
        SearchField {
            width: 220; height: 36
            placeholder: shell.text("Search binder …")
            onAccepted: v.bd.find(text)
            onEdited: function (t) { if (t === "") v.bd.find("") }
        }
        Btn { visible: !v.bd.readOnly; text: shell.text("Add all prints …"); height: 36
              width: implicitWidth; onClicked: v.bd.addDialog()
              tip: shell.text("All prints of a card at once – missing ones as gaps") }
        Btn { visible: !v.bd.readOnly; text: shell.text("Missing → wishlist"); height: 36; width: implicitWidth
              onClicked: v.bd.missingToWishlist() }
        Btn { visible: !v.bd.readOnly; text: shell.text("Post for friends"); height: 36; width: implicitWidth
              onClicked: v.bd.share() }
        Btn { visible: !v.bd.readOnly; glyph: "trash"; compact: true; width: 40; height: 36
              tip: shell.text("Delete binder"); onClicked: v.bd.remove() }
    }

    // ---- Lists on the left („Lists“ button): the binder moves right and gets smaller, but stays a double page ----
    property bool listsShown: false
    readonly property real listsW: listsShown && !v.bd.readOnly ? 330 : 0
    Loader {   // only once the lists are expanded (otherwise ~2,700 items for nothing)
        active: v.listsW > 0
        x: v.bookW + 22; y: head.height + 18
        width: v.listsW - 14; height: v.height - y
        sourceComponent: ListsPanel {
            lib: libraryPage
            pickable: false
            onCloseRequested: v.listsShown = false
        }
    }

    // ---- Width: binder | Library (grip in between) ----
    // Library wide enough for the advanced search to fit in three rows (chips visible, the rest scrolls)
    readonly property real libMin: 640 + listsW
    readonly property real bookMin: 480
    property real dragSplit: -1
    readonly property real bookW: v.bd.readOnly ? width
        : Math.max(bookMin, Math.min(width - libMin - 22, width * (dragSplit > 0 ? dragSplit : v.bd.split)))
    Item {
        id: grip
        visible: !v.bd.readOnly
        x: v.bookW + 4; y: head.height + 18; width: 14; height: v.height - y
        Rectangle { anchors.centerIn: parent; width: 3; height: 46; radius: 1.5
                    color: gh.hovered || gd.active ? T.text2 : T.line2 }
        HoverHandler { id: gh; cursorShape: Qt.SplitHCursor }
        DragHandler {
            id: gd
            target: null; yAxis.enabled: false
            property real startW: 0
            onActiveChanged: {
                if (active) startW = v.bookW
                else { v.bd.setSplit(v.bookW / v.width); v.dragSplit = -1 }
            }
            onTranslationChanged: if (active) v.dragSplit = (startW + translation.x) / v.width
        }
    }
    Loader {   // Library only for editing (viewing doesn't need it – otherwise ~8,000 items on every open)
        active: !v.bd.readOnly
        asynchronous: true   // builds up next to the already visible binder without the UI freezing
        x: v.bookW + 22 + v.listsW; y: head.height + 4
        width: v.width - x; height: v.height - y
        sourceComponent: libC
    }
    Component {
        id: libC
        LibraryView {
        id: libv
        lib: v.bd.libView
        pad: 6
        gridMinimum: 160
        draggable: true
        onTileDoubleClicked: function (i) { v.bd.addFromGrid(i) }
        onTileDragMoved: function (i, img, sx, sy) {
            var p = book.mapFromItem(null, sx, sy)
            book.target = book.dropAt(p.x, p.y, false)
        }
        onTileDropped: function (i, sx, sy) {
            var p = book.mapFromItem(null, sx, sy)
            var t = book.dropAt(p.x, p.y, false)
            book.target = book.none
            if (t.mode === "on") v.bd.dropFromGrid(i, t.k)
            else if (t.mode === "before") v.bd.insertFromGrid(i, t.k)
        }
        }
    }

    // ---- Double page ----
    Item {
        id: book
        x: 0; y: head.height + 18
        width: v.bookW; height: parent.height - y - foot.height - 12
        readonly property real gap: 26
        readonly property int c: Math.max(1, v.bd.cols)
        readonly property int r: Math.max(1, v.bd.rows)
        // pockets as large as possible (card format 63:88 + room for the name)
        readonly property real cellW: Math.max(60, Math.min((width - gap - 2 * 28) / (2 * c),
                                                            ((height - 30) / r - 50) * 63 / 88 + 16))
        readonly property real cellH: (cellW - 16) * 88 / 63 + 50
        readonly property real pageW: c * cellW + 28
        readonly property real pageH: r * cellH + 24
        readonly property real x0: Math.max(0, (width - 2 * pageW - gap) / 2)

        // dragging in the binder: from where, image at the mouse, target {k, mode: "on" | "before" | "out" | ""}
        readonly property var none: ({k: -1, mode: ""})
        property var target: none
        property int dragFrom: -1
        property url dragImg
        property point dragPos

        // target under a point: on a card (middle) = swap/replace, at the left/right edge of a pocket =
        // insert before/after, outside the pages = remove (only when dragging out of the binder)
        function dropAt(px, py, fromBook) {
            for (var p = 0; p < 2; p++) {
                var left = x0 + p * (pageW + gap) + 14
                if (px < left - 10 || px > left + c * cellW + 10 || py < 0 || py > pageH) continue
                var col = Math.max(0, Math.min(c - 1, Math.floor((px - left) / cellW)))
                var row = Math.max(0, Math.min(r - 1, Math.floor((py - 12) / cellH)))
                var cells = v.bd.pagesData[p]
                var k = row * c + col
                if (!cells || k >= cells.length) return none
                var idx = cells[k].index
                var fx = (px - left - col * cellW) / cellW
                if (fx < 0.2) return {k: idx, mode: "before"}
                if (fx > 0.8) return {k: idx + 1, mode: "before"}
                return {k: idx, mode: "on"}
            }
            if (fromBook && (px < -10 || px > width + 10 || py < -10 || py > height + 10 || py > pageH + 10))
                return {k: -1, mode: "out"}
            return none
        }

        Repeater {
            model: v.bd.pagesData
            delegate: Rectangle {
                id: pg
                required property var modelData
                required property int index
                x: book.x0 + index * (book.pageW + book.gap); y: 0
                width: book.pageW; height: book.pageH
                radius: 14
                color: T.surface; border.width: 1; border.color: T.line
                Grid {
                    x: 14; y: 12
                    columns: book.c
                    Repeater {
                        model: pg.modelData
                        delegate: Item {
                            id: cell
                            required property var modelData
                            width: book.cellW; height: book.cellH
                            readonly property bool isTarget: book.target.mode === "on" && book.target.k === cell.modelData.index
                            readonly property bool lifted: book.dragFrom === cell.modelData.index
                            // empty pocket: dashed outline
                            Rectangle {
                                visible: cell.modelData.empty
                                x: 8; y: 4; width: parent.width - 16; height: (parent.width - 16) * 88 / 63
                                radius: 8; color: cell.isTarget ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
                                border.width: 1; border.color: cell.modelData.hl || cell.isTarget ? T.text : T.line2
                                Text { anchors.centerIn: parent; text: "+"; color: T.dim; font.pixelSize: 22
                                       visible: !v.bd.readOnly }
                            }
                            CardTile {
                                visible: !cell.modelData.empty
                                anchors.fill: parent
                                name: cell.modelData.name
                                setLine: cell.modelData.have ? cell.modelData.setLine
                                                             : shell.text("fehlt noch") + " · " + cell.modelData.setLine
                                img: cell.modelData.img
                                dim: !cell.modelData.have
                                selected: cell.modelData.hl || cell.isTarget
                                calm: true
                                // still missing: clearly paler; lifted (being dragged): only a shadow left
                                opacity: cell.lifted ? 0.18 : (cell.modelData.have ? 1 : 0.32)
                                Behavior on opacity { NumberAnimation { duration: 140 } }
                            }
                            // insertion line left of the pocket
                            Rectangle {
                                visible: book.target.mode === "before" && book.target.k === cell.modelData.index
                                x: 1; y: 6; width: 3; radius: 1.5; height: (parent.width - 16) * 88 / 63 - 4
                                color: T.text
                            }
                            // … or right of the last pocket in a row
                            Rectangle {
                                visible: book.target.mode === "before" && book.target.k === cell.modelData.index + 1
                                         && (cell.modelData.index % book.c) === book.c - 1
                                x: parent.width - 4; y: 6; width: 3; radius: 1.5; height: (parent.width - 16) * 88 / 63 - 4
                                color: T.text
                            }
                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: book.dragFrom >= 0 ? Qt.ClosedHandCursor
                                             : (cell.modelData.empty ? Qt.ArrowCursor : Qt.PointingHandCursor)
                                property point p0
                                property bool moved: false
                                onPressed: function (m) { p0 = Qt.point(m.x, m.y); moved = false }
                                onPositionChanged: function (m) {
                                    if (!pressed) return
                                    var g = mapToItem(book, m.x, m.y)
                                    if (!moved && !v.bd.readOnly && !cell.modelData.empty
                                            && Math.abs(m.x - p0.x) + Math.abs(m.y - p0.y) > 8) {
                                        moved = true
                                        book.dragFrom = cell.modelData.index
                                        book.dragImg = cell.modelData.img
                                    }
                                    if (moved) {
                                        book.dragPos = g
                                        book.target = book.dropAt(g.x, g.y, true)
                                    }
                                }
                                onReleased: function (m) {
                                    if (moved && book.dragFrom >= 0) {
                                        var t = book.target, from = book.dragFrom
                                        book.dragFrom = -1; book.target = book.none
                                        if (t.mode === "on" && t.k !== from) v.bd.moveSlot(from, t.k)
                                        else if (t.mode === "before") v.bd.insertSlot(from, t.k)
                                        else if (t.mode === "out") v.bd.takeOut(from)
                                    } else if (!moved) {
                                        v.bd.click(cell.modelData.index)
                                    }
                                }
                                onCanceled: { book.dragFrom = -1; book.target = book.none }
                            }
                        }
                    }
                }
            }
        }
        // the dragged card sticks to the mouse (slightly tilted and lifted)
        Item {
            id: ghost
            visible: book.dragFrom >= 0
            z: 50
            width: book.cellW - 16; height: width * 88 / 63
            x: book.dragPos.x - width / 2; y: book.dragPos.y - height * 0.4
            rotation: book.target.mode === "out" ? -8 : 3
            scale: 1.06
            opacity: book.target.mode === "out" ? 0.55 : 0.95
            Behavior on rotation { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
            Behavior on opacity { NumberAnimation { duration: 160 } }
            Rectangle { anchors.fill: parent; anchors.margins: -1; radius: width * 0.055 + 1; color: "#000000"
                        opacity: 0.45; x: 6; y: 8 }
            Image {
                anchors.fill: parent; source: book.dragImg; fillMode: Image.PreserveAspectCrop
                asynchronous: true; smooth: true; mipmap: true
            }
            Text {
                visible: book.target.mode === "out"
                anchors.horizontalCenter: parent.horizontalCenter; y: parent.height + 8
                text: shell.text("release = take out"); color: T.text2
                font.family: T.font; font.pixelSize: 12
            }
        }
    }

    // ---- below the binder: flip and info ----
    Item {
        id: foot
        x: 0; width: v.bookW; height: 48
        y: book.y + Math.min(book.height, book.pageH) + 14
        readonly property var st: v.bd.stats || {}
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 14
            Btn { width: 44; height: 40; text: "‹"; enabled: v.bd.canPrev; onClicked: v.bd.prev()
                  tip: shell.text("Previous pages (←)") }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                width: 150
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; text: foot.st.page || ""
                       color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                       text: [foot.st.cards, foot.st.have].filter(function (x) { return !!x }).join("  ·  ")
                       color: T.muted; font.family: T.font; font.pixelSize: 12 }
            }
            Btn { width: 44; height: 40; text: "›"; enabled: v.bd.canNext; onClicked: v.bd.next()
                  tip: shell.text("Next pages (→) – at the end an empty spread is added") }
            Rectangle { width: 1; height: 30; color: T.line; anchors.verticalCenter: parent.verticalCenter }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Text { text: shell.text("Value") + "  " + (foot.st.value || "–"); color: T.text
                       font.family: T.font; font.pixelSize: 13; font.bold: true }
                Text { text: shell.text("owned") + "  " + (foot.st.haveValue || "–")
                             + (foot.st.missing ? "  ·  " + foot.st.missing : "")
                       color: T.muted; font.family: T.font; font.pixelSize: 12 }
            }
        }
    }
}
