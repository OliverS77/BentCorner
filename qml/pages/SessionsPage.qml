// Sessions: on the left the table (selectable columns) with the buttons below, centre „Edit session“, overview and
// the packs with their cards, right the detail view of a card or „Change card“. Logic: sessionsPage (qsessions.py).
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var sp: sessionsPage
    onVisibleChanged: sp.setActive(visible)
    Component.onCompleted: sp.setActive(visible)

    SessionsHead {   // the "Sessions" tab: List | Stats
        id: head
        x: 22; y: 12; width: page.width - 42
        view: "sessions"
        sub: shell.text("View and edit past logs")
    }

    Item {
        id: area
        x: 20; y: head.y + head.height + 12
        width: page.width - 40; height: page.height - y - 14
        property real dragW: -1
        readonly property bool rightOpen: sp.detailOpen || sp.editOpen
        readonly property real panelW: Math.max(380, Math.min(dragW > 0 ? dragW : sp.panelWidth, (width - 700) / (sp.compareOpen ? 2 : 1)))
        property real detW: rightOpen ? (sp.editOpen ? Math.max(panelW, 460) : panelW) : 0
        property real cmpW: sp.compareOpen && !sp.editOpen ? panelW : 0
        Behavior on detW { enabled: shell.animate && area.dragW < 0; NumberAnimation { duration: 320 * shell.speed; easing.type: Easing.InOutCubic } }
        Behavior on cmpW { enabled: shell.animate && area.dragW < 0; NumberAnimation { duration: 320 * shell.speed; easing.type: Easing.InOutCubic } }
        readonly property real mainW: width - detW - cmpW - (detW > 1 ? 16 : 0) - (cmpW > 1 ? 14 : 0)
        // no log chosen: the table takes the whole width (on the right there would only be "Pick a log …"); one chosen:
        // the table's share of it (the divider between them can be dragged)
        property real shareDrag: -1
        readonly property real share: shareDrag > 0 ? shareDrag : page.sp.tableShare
        property real leftW: page.sp.hasSelection ? Math.round((mainW - 16) * share) : mainW
        Behavior on leftW { enabled: shell.animate && area.shareDrag < 0 && area.dragW < 0
                            NumberAnimation { duration: 260 * shell.speed; easing.type: Easing.InOutCubic } }

        // ================= left: table =================
        Item {
            id: left
            width: area.leftW; height: area.height
            // top (review .101): only "New log" and "Import/Export", next to them the advanced log search (expands: jump
            // into a part – cards, boosters, trades …, the trash); on the right ☰ for the columns
            Row {
                id: topRow
                spacing: 8
                Btn { height: 32; compact: true; primary: !page.sp.sessionActive
                      text: page.sp.sessionActive ? shell.text("End log") : shell.text("New log …")
                      tip: page.sp.sessionActive ? shell.text("End the running log (cards to collection, save …)")
                                                 : shell.text("Start a new log: game, open packs, singles, trade or trade ticket")
                      onClicked: page.sp.newSession() }
                Btn { height: 32; compact: true; navIcon: "import"; text: shell.text("Import/Export")
                      tip: shell.text("Import a collection (CSV from ManaBox, Moxfield & co.) – shows up here as an import")
                      onClicked: page.sp.importCards() }
                Btn { id: searchBtn; height: 32; compact: true; active: filtRow.open
                      readonly property var curF: page.sp.filters.find(function (f) { return f.key === page.sp.filter })
                      text: shell.text("Advanced log search") + (page.sp.filter !== "all" && curF ? "  ·  " + curF.text : "")
                            + (filtRow.open ? "  ▴" : "  ▾")
                      onClicked: filtRow.open = !filtRow.open }
            }
            Btn { id: colBtn; anchors.right: parent.right; height: 32; width: 40; compact: true; glyph: "menu"
                  active: colMenu.open; tip: shell.text("Choose and sort columns"); onClicked: colMenu.openAt(colBtn) }
            SortMenu {
                id: colMenu
                title: shell.text("Choose and sort columns")
                model: page.sp.allColumns
                onToggled: function (i) { page.sp.toggleColumn(page.sp.allColumns[i].i) }
                onMoved: function (from, to) { page.sp.moveColumn(from, to) }
            }
            Flow {   // the advanced log search: all · cards · boosters · trades · imports · by hand · trash
                id: filtRow
                property bool open: false
                y: topRow.height + (open ? 8 : 0)
                width: left.width
                height: open ? implicitHeight : 0
                Behavior on height { enabled: shell.animate; NumberAnimation { duration: 200 * shell.speed; easing.type: Easing.OutCubic } }
                opacity: open ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 160 } }
                visible: height > 0.5
                clip: true
                spacing: 6
                Repeater {
                    model: page.sp.filters
                    Btn { required property var modelData
                          height: 32; compact: true; text: modelData.text; navIcon: modelData.icon || ""; led: true
                          tip: modelData.key === "trash" ? shell.text("Trash: everything deleted (logs, packs, cards, decks, lists, friends) – restorable for 60 days") : ""
                          active: page.sp.filter === modelData.key; onClicked: page.sp.setFilter(modelData.key) }
                }
            }
            // trash: own tab (instead of the table)
            Rectangle {
                id: trashBox
                readonly property bool shown: page.sp.filter === "trash"
                y: filtRow.y + filtRow.height + 8
                width: parent.width
                height: shown ? parent.height - y - buttons.height - 10 : 0
                visible: shown
                color: "transparent"   // no frame (heading on top)
                clip: true
                Text { x: 12; y: 8; text: shell.text("Trash – entries stay 60 days, then they're gone for good")
                       color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true }
                Btn { anchors.right: parent.right; anchors.rightMargin: 8; y: 5; height: 24; compact: true; danger: true
                      visible: page.sp.trash.length > 0; text: shell.text("Empty trash")
                      onClicked: page.sp.emptyTrash() }
                Text { x: 12; y: 34; visible: page.sp.trash.length === 0; text: shell.text("Empty – nothing deleted.")
                       color: T.dim; font.family: T.font; font.pixelSize: 13 }
                ListView {
                    ScrollHint {}
                    id: trashList
                    x: 6; y: 30; width: parent.width - 12; height: parent.height - y - 6
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    model: trashBox.shown ? page.sp.trash : []   // rows only while the trash is open
                    delegate: Item {
                        id: ti
                        required property var modelData
                        width: trashList.width; height: 32
                        Rectangle { anchors.fill: parent; radius: 7; color: th.hovered ? Qt.lighter(T.surface, 1.08) : "transparent" }
                        Text { x: 8; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 230; elide: Text.ElideRight
                               textFormat: Text.StyledText
                               text: "<font color='" + T.dim + "'>" + ti.modelData.kind + "</font>  " + ti.modelData.title
                               color: T.text; font.family: T.font; font.pixelSize: 13 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 196; anchors.verticalCenter: parent.verticalCenter
                               text: ti.modelData.when; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                        HoverHandler { id: th }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Btn { height: 26; width: 140; compact: true; text: "↺  " + shell.text("Restore")
                                  onClicked: page.sp.restoreTrash(ti.modelData.name) }
                            Btn { height: 26; width: 30; compact: true; text: "✕"; danger: true; tip: shell.text("Delete for good")
                                  onClicked: page.sp.dropTrash(ti.modelData.name) }
                        }
                    }
                }
            }
            Rectangle {
                id: table
                visible: !trashBox.shown
                y: filtRow.y + filtRow.height + 8
                width: parent.width; height: parent.height - y - buttons.height - 10 - (undoBar.visible ? undoBar.height + 8 : 0)
                color: "transparent"   // no frame: header line with a divider (like the tables in Play)
                clip: true
                // date and numbers (packs, cards, value, spent, balance) are never cut: those columns are as wide as
                // their widest entry (or head); the text columns (title, types, tags) share what is left by their shares
                // the columns once per change – read by every cell, each read was a call into Python (1500 per opening)
                readonly property var cols: page.sp.columns
                FontMetrics { id: cellFm; font.family: T.font; font.pixelSize: 13 }
                FontMetrics { id: headFm; font.family: T.font; font.pixelSize: 12; font.bold: true }
                readonly property var fitW: {
                    var cs = table.cols, rs = page.sp.rows, out = []
                    for (var i = 0; i < cs.length; i++) {
                        if (!cs[i].fit) { out.push(-1); continue }
                        var w = headFm.advanceWidth(cs[i].text)
                        for (var r = 0; r < rs.length; r++) w = Math.max(w, cellFm.advanceWidth(rs[r].cells[i].text || ""))
                        out.push(Math.ceil(w) + 16)
                    }
                    // very narrow (table next to an open log and the card editor): the title keeps ~90 px – the date
                    // gives way first (it may be cut there), the numbers never
                    var fixed = 0
                    for (var k = 0; k < out.length; k++) if (out[k] > 0) fixed += out[k]
                    if (width - fixed < 90 && cs.length && cs[0].i === 0) out[0] = Math.max(48, out[0] - (90 - (width - fixed)))
                    return out
                }
                readonly property real fixedW: { var s = 0; for (var i = 0; i < fitW.length; i++) if (fitW[i] > 0) s += fitW[i]; return s }
                readonly property real totalW: {
                    var s = 0, cs = table.cols
                    for (var i = 0; i < cs.length; i++) if (!(fitW[i] > 0)) s += cs[i].w
                    return Math.max(1, s)
                }
                // little room left for the texts: all of it goes to the title (types and tags step aside, the row's
                // tip still has them) – three narrow text columns would each show only "…"
                readonly property bool tight: width - fixedW < 260
                function colW(i) {
                    if (fitW[i] > 0) return fitW[i]
                    if (tight) return table.cols[i].i === 1 ? Math.max(0, width - fixedW) : 0
                    return Math.max(0, width - fixedW) * table.cols[i].w / totalW
                }
                Row {
                    id: thead
                    y: 0; height: 30
                    Repeater {
                        model: table.cols
                        Text {
                            required property var modelData
                            required property int index
                            width: table.colW(index); height: 30; visible: width > 8
                            verticalAlignment: Text.AlignVCenter
                            horizontalAlignment: modelData.right ? Text.AlignRight : Text.AlignLeft
                            rightPadding: modelData.right ? 8 : 0
                            leftPadding: modelData.right ? 0 : 6
                            text: modelData.text; elide: Text.ElideRight
                            color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true
                        }
                    }
                }
                Rectangle { y: thead.y + thead.height; width: table.width; height: 1; color: T.line }
                ListView {
                    ScrollHint {}
                    id: rows
                    y: thead.y + thead.height + 4
                    width: table.width; height: table.height - y
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    model: page.sp.rows
                    delegate: Rectangle {
                        id: rr
                        required property var modelData
                        width: rows.width; height: 34; radius: 8
                        color: modelData.sel ? T.surface2 : (rh.hovered ? Qt.lighter(T.surface, 1.12) : "transparent")
                        border.width: modelData.sel ? 1 : 0; border.color: T.line2
                        HoverHandler { id: rh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: page.sp.select(rr.modelData.r) }
                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            Repeater {
                                model: rr.modelData.cells
                                Text {
                                    required property var modelData
                                    required property int index
                                    readonly property bool alignR: table.cols[index] ? table.cols[index].right : false
                                    width: table.colW(index); visible: width > 8
                                    horizontalAlignment: alignR ? Text.AlignRight : Text.AlignLeft
                                    rightPadding: alignR ? 8 : 0
                                    leftPadding: alignR ? 0 : 6
                                    text: modelData.text; elide: Text.ElideRight
                                    color: modelData.color !== "" && modelData.color !== "#000000" ? modelData.color : (rr.modelData.sel ? T.top : T.text)
                                    font.family: T.font; font.pixelSize: 13
                                    // cut short (title, types): the whole text as a tip
                                    HoverHandler {
                                        enabled: parent.truncated
                                        onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, 0, parent.height + 2); shell.tip(modelData.tip || modelData.text, p.x, p.y) }
                                                          else shell.tip("", 0, 0)
                                    }
                                }
                            }
                        }
                    }
                }
                Column {
                    anchors.centerIn: parent
                    visible: page.sp.empty
                    spacing: 16
                    width: Math.min(parent.width - 60, 460)
                    Text { width: parent.width; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                           text: shell.text("No logs yet. A log starts by itself with the first card you scan – with value and balance.")
                           color: T.text2; font.family: T.font; font.pixelSize: 15 }
                    Btn { anchors.horizontalCenter: parent.horizontalCenter; height: 42; width: 200; primary: true
                          text: shell.text("Scan cards"); onClicked: page.sp.scan() }
                }
            }
            // undo after removing a card / a pack
            Rectangle {
                id: undoBar
                visible: page.sp.undoText !== ""
                y: buttons.y - height - 8
                width: parent.width; height: 40
                radius: 10; color: T.surface2; border.width: 1; border.color: T.line2
                Text { x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 190; elide: Text.ElideRight
                       text: page.sp.undoText; color: T.text2; font.family: T.font; font.pixelSize: 13 }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Btn { height: 28; width: 120; compact: true; text: "↺  " + shell.text("Undo"); onClicked: page.sp.undo() }
                    Btn { height: 28; width: 30; compact: true; glyph: "close"; tip: shell.text("Hide – stays in the trash")
                          onClicked: page.sp.dropUndo() }
                }
            }
            Item { id: buttons; y: parent.height; width: parent.width; height: 0 }   // (its keys sit in the log's head now)
        }

        // ================= centre: edit, overview, packs =================
        Flickable {
            ScrollHint {}
            id: mid
            x: left.width + 16
            width: Math.max(0, area.mainW - x); height: area.height
            visible: width > 40
            contentHeight: midCol.implicitHeight + 10
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: midCol
                width: mid.width - 8
                spacing: 10
                // one flow without frames: edit form | summary | packs, divided by lines (no stacked boxes)
                Item {   // the log's head in two parts (review .101): left edit, right what you can do with it
                    visible: page.sp.hasSelection
                    width: parent.width; height: Math.max(form.height, acts.y + acts.implicitHeight) + 6
                    readonly property bool narrow: width < 620   // narrow: the actions below the form
                    Mirror { id: form; width: parent.narrow ? parent.width : parent.width - acts.width - 24
                             mirror: page.sp.editForm }
                    Rectangle { visible: !parent.narrow; x: form.width + 11; width: 1; height: parent.height - 6; color: T.line }
                    Column {
                        id: acts
                        x: parent.narrow ? 0 : parent.width - width
                        y: parent.narrow ? form.height + 10 : 0
                        width: 200
                        spacing: 8
                        Text { text: shell.text("Actions"); color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true
                               height: 24; verticalAlignment: Text.AlignVCenter }
                        Btn { width: parent.width; height: 32; compact: true; navIcon: "share"; text: shell.text("Share image")
                              tip: shell.text("Share: log recap as an image – packs, value, balance and the best hits; to copy for WhatsApp/Discord or as PNG")
                              onClicked: page.sp.share() }
                        Btn { width: parent.width; height: 32; compact: true; led: true; active: page.sp.libOn
                              text: shell.text("in the library"); enabled: page.sp.libEnabled; tip: page.sp.libTip
                              onClicked: page.sp.toggleLibrary() }
                        Btn { width: parent.width; height: 32; compact: true; text: shell.text("Create deck …")
                              tip: shell.text("Selected pack (or the whole log if a card/nothing is selected) as a deck")
                              onClicked: page.sp.toDeck() }
                        Btn { width: parent.width; height: 32; compact: true; text: shell.text("As list")
                              tip: shell.text("All cards of this log (exact prints) as an own list – Library → Lists")
                              onClicked: page.sp.toList() }
                        Btn { width: parent.width; height: 32; compact: true; danger: true; text: shell.text("To the trash")
                              enabled: !page.sp.selectedRunning
                              tip: page.sp.selectedRunning ? shell.text("End the running log first – then it can be deleted.") : ""
                              onClicked: page.sp.deleteSession() }
                    }
                }
                Item {
                    width: parent.width; height: sumText.implicitHeight + 22
                    Rectangle { visible: page.sp.hasSelection; width: parent.width; height: 1; color: T.line }
                    Text { id: sumText; y: 12; width: parent.width
                           text: page.sp.summary; textFormat: Text.RichText; wrapMode: Text.Wrap
                           color: T.text2; font.family: T.font; font.pixelSize: 13; lineHeight: 1.25 }
                }
                Item {
                    id: packBox
                    visible: page.sp.hasSelection
                    width: parent.width; height: Math.max(120, packList.contentHeight + 16)
                    Rectangle { width: parent.width; height: 1; color: T.line }
                    // The list is only as tall as the visible area and moves along while scrolling (box = full
                    // height for outer scrolling) – so Qt builds only the visible rows, not all (large sessions with
                    // 1000+ cards otherwise took over a second to open)
                    readonly property real boxTop: packBox.y + midCol.y
                    readonly property real full: Math.max(0, packBox.height - 16)
                    readonly property real viewH: Math.min(full, mid.height)
                    readonly property real off: Math.max(0, Math.min(full - viewH, mid.contentY - boxTop - 8))
                    ListView {
                        id: packList
                        y: 8 + packBox.off; width: parent.width; height: packBox.viewH
                        // set, not bound: moving contentY builds rows, which corrects contentHeight -> the box height ->
                        // off -> contentY (tester log: hundreds of "binding loop" warnings while scrolling a log)
                        property bool following: false
                        function follow() {
                            if (following) return
                            following = true
                            var y = originY + packBox.off
                            if (Math.abs(contentY - y) > 0.5) contentY = y
                            following = false
                        }
                        Connections { target: packBox; function onOffChanged() { packList.follow() } }
                        onOriginYChanged: follow()
                        Component.onCompleted: follow()
                        interactive: false
                        model: page.sp.packs
                        delegate: Rectangle {
                            id: pr
                            required property var modelData
                            width: packList.width; height: modelData.pack ? 34 : (pr.note !== "" ? 42 : 30)
                            readonly property string note: modelData.note || ""   // what changed on it (grey, small)
                            radius: 7
                            readonly property bool foreign: modelData.foreign === true   // other game (mixed trade)
                            readonly property bool foreignCard: foreign && !modelData.pack
                            opacity: foreign ? (fh.hovered && foreignCard ? 0.8 : 0.5) : 1
                            color: (ph.hovered && !foreign) || (fh.hovered && foreignCard) ? T.surface2 : "transparent"
                            HoverHandler { id: ph; enabled: !pr.foreign; cursorShape: Qt.PointingHandCursor }
                            HoverHandler { id: fh; enabled: pr.foreignCard; cursorShape: Qt.PointingHandCursor
                                onHoveredChanged: if (hovered) { var p = pr.mapToItem(null, pr.width / 2, pr.height); shell.tip(pr.modelData.tip || "", p.x, p.y) }
                                                  else shell.tip("", 0, 0) }
                            TapHandler { enabled: pr.foreignCard; onTapped: { shell.tip("", 0, 0); page.sp.openForeign(pr.modelData.g) } }
                            TapHandler {
                                enabled: !pr.foreign
                                onTapped: function (ev, b) {
                                    if (tapCount !== 1) return
                                    if (pr.modelData.pack) page.sp.togglePack(pr.modelData.pi)
                                    else page.sp.clickRow(pr.modelData.pi, pr.modelData.ci, 0)
                                }
                                onDoubleTapped: if (!pr.modelData.pack && pr.modelData.manual !== true) page.sp.editCard(pr.modelData.pi, pr.modelData.ci)
                            }
                            Text {
                                visible: pr.modelData.pack && !pr.foreign
                                x: 6; anchors.verticalCenter: parent.verticalCenter
                                text: pr.modelData.open ? "▾" : "▸"; color: T.muted; font.pixelSize: 13
                            }
                            Text {
                                id: rowName
                                x: pr.modelData.pack ? 24 : 34; anchors.verticalCenter: parent.verticalCenter
                                anchors.verticalCenterOffset: pr.note !== "" ? -7 : 0
                                width: parent.width * 0.52 - x; elide: Text.ElideRight
                                text: pr.modelData.name
                                color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: pr.modelData.pack
                            }
                            Text {   // what changed on this copy (from the library: condition, language …) – small, grey
                                visible: pr.note !== ""
                                x: rowName.x; y: rowName.y + rowName.height
                                width: parent.width - x - 120; elide: Text.ElideRight
                                text: pr.note
                                color: T.dim; font.family: T.font; font.pixelSize: 11
                            }
                            Text {
                                visible: pr.modelData.pack && !pr.modelData.plain   // scanning cards: no pack type
                                x: parent.width * 0.54; anchors.verticalCenter: parent.verticalCenter
                                width: parent.width * 0.26; elide: Text.ElideRight
                                text: pr.modelData.type
                                color: th2.hovered ? T.top : (pr.modelData.typeColor || T.text2)
                                font.family: T.font; font.pixelSize: 13; font.bold: true
                                font.underline: th2.hovered
                                HoverHandler { id: th2; cursorShape: Qt.PointingHandCursor
                                    onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(shell.text("Click to change the type of this pack"), p.x, p.y) } else shell.tip("", 0, 0) }
                                TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: page.sp.clickRow(pr.modelData.pi, -1, 1) }
                            }
                            Text {
                                visible: !pr.modelData.pack
                                x: parent.width * 0.54; anchors.verticalCenter: parent.verticalCenter
                                text: pr.modelData.set; color: T.muted; font.family: T.font; font.pixelSize: 13
                            }
                            Text {
                                anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                                visible: !ph.hovered
                                text: pr.modelData.price; color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: pr.modelData.pack
                            }
                            // buttons on the row under the mouse – made only for that row (seven keys on every row
                            // cost ~280 items each: switching a log rebuilt ~8000 items, ~0.8 s)
                            Loader {
                                active: ph.hovered
                                anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                                sourceComponent: Row {
                                spacing: 4
                                Btn { visible: !pr.modelData.pack && pr.modelData.manual === true; height: 26; width: implicitWidth + 12
                                      compact: true; text: shell.text("Undo")
                                      tip: shell.text("Take this change back – the collection follows")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, pr.modelData.ci, "undo") }
                                Btn { visible: !pr.modelData.pack && pr.modelData.manual !== true; width: 28; height: 26; compact: true; text: "+"; tip: shell.text("Count once more (key +)")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, pr.modelData.ci, "plus") }
                                Btn { visible: !pr.modelData.pack && pr.modelData.manual !== true; width: 32; height: 26; compact: true; text: pr.modelData.fin || "F"
                                      tip: shell.text("Switch finish (Foil, or Normal → Holo → Reverse Holo)")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, pr.modelData.ci, "foil") }
                                Btn { visible: !pr.modelData.pack && pr.modelData.manual !== true; width: 28; height: 26; compact: true; text: "⚙"; tip: shell.text("Change card …")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, pr.modelData.ci, "gear") }
                                Btn { visible: !pr.modelData.pack && pr.modelData.manual !== true; width: 28; height: 26; compact: true; danger: true; text: "✕"; tip: shell.text("Remove card")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, pr.modelData.ci, "remove") }
                                Btn { visible: pr.modelData.pack && !pr.modelData.plain && pr.modelData.pi > 0; width: 28; height: 26; compact: true; text: "⤒"
                                      tip: shell.text("Merge with the pack before (e.g. after “New pack” by mistake)")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, -1, "merge") }
                                Btn { visible: pr.modelData.pack && !pr.modelData.plain; width: 28; height: 26; compact: true; danger: true; text: "✕"; tip: shell.text("Delete pack")
                                      onClicked: page.sp.rowAction(pr.modelData.pi, -1, "pack") }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ================= right: detail / compare / change card =================
        DetailView {
            id: detView
            det: page.sp.detail
            x: area.width - area.detW
            width: Math.max(0, area.detW); height: area.height
            visible: area.detW > 1 && !page.sp.editOpen
        }
        Loader {   // compare: made only while it is open
            x: detView.x - area.cmpW - (area.cmpW > 1 ? 14 : 0)
            width: Math.max(0, area.cmpW); height: area.height
            active: area.cmpW > 1
            visible: active
            sourceComponent: DetailView { det: page.sp.compare }
        }
        Rectangle {
            visible: page.sp.editOpen && area.detW > 1
            x: area.width - area.detW
            width: area.detW; height: area.height
            radius: 14
            color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
            clip: true
            Loader {   // edit card (the same window as when scanning) – made only while it is open
                anchors.fill: parent; anchors.margins: 16
                active: page.sp.editOpen
                sourceComponent: CardSearch {
                    cs: page.sp.cardSearch
                    closable: true
                    onCloseRequested: page.sp.escape()
                }
            }
        }
        Item {   // divider: table wider/narrower next to the open log
            visible: page.sp.hasSelection && mid.visible
            x: left.width + 3
            height: area.height; width: 10
            Rectangle { anchors.centerIn: parent; width: 3; height: 46; radius: 1.5; color: dvh.hovered || td.active ? T.text2 : T.line2 }
            HoverHandler { id: dvh; cursorShape: Qt.SplitHCursor }
            DragHandler {
                id: td
                target: null; yAxis.enabled: false
                property real startW: 0
                onActiveChanged: {
                    if (active) startW = left.width
                    else { page.sp.setTableShare(area.share); area.shareDrag = -1 }
                }
                onTranslationChanged: if (active) area.shareDrag = Math.max(0.3, Math.min(0.7, (startW + translation.x) / Math.max(1, area.mainW - 16)))
            }
        }
        Item {   // handle: detail view wider/narrower
            visible: area.detW > 1 && !page.sp.editOpen
            x: (area.cmpW > 1 ? area.width - area.detW - area.cmpW - 14 : area.width - area.detW) - 13
            height: area.height; width: 10
            Rectangle { anchors.centerIn: parent; width: 3; height: 46; radius: 1.5; color: gh.hovered || gd.active ? T.text2 : T.line2 }
            HoverHandler { id: gh; cursorShape: Qt.SplitHCursor }
            DragHandler {
                id: gd
                target: null; yAxis.enabled: false
                property real startW: 0
                onActiveChanged: {
                    if (active) startW = area.panelW
                    else { page.sp.setPanelWidth(Math.round(area.panelW)); area.dragW = -1 }
                }
                onTranslationChanged: if (active) area.dragW = Math.max(380, startW - translation.x / (page.sp.compareOpen ? 2 : 1))
            }
        }
    }
    Shortcut { sequence: "Escape"; enabled: page.visible && (page.sp.detailOpen || page.sp.editOpen); onActivated: page.sp.escape() }
}
