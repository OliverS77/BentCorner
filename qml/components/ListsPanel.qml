// Lists on the left of the Library: wish, trade and own lists. Click a list = Library shows only its
// cards (again = all again); ▸ expands the list's cards (−/+/✕ on hover); „⋯“ = menu
// (rename, copy, move, merge, clear, delete). Cards from the grid can be dragged onto a
// list. lib = qlibrary.LibraryBackend.
import QtQuick

Rectangle {
    id: p
    property var lib
    property string dropKey: ""           // list under the dragged card („kind|id“)
    property bool pickable: true          // click = Library shows only this list (off: click expands it)
    property string hintText: ""   // (used to be a usage hint – explains itself on the first click)
    property string q: ""                 // search for lists
    property real askClosedAt: 0
    // search: section headers stay, lists by name, expanded cards only under matching lists
    property string freshId: ""          // the list just created (grows in once)
    property string askKind: ""          // „+ New list“: name field expands in this section
    property string renameKey: ""        // „kind|id“ of the list whose name is a field right now (menu → Rename)
    Connections {
        target: p.lib
        function onRenameAsked(kind, lid) {
            var b = p.lib.listBar   // the picked list: renamed in its tool row above the grid
            if (p.pickable && b && b.kind === kind && b.lid === lid) return
            p.renameKey = kind + "|" + lid
        }
    }
    readonly property var shown: {
        var all = p.lib ? p.lib.lists : [], t = q.toLowerCase().trim()
        if (p.askKind !== "") {
            // at the very top of the section (above the default list too) – exactly where the new list will appear
            var withAsk = []
            for (var j = 0; j < all.length; j++) {
                withAsk.push(all[j])
                if (all[j].head && all[j].kind === p.askKind)
                    withAsk.push({"ask": true, "kind": p.askKind, "name": all[j].name || ""})
            }
            all = withAsk
        }
        if (!t) return all
        var out = [], keep = false
        for (var i = 0; i < all.length; i++) {
            var r = all[i]
            if (r.head || r.gameHead || r.ask) { out.push(r); continue }
            if (!r.entry) { keep = (r.name || "").toLowerCase().indexOf(t) >= 0; if (keep) out.push(r); continue }
            if (keep) out.push(r)
        }
        return out
    }
    signal closeRequested()
    signal menuRequested(string kind, string lid, real sx, real sy)
    radius: 14
    color: Qt.darker(T.surface, 1.1)
    border.width: 1; border.color: T.line
    clip: true

    // list under a point (scene) -> {kind, id} or null – for dropping dragged cards
    function listAt(sx, sy) {
        var q = list.mapFromItem(null, sx, sy)
        if (q.x < 0 || q.y < 0 || q.x > list.width || q.y > list.height) return null
        var it = list.itemAt(q.x, q.y + list.contentY)
        if (!it || !it.modelData || it.modelData.head || it.modelData.entry || it.modelData.gameHead || it.modelData.other
            || it.modelData.ask) return null
        return {kind: it.modelData.kind, id: it.modelData.id}
    }

    Item {
        id: top
        x: 12; y: 10; width: p.width - 24; height: 34
        Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Lists")
               color: T.text; font.family: T.font; font.pixelSize: 17; font.bold: true }
        Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
              width: 32; height: 32; compact: true; glyph: "close"; tip: shell.text("Close lists")
              onClicked: p.closeRequested() }
    }
    Text {
        id: hint
        x: 12; y: top.y + top.height + 4; width: p.width - 24
        text: p.hintText
        visible: text !== ""
        height: visible ? implicitHeight : 0
        color: T.muted; font.family: T.font; font.pixelSize: 12; wrapMode: Text.Wrap
    }
    SearchField {
        id: lq
        x: 12; y: hint.y + hint.height + 8; width: p.width - 24; height: 32
        placeholder: shell.text("Search lists …")
        onEdited: function (t) { p.q = t }
    }
    ListView {
        ScrollHint {}
        id: list
        x: 8; y: lq.y + lq.height + 8
        width: p.width - 16; height: p.height - y - 8 - (undo.visible ? undo.height + 8 : 0)
        clip: true; boundsBehavior: Flickable.StopAtBounds
        model: p.shown
        delegate: Item {
            id: row
            required property var modelData
            width: list.width
            // a list just created grows in at the top of its section (Oliver, review .90)
            readonly property bool fresh: !modelData.head && !modelData.entry && !modelData.ask && p.freshId !== ""
                                          && modelData.id === p.freshId
            property real grow: 1
            clip: grow < 1
            Component.onCompleted: if (fresh && shell.animate) { grow = 0; growIn.start() }
            NumberAnimation { id: growIn; target: row; property: "grow"; to: 1; duration: 280 * shell.speed
                              easing.type: Easing.OutCubic; onFinished: p.freshId = "" }
            height: grow * (modelData.ask ? (askL.item ? askL.item.height : 0) : (modelData.gameHead ? 52 : (modelData.head ? 40 : (modelData.entry ? 30 : 36))))
            opacity: grow
            readonly property bool dropHere: !modelData.head && !modelData.entry && !modelData.gameHead && !modelData.other
                                             && !modelData.ask
                                             && p.dropKey === modelData.kind + "|" + modelData.id

            // ---- Game: the open one on top (bright), the others collapsed and greyed out – with summary ----
            Loader {   // built only for its kind of row (a long open list: only cards, nothing else)
                active: row.modelData.gameHead === true
                anchors.fill: parent
                sourceComponent: Component {
                    Item {
                        anchors.fill: parent
                        opacity: row.modelData.current ? 1 : (gh.hovered ? 0.85 : 0.55)
                        Rectangle { anchors.fill: parent; anchors.topMargin: 6; anchors.bottomMargin: 2; radius: 9
                                    color: row.modelData.current ? "transparent" : (gh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent")
                                    border.width: row.modelData.current ? 0 : 1; border.color: T.line }
                        Chevron { visible: !row.modelData.current; x: 8; anchors.verticalCenter: parent.verticalCenter
                                  anchors.verticalCenterOffset: 2; size: 15; open: row.modelData.open === true; color: T.text2 }
                        Column {
                            x: row.modelData.current ? 6 : 30; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 2
                            width: parent.width - x - 8
                            Text { text: row.modelData.name || ""; color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true
                                   elide: Text.ElideRight; width: parent.width }
                            Row {
                                spacing: 6; width: parent.width
                                Text { id: gsum; text: row.modelData.summary || ""; color: T.muted; font.family: T.font
                                       font.pixelSize: 11; elide: Text.ElideRight
                                       width: Math.min(implicitWidth, parent.width - (galert.visible ? galert.width + 6 : 0)) }
                                Item {   // „1 alert“: bell + underlined – click jumps to Trade → Price alerts
                                    id: galert
                                    visible: (row.modelData.alerts || "") !== ""
                                    width: gaT.x + gaT.implicitWidth; height: gsum.height
                                    NavIcon { y: -3; key: "bell"; s: 0.55; color: gah.hovered ? T.text : T.text2; play: gah.hovered }
                                    Text { id: gaT; x: 15; text: row.modelData.alerts || ""; font.underline: true
                                           color: gah.hovered ? T.text : T.text2; font.family: T.font; font.pixelSize: 11 }
                                    HoverHandler { id: gah; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: p.lib.openAlarms() }
                                }
                            }
                        }
                        HoverHandler { id: gh; enabled: !row.modelData.current; cursorShape: Qt.PointingHandCursor }
                        TapHandler { enabled: !row.modelData.current; onTapped: p.lib.toggleGameLists(row.modelData.game) }
                    }
                }
            }

            // ---- List of another game: greyed out, click switches to the game and shows it ----
            Loader {   // built only for its kind of row (a long open list: only cards, nothing else)
                active: row.modelData.other === true
                anchors.fill: parent
                sourceComponent: Component {
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 2; anchors.leftMargin: 22
                        radius: 9
                        opacity: oh.hovered ? 0.9 : 0.55
                        color: oh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent"
                        NavIcon { x: 6; anchors.verticalCenter: parent.verticalCenter; s: 0.62
                                  key: row.modelData.kind === "wish" ? "star" : (row.modelData.kind === "have" ? "trade" : "bookmark")
                                  color: T.muted; play: oh.hovered }
                        Text { x: 28; anchors.verticalCenter: parent.verticalCenter; width: parent.width - x - 60; elide: Text.ElideRight
                               text: row.modelData.name || ""; color: T.text2; font.family: T.font; font.pixelSize: 14 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                               text: oh.hovered ? shell.text("open →") : (row.modelData.count === undefined ? "" : row.modelData.count)
                               color: T.muted; font.family: T.font; font.pixelSize: 12 }
                        HoverHandler { id: oh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: p.lib.openOtherList(row.modelData.game, row.modelData.kind, row.modelData.id) }
                    }
                }
            }

            // ---- Section header + „+ New list“ ----
            Loader {   // built only for its kind of row (a long open list: only cards, nothing else)
                active: row.modelData.head === true
                anchors.fill: parent
                sourceComponent: Component {
                    Item {
                        anchors.fill: parent
                        Text { x: 6; anchors.bottom: parent.bottom; anchors.bottomMargin: 7
                               text: (row.modelData.name || "").toUpperCase()
                               color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.5 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 8; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                               text: "+  " + shell.text("New list")
                               color: nh.hovered ? T.text : T.muted; font.family: T.font; font.pixelSize: 12
                               HoverHandler { id: nh; cursorShape: Qt.PointingHandCursor }
                               TapHandler { onTapped: {
                                   if (p.askKind === row.modelData.kind) { p.askKind = ""; return }
                                   if (Date.now() - p.askClosedAt < 400) return
                                   p.askKind = row.modelData.kind
                               } } }
                    }
                }
            }

            // ---- Name field of the new list (expands exactly where it will go) ----
            Loader {   // built only for its kind of row (a long open list: only cards, nothing else)
                id: askL
                active: row.modelData.ask === true
                width: parent.width
                sourceComponent: Component {
                    InlineAsk {
                        id: rowAsk
                        width: parent.width
                        property bool shared: false
                        placeholder: shell.text("Name")
                        Component.onCompleted: if (row.modelData.ask === true)
                            start("new", row.modelData.kind, shell.text("New list") + " · " + (row.modelData.name || ""), "", shell.text("Create"))
                        onAccepted: function (mode, ident, text) { var s = rowAsk.shared; p.askKind = ""; p.freshId = p.lib.newListNamed(ident, text, s) }
                        // Cancel: the same expand animation backwards – the row leaves the model only once it is closed (review .101)
                        onCanceled: p.askClosedAt = Date.now()
                        onHeightChanged: if (!open && height < 0.5 && row.modelData.ask === true && p.askKind !== "") p.askKind = ""
                        extra: Component { Column {   // (built only while open)
                            spacing: 8
                            Seg {   // default: private (own lists are always private)
                                visible: rowAsk.ident === "wish" || rowAsk.ident === "have"
                                anchors.horizontalCenter: parent.horizontalCenter
                                items: [{"key": "p", "text": shell.text("private")},
                                        {"key": "s", "text": shell.text("shared with friends"),
                                         "tip": shell.text("Friends see the list – encrypted, visible only to them")}]
                                current: rowAsk.shared ? "s" : "p"
                                onPicked: function (k) { rowAsk.shared = k === "s" }
                            }
                        } }
                        Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: T.line; visible: rowAsk.height > 1 }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line; visible: rowAsk.height > 1 }
                    }
                }
            }

            // ---- List ----
            Loader {   // built only for its kind of row (a long open list: only cards, nothing else)
                active: !row.modelData.head && !row.modelData.entry && !row.modelData.gameHead && !row.modelData.other && !row.modelData.ask
                anchors.fill: parent
                sourceComponent: Component {
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 2
                        radius: 9
                        color: row.dropHere ? T.surface2 : (row.modelData.on ? T.surface2 : (rh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent"))
                        border.width: row.modelData.on || row.dropHere ? 1 : 0
                        border.color: row.dropHere ? T.text : T.line2
                        Item {   // expand/collapse
                            id: chev
                            x: 2; width: 26; height: parent.height
                            Chevron { anchors.centerIn: parent; size: 15; open: row.modelData.open === true
                                      color: ch.hovered ? T.text : T.text2 }
                            HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: p.lib.toggleListOpen(row.modelData.kind, row.modelData.id) }
                        }
                        NavIcon { x: 26; anchors.verticalCenter: parent.verticalCenter; s: 0.62
                                  key: row.modelData.kind === "wish" ? "star" : (row.modelData.kind === "have" ? "trade" : "bookmark")
                                  color: row.modelData.on ? T.text : T.muted }
                        Row {   // right after the name – so nothing shifts when the buttons appear on hover
                            id: lchips
                            x: lname.x + lname.width + 8
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Chip { visible: row.modelData.auto === true; text: shell.text("automatic")
                                   tip: shell.text("Keeps itself up to date") }
                            Chip { visible: row.modelData.shareable === true
                                   text: row.modelData.shared ? shell.text("shared") : shell.text("private"); lit: row.modelData.shared === true
                                   tip: row.modelData.shared ? shell.text("Shared with friends – click: private")
                                                             : shell.text("Private – click: share with friends")
                                   onClicked: p.lib.setShared(row.modelData.kind, row.modelData.id, !row.modelData.shared) }
                        }
                        Text { id: lname; x: 48; anchors.verticalCenter: parent.verticalCenter
                               width: Math.min(implicitWidth, parent.width - x - lchips.width - lcount.width - 98); elide: Text.ElideRight
                               text: row.modelData.name || ""
                               color: row.modelData.on ? T.top : T.text; font.family: T.font; font.pixelSize: 14
                               font.bold: row.modelData.on === true
                               opacity: lren.visible ? 0 : 1 }
                        RenameField {   // menu → Rename: the name becomes a field right here
                            id: lren
                            readonly property bool mine: p.renameKey !== "" && p.renameKey === row.modelData.kind + "|" + row.modelData.id
                            visible: mine
                            z: 20
                            x: lname.x - 4; anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - x - 40; height: 26
                            text: row.modelData.name || ""; tip: ""
                            pixelSize: 14
                            onMineChanged: if (mine) start()
                            onEditingChanged: if (!editing && mine) p.renameKey = ""
                            commit: function (v) { return p.lib.renameListTo(row.modelData.kind, row.modelData.id, v) }
                        }
                        // the number always stays far right – the hover buttons appear before it (review .101)
                        Text { id: lcount; anchors.right: parent.right; anchors.rightMargin: 10
                               anchors.verticalCenter: parent.verticalCenter
                               text: row.modelData.count || 0; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                        HoverHandler { id: rh; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: function (ev) {
                                if (ev.position.x < chev.x + chev.width) return
                                if (p.pickable) p.lib.pickList(row.modelData.kind, row.modelData.id)
                                else p.lib.toggleListOpen(row.modelData.kind, row.modelData.id)
                            }
                        }
                        Loader {   // the hover keys: only while the mouse is on the row (a long list stays light)
                            active: rh.hovered
                            anchors.right: lcount.left; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                            sourceComponent: Row {
                                spacing: 2
                                Btn {   // open in Trade for editing
                                    width: 30; height: 26; compact: true; text: "→"; tip: shell.text("Edit in Orbit")
                                    onClicked: p.lib.editList(row.modelData.kind, row.modelData.id)
                                }
                                Btn {   // menu
                                    width: 30; height: 26; compact: true; text: "⋯"; tip: shell.text("Manage list")
                                    onClicked: { var q = mapToItem(null, 0, height + 4); p.menuRequested(row.modelData.kind, row.modelData.id, q.x, q.y) }
                                }
                            }
                        }
                    }
                }
            }

            // ---- Card of an expanded list ----
            Loader {   // built only for its kind of row (a long open list: only cards, nothing else)
                active: row.modelData.entry === true
                anchors.fill: parent
                sourceComponent: Component {
                    Item {
                        anchors.fill: parent
                        Rectangle { anchors.fill: parent; anchors.leftMargin: 26; anchors.margins: 1; radius: 7
                                    color: eh.hovered ? Qt.lighter(T.surface, 1.08) : "transparent" }
                        Text { x: 36; anchors.verticalCenter: parent.verticalCenter
                               width: ecount.x - x - (eh.hovered ? 96 : 6) - (epin.visible ? epin.width + 4 : 0); elide: Text.ElideRight
                               textFormat: Text.StyledText
                               text: (row.modelData.name || "") + "  <font color='" + T.dim + "'>" + (row.modelData.extra || "") + "</font>"
                               color: row.modelData.red ? "#ff8a95" : T.text2; font.family: T.font; font.pixelSize: 13 }
                        Text { id: ecount; anchors.right: parent.right; anchors.rightMargin: 10   // always far right (review .101)
                               anchors.verticalCenter: parent.verticalCenter
                               text: (row.modelData.count || 0) + "×"; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                        Item {   // pin right in the list (like in the Orbit tab): exactly this print ↔ any version
                            id: epin
                            visible: row.modelData.pinnable === true
                            anchors.right: ecount.left; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                            width: 24; height: 24
                            NavIcon { anchors.centerIn: parent; width: 15; height: 15; key: row.modelData.pinned ? "pinOn" : "pin"
                                      color: row.modelData.pinned ? T.hi : (eph.hovered ? "#9a9a9a" : "#5e5e5e"); play: eph.hovered }
                            HoverHandler { id: eph; cursorShape: Qt.PointingHandCursor
                                onHoveredChanged: if (hovered) {
                                    var q = parent.mapToItem(null, parent.width / 2, parent.height)
                                    shell.tip(row.modelData.pinned ? shell.text("Exactly this printing – click: any version")
                                                                   : shell.text("Any version – click: pin exactly this printing"), q.x, q.y)
                                } else shell.tip("", 0, 0) }
                            TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds
                                         onTapped: p.lib.pinEntry(row.modelData.kind, row.modelData.id, row.modelData.key) }
                        }
                        HoverHandler { id: eh; cursorShape: Qt.PointingHandCursor }
                        // click: the card in the detail view, selected in your own library if you have it (Oliver, review .90)
                        TapHandler { onTapped: p.lib.showEntry(row.modelData.kind, row.modelData.id, row.modelData.key) }
                        Loader {   // − + ✕ only while the mouse is on the card
                            active: eh.hovered
                            anchors.right: epin.visible ? epin.left : ecount.left; anchors.rightMargin: 4
                            anchors.verticalCenter: parent.verticalCenter
                            sourceComponent: Row {
                                spacing: 2
                                Btn { width: 28; height: 24; compact: true; text: "−"; tip: shell.text("One less")
                                      onClicked: p.lib.changeEntry(row.modelData.kind, row.modelData.id, row.modelData.key, -1) }
                                Btn { width: 28; height: 24; compact: true; text: "+"
                                      readonly property bool full: (row.modelData.max || 0) > 0 && row.modelData.count >= row.modelData.max
                                      enabled: !full
                                      tip: full ? shell.text("All your copies are already on the list") : shell.text("One more")
                                      onClicked: p.lib.changeEntry(row.modelData.kind, row.modelData.id, row.modelData.key, 1) }
                                Btn { width: 28; height: 24; compact: true; text: "✕"; danger: true; tip: shell.text("Remove from list")
                                      onClicked: p.lib.changeEntry(row.modelData.kind, row.modelData.id, row.modelData.key, 0) }
                            }
                        }
                    }
                }
            }
        }
    }
    // undo after copy / move / merge / clear
    Rectangle {
        id: undo
        visible: p.lib.undoText !== ""
        x: 8; width: p.width - 16; height: 40
        y: p.height - height - 8
        radius: 10; color: T.surface2; border.width: 1; border.color: T.line2
        Text { x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 130; elide: Text.ElideRight
               text: p.lib.undoText; color: T.text2; font.family: T.font; font.pixelSize: 13 }
        Btn { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
              height: 28; width: 110; compact: true; text: "↺  " + shell.text("Undo"); onClicked: p.lib.undo() }
    }
}
