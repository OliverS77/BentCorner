// Decks: overview in Qt Quick (folder bar, tiles, new deck, Built chip, drag onto folder, right click).
// Editor: components/DeckEditor.qml (qdeckedit.py); compare and suggest: DeckCompare/DeckSuggest (qdeckmore.py). Data/logic: decksPage (qdecks.py).
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var dk: decksPage

    // ---------- Editor ----------
    ViewPane {
        anchors.fill: parent
        shown: page.dk.view === "editor"
        lazy: Component { DeckEditor { de: page.dk.editor } }
    }
    // ---------- Compare / suggest ----------
    ViewPane {
        anchors.fill: parent
        shown: page.dk.view === "compare"
        lazy: Component { DeckCompare { cv: page.dk.compareView } }
    }
    ViewPane {
        anchors.fill: parent
        shown: page.dk.view === "suggest"
        lazy: Component { DeckSuggest { sg: page.dk.suggestView; br: page.dk.brew } }
    }
    Shortcut { sequence: "Escape"; enabled: page.visible && page.dk.view !== "overview" && !sheetHost.covering
               onActivated: page.dk.view === "editor" ? page.dk.editor.escape() : page.dk.escape() }

    // ---------- Overview ----------
    ViewPane {
        id: over
        anchors.fill: parent
        anchors.leftMargin: 20; anchors.rightMargin: 20; anchors.topMargin: 14; anchors.bottomMargin: 10
        shown: page.dk.view === "overview"
        depth: 0

        // folder bar
        Rectangle {
            id: bar
            width: page.dk.sidebarOpen ? 260 : 60
            Behavior on width { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            height: parent.height
            radius: 16
            color: Qt.darker(T.surface, 1.1)
            border.width: 1; border.color: T.line
            clip: true
            Item {
                x: 8; y: 10; width: parent.width - 16; height: 30
                Text { visible: page.dk.sidebarOpen; x: 6; anchors.verticalCenter: parent.verticalCenter
                       text: shell.text("Folder"); color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
                Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                       text: page.dk.sidebarOpen ? "«" : "»"; color: tg.hovered ? T.text : T.muted
                       font.pixelSize: 15; font.bold: true
                       HoverHandler { id: tg; cursorShape: Qt.PointingHandCursor }
                       TapHandler { onTapped: page.dk.toggleSidebar() } }
            }
            Column {
                id: entries
                x: 8; y: 46; width: parent.width - 16
                spacing: 2
                Repeater {
                    model: page.dk.folders
                    delegate: Item {
                        id: fe
                        required property var modelData
                        width: entries.width; height: 44
                        readonly property bool drop: dropArea.containsDrag
                        Rectangle {
                            anchors.fill: parent; anchors.margins: 2
                            radius: 10
                            visible: fe.modelData.sel || eh.hovered || fe.drop
                            color: fe.modelData.sel ? T.accent_deep : T.surface2
                            border.width: 1; border.color: fe.drop ? T.text : (fe.modelData.sel ? T.accent : T.line)
                        }
                        Text {   // diamond in the folder colour
                            x: page.dk.sidebarOpen ? 14 : (fe.width - width) / 2
                            anchors.verticalCenter: parent.verticalCenter
                            text: "◆"; color: fe.modelData.color; font.pixelSize: 15
                        }
                        Text {
                            visible: page.dk.sidebarOpen
                            x: 40; width: parent.width - 84; anchors.verticalCenter: parent.verticalCenter
                            text: fe.modelData.name; elide: Text.ElideRight
                            color: fe.modelData.sel ? T.top : (eh.hovered ? T.text : T.text2)
                            font.family: T.font; font.pixelSize: 14
                        }
                        Text {
                            visible: page.dk.sidebarOpen
                            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                            text: fe.modelData.count; color: fe.modelData.sel ? T.text : T.dim
                            font.family: T.font; font.pixelSize: 12
                        }
                        HoverHandler { id: eh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: page.dk.setFolder(fe.modelData.key) }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            enabled: fe.modelData.editable
                            onTapped: function (ev) {
                                var p = fe.mapToItem(over, ev.position.x, ev.position.y)
                                folderMenu.folder = fe.modelData.key; folderMenu.color = fe.modelData.color
                                folderMenu.open(p.x, p.y)
                            }
                        }
                        DropArea {
                            id: dropArea
                            anchors.fill: parent
                            keys: ["deck"]
                            onDropped: function (ev) { page.dk.moveDeck(ev.source.deckIndex, fe.modelData.key) }
                        }
                    }
                }
            }
            // new folder / rename directly in the bar: name, colour, ✕ / ✓
            Rectangle {
                id: edit
                property string renaming: ""
                property string fcolor: ""
                visible: false
                x: 8; y: entries.y + entries.height + 8; width: parent.width - 16
                height: editCol.implicitHeight + 16
                radius: 12; color: T.surface2; border.width: 1; border.color: T.line
                function start(old, col) { renaming = old; fcolor = col || page.dk.nextColor(); nameField.text = old; visible = true; nameField.focusAll() }
                Column {
                    id: editCol
                    x: 8; y: 8; width: parent.width - 16; spacing: 8
                    SearchField { id: nameField; width: parent.width; height: 32; clearable: false
                                  placeholder: shell.text("Folder name …")
                                  onAccepted: { page.dk.saveFolder(edit.renaming, text, edit.fcolor); edit.visible = false } }
                    Flow {
                        width: parent.width; spacing: 4
                        Repeater { model: page.dk.colors
                            Rectangle { required property var modelData; width: 30; height: 30; radius: 7
                                        color: edit.fcolor.toLowerCase() === modelData.color.toLowerCase() ? T.accent_deep : "transparent"
                                        border.width: 1; border.color: edit.fcolor.toLowerCase() === modelData.color.toLowerCase() ? T.accent : "transparent"
                                        Text { anchors.centerIn: parent; text: "◆"; color: modelData.color; font.pixelSize: 16 }
                                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                                        TapHandler { onTapped: edit.fcolor = modelData.color } } }
                    }
                    Row {
                        anchors.right: parent.right; spacing: 6
                        Btn { text: "✕"; compact: true; danger: true; width: 36; onClicked: edit.visible = false }
                        Btn { text: "✓"; compact: true; primary: true; width: 36
                              onClicked: { page.dk.saveFolder(edit.renaming, nameField.text, edit.fcolor); edit.visible = false } }
                    }
                }
            }
            Item {   // a text key, no framed row inside the panel
                visible: !edit.visible
                x: 8; y: entries.y + entries.height + 8; width: parent.width - 16; height: 38
                Text { x: 12; anchors.verticalCenter: parent.verticalCenter
                       text: page.dk.sidebarOpen ? "+  " + shell.text("New folder") : "+"
                       color: nh.hovered ? T.text : T.muted; font.family: T.font; font.pixelSize: 13 }
                HoverHandler { id: nh; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: { if (!page.dk.sidebarOpen) page.dk.toggleSidebar(); edit.start("", "") } }
            }
        }

        // header
        Item {
            id: head
            x: bar.width + 16; width: parent.width - x; height: 40
            // heading = what is shown: "All decks" or the folder; a thin line runs on to the keys on the right, so
            // they aren't overlooked behind the gap (Oliver, review .101 a8 – a test)
            Row {
                id: headL
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                Text { visible: page.dk.crumb !== ""; text: "◆"; color: page.dk.crumbColor; font.pixelSize: 16; anchors.verticalCenter: parent.verticalCenter }
                Text { text: page.dk.crumb !== "" ? page.dk.crumb : shell.text("All decks")
                       color: T.text; font.family: T.font; font.pixelSize: 22; font.bold: true }
                Text { anchors.verticalCenter: parent.verticalCenter
                       text: page.dk.hasDecks ? ""
                                              : page.dk.tagline
                       color: T.dim; font.family: T.font; font.pixelSize: 13; elide: Text.ElideRight
                       visible: !page.dk.selecting && !page.dk.hasDecks   // selection mode: the actions sit on the right
                       width: visible ? Math.max(0, head.width - 640) : 0 }
            }
            Rectangle {
                visible: page.dk.hasDecks && width > 20
                x: headL.x + headL.width + 16; width: headR.x - 16 - x
                anchors.verticalCenter: parent.verticalCenter; height: 1
                color: T.line
            }
            Row {
                id: headR
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                // selection: „Select“ starts it; then the actions fade in (instead of hidden in the menu)
                Text { visible: page.dk.selecting; anchors.verticalCenter: parent.verticalCenter
                       text: page.dk.selected.length > 0 ? page.dk.selected.length + " " + shell.text("selected")
                                                         : shell.text("Click decks to select them")
                       color: T.text2; font.family: T.font; font.pixelSize: 13 }
                Repeater {
                    model: [{"k": "deck_export", "t": shell.text("Export decklist")},
                            {"k": "share_decks", "t": shell.text("Deck overview as image")}]
                    Btn { required property var modelData
                          visible: opacity > 0.01; opacity: page.dk.selecting ? 1 : 0
                          Behavior on opacity { NumberAnimation { duration: 200 } }
                          enabled: page.dk.selected.length > 0
                          text: modelData.t + (page.dk.selected.length > 0 ? "  (" + page.dk.selected.length + ")" : "")
                          onClicked: page.dk.exportTo(modelData.k) }
                }
                Btn { visible: page.dk.selecting; text: page.dk.allSelected ? shell.text("Keine") : shell.text("Alle")
                      onClicked: page.dk.allSelected ? page.dk.selectNone() : page.dk.selectAll() }
                Btn { text: page.dk.selecting ? shell.text("Done") : shell.text("Select"); enabled: page.dk.hasDecks
                      active: page.dk.selecting
                      tip: page.dk.selecting ? "" : shell.text("Select several decks – to export or as an image")
                      onClicked: page.dk.selecting ? page.dk.clearSelect() : page.dk.startSelect() }
                Btn {
                    id: ioBtn
                    glyph: "import"; width: 44
                    tip: shell.text("Import / export")
                    active: ioMenu.visible
                    onClicked: ioMenu.openAt(ioBtn)
                }
            }
        }

        // tiles
        GridView {
            ScrollHint {}
            EdgeFade {}
            id: grid
            x: head.x; y: head.height + 12
            width: head.width; height: parent.height - y
            visible: !page.dk.empty
            clip: true
            model: page.dk.tiles
            readonly property int cols: Math.max(1, Math.floor(width / 330))
            cellWidth: Math.floor(width / cols)
            cellHeight: 330
            boundsBehavior: Flickable.StopAtBounds
            delegate: Item {
                id: cell
                required property var modelData
                required property int index
                width: grid.cellWidth; height: grid.cellHeight
                property int deckIndex: modelData.i
                Drag.active: dragH.active
                Drag.keys: ["deck"]
                Drag.source: cell
                Drag.hotSpot.x: dragH.gx; Drag.hotSpot.y: dragH.gy   // drop target = under the mouse
                DeckTile {
                    id: tile
                    anchors.fill: parent
                    d: cell.modelData
                    suggest: page.dk.canSuggest
                    importHint: page.dk.importHint
                    selecting: page.dk.selecting
                    selected: cell.modelData.kind === "deck" && page.dk.selected.indexOf(cell.modelData.id) >= 0
                    onSelectToggled: page.dk.toggleSelect(cell.modelData.id)
                    opacity: dragH.active ? 0.6 : tile.selOpacity
                    scale: dragH.active ? 0.9 : 1
                    Behavior on scale { NumberAnimation { duration: 150 } }
                    onOpen: function (half) { page.dk.openTile(cell.modelData.i, half) }
                    onBuiltToggled: page.dk.toggleBuilt(cell.modelData.i)
                    onMenuRequested: function (x, y) {   // the menu in the window, at the click (x, y: window coordinates)
                        var g = page.Window.contentItem.mapToGlobal(x, y)
                        page.dk.deckMenuAt(cell.modelData.i, g.x, g.y) }
                }
                // drag another deck onto this one = sort it in before (custom order in the folder)
                DropArea {
                    id: reorder
                    anchors.fill: parent
                    keys: ["deck"]
                    enabled: cell.modelData.kind === "deck" && !dragH.active
                    onDropped: function (ev) {
                        var s = drag.source
                        if (s && s.modelData && s.modelData.id !== cell.modelData.id)
                            Qt.callLater(page.dk.reorderDeck, s.modelData.id, cell.modelData.id)
                    }
                }
                Rectangle {   // insertion line left of the deck while something is dragged over it
                    visible: reorder.containsDrag
                    x: 2; y: 18; width: 4; height: parent.height - 36; radius: 2
                    color: "#e6e6e6"
                }
                FollowDrag {
                    id: dragH
                    enabled: cell.modelData.kind === "deck"
                    onActiveChanged: if (!active) { cell.Drag.drop()   // then back into its cell
                        settleIn(grid, cell.index) }
                }
                states: State {
                    when: dragH.active
                    ParentChange { target: cell; parent: over }
                }
            }
        }

        // no decks: sentence + buttons
        Column {
            anchors.centerIn: grid
            visible: page.dk.empty
            spacing: 18
            width: Math.min(700, grid.width * 0.85)
            Text { width: parent.width; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                   text: page.dk.emptyText
                   color: T.text2; font.family: T.font; font.pixelSize: 17 }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                Btn { visible: page.dk.canSuggest; text: shell.text("Suggestion from my collection"); primary: true; height: 46
                      onClicked: page.dk.suggest() }
                Btn { text: shell.text("Build it yourself"); primary: !page.dk.canSuggest; height: 46; onClicked: page.dk.newDeck() }
                Btn { text: shell.text("Import decklist …"); height: 46; onClicked: page.dk.importDeck() }
            }
        }

        // Import/Export: what should happen? (marked decks are already selected in the Import/Export tab)
        ContextMenu {
            id: ioMenu
            readonly property int n: page.dk.selected.length
            items: {
                var sfx = n > 0 ? "  (" + n + ")" : " …"
                return [{text: shell.text("Import decklist …"), key: "import"}, {sep: true},
                        {text: shell.text("Export decklist") + sfx, key: "deck_export", enabled: page.dk.hasDecks},
                        {text: shell.text("Deck overview as image") + sfx, key: "share_decks", enabled: page.dk.hasDecks}]
            }
            onPicked: function (k) {
                if (k === "import") page.dk.importDeck()
                else if (k === "select") page.dk.startSelect()
                else if (k === "clear") page.dk.clearSelect()
                else page.dk.exportTo(k)
            }
        }
        // right click on a folder
        ContextMenu {
            id: folderMenu
            property string folder: ""
            property string color: ""
            items: [{text: shell.text("Rename"), key: "rename"}, {sep: true},
                    {text: shell.text("Color"), enabled: false}].concat(page.dk.colors.map(function (c) {
                        return {text: "◆ " + c.label, key: "col:" + c.color, indent: true, on: c.color.toLowerCase() === folderMenu.color.toLowerCase()} }))
                    .concat([{sep: true}, {text: shell.text("Delete folder (decks stay)"), key: "del"}])
            onPicked: function (k) {
                if (k === "rename") edit.start(folder, color)
                else if (k.indexOf("col:") === 0) page.dk.setColor(folder, k.substring(4))
                else if (k === "del") page.dk.deleteFolder(folder)
            }
        }
    }
}
