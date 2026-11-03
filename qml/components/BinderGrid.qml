// Binder tiles (profile and Trade page): four per row, closed abstract binders of all games. Click opens,
// „⋯“ in the top corner (flat, semi-transparent like on the decks) opens the binder menu. Drag onto the edge of
// another binder = order. At the end „+ New binder“ (game, size 4 · 9 · 12, name – right in the tile).
// pp = qprofile.ProfileBackend.
import QtQuick

Item {
    id: g
    property var pp: profilePage
    property int columns: 4
    property string renameId: ""   // menu → Rename: this binder's name becomes a field under its cover (review .101)
    readonly property real gap: 18
    readonly property real tileW: Math.floor((width - gap * (columns - 1)) / columns)
    readonly property real coverH: tileW * 1.3
    implicitHeight: flow.implicitHeight
    signal opened()   // a binder was opened (the Trade page then switches to the profile)

    Flow {
        id: flow
        width: g.width
        spacing: g.gap
        Repeater {
            model: g.pp.binderTiles
            delegate: Item {
                id: bt
                required property var modelData
                readonly property bool isNew: modelData["new"] === true
                width: g.tileW; height: g.coverH + 52
                opacity: isNew || modelData.owned ? 1 : 0.4
                property real hv: ch.hovered ? 1 : 0
                Behavior on hv { NumberAnimation { duration: 160 } }
                Drag.active: bdrag.active
                Drag.keys: ["binder"]
                Drag.source: bt
                Drag.hotSpot.x: bdrag.gx; Drag.hotSpot.y: bdrag.gy   // drop target = under the mouse
                FollowDrag { id: bdrag; enabled: !bt.isNew && !nask.open
                              onActiveChanged: if (!active) { bt.Drag.drop(); bt.x = bt.x } }
                states: State { when: bdrag.active
                                ParentChange { target: bt; parent: g.Window.window ? g.Window.window.contentItem : g }
                                PropertyChanges { target: bt; z: 300 } }
                DropArea { id: dl; x: 0; width: parent.width / 2; height: parent.height; keys: ["binder"]
                           enabled: !bt.isNew && !bdrag.active
                           onDropped: function (ev) { var s = drag.source; if (s && s !== bt)
                               Qt.callLater(g.pp.reorderBinders, s.modelData.key, bt.modelData.key, false) } }
                DropArea { id: dr; x: parent.width / 2; width: parent.width / 2; height: parent.height; keys: ["binder"]
                           enabled: !bt.isNew && !bdrag.active
                           onDropped: function (ev) { var s = drag.source; if (s && s !== bt)
                               Qt.callLater(g.pp.reorderBinders, s.modelData.key, bt.modelData.key, true) } }
                Rectangle { visible: dl.containsDrag; x: -g.gap / 2 - 2; y: 10; width: 4; height: g.coverH - 20; radius: 2; color: "#e6e6e6" }
                Rectangle { visible: dr.containsDrag; x: parent.width + g.gap / 2 - 2; y: 10; width: 4; height: g.coverH - 20; radius: 2; color: "#e6e6e6" }

                // ---------- closed binder ----------
                Item {
                    id: cover
                    visible: !bt.isNew
                    width: parent.width; height: g.coverH
                    scale: bdrag.active ? 0.92 : 1
                    Rectangle { x: 6; y: 6; width: parent.width - 6; height: parent.height - 6; radius: 12
                                color: Qt.rgba(0, 0, 0, 0.45) }
                    Rectangle {
                        width: parent.width - 6; height: parent.height - 6; radius: 12
                        color: Qt.hsla((bt.modelData.hue || 0) / 360, 0.32, 0.26 + 0.04 * bt.hv, 1)
                        border.width: 1; border.color: Qt.hsla((bt.modelData.hue || 0) / 360, 0.3, 0.4 + 0.2 * bt.hv, 1)
                        Rectangle { width: 26; height: parent.height; radius: 12
                                    color: Qt.hsla((bt.modelData.hue || 0) / 360, 0.3, 0.18, 1) }
                        Repeater { model: 3
                            Rectangle { required property int index; x: 8; y: parent.height * (0.18 + index * 0.27); width: 10
                                        height: 22; radius: 5; color: "#c9c9c9"; opacity: 0.8 } }
                        Rectangle { x: 44; y: parent.height * 0.3; width: parent.width - 66; height: parent.height * 0.36; radius: 8
                                    color: "transparent"; border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.18) }
                        Image { x: 36; y: 10; width: 20; height: 20; smooth: false; source: bt.modelData.icon || "" }
                    }
                    Rectangle {   // „⋯“: binder menu – flat, semi-transparent (like on the decks)
                        id: menuDot
                        visible: bt.hv > 0.01 && !bdrag.active
                        x: parent.width - width - 14; y: 10
                        width: 34; height: 26; radius: 13
                        color: Qt.rgba(0.04, 0.04, 0.04, mdh.hovered ? 0.92 : 0.72)
                        border.width: 1.5; border.color: Qt.rgba(0.85, 0.85, 0.85, mdh.hovered ? 1 : 0.7)
                        Text { anchors.centerIn: parent; text: "⋯"; color: "#ededed"; font.pixelSize: 16; font.bold: true }
                        HoverHandler { id: mdh; cursorShape: Qt.PointingHandCursor }
                    }
                    HoverHandler { id: ch; cursorShape: bt.modelData.owned ? Qt.PointingHandCursor : Qt.ArrowCursor }
                    TapHandler {
                        enabled: bt.modelData.owned === true
                        onTapped: function (ev) {
                            var p = ev.position
                            if (menuDot.visible && p.x >= menuDot.x && p.y <= menuDot.y + menuDot.height + 2) {
                                bmenu.game = bt.modelData.game; bmenu.bid = bt.modelData.id
                                bmenu.items = g.pp.binderMenu(bt.modelData.game, bt.modelData.id)
                                bmenu.openAt(menuDot)
                                return
                            }
                            g.pp.openBinder(bt.modelData.game, bt.modelData.id)
                            g.opened()
                        }
                    }
                }
                Column {
                    visible: !bt.isNew
                    y: g.coverH + 8; width: parent.width; spacing: 2
                    Item {
                        width: parent.width; height: Math.max(nameT.implicitHeight, shareChip.height)
                        RenameField {   // click on the name = rename (only your own binders)
                            id: nameT
                            z: 30
                            readonly property bool asked: g.renameId !== "" && g.renameId === bt.modelData.id
                            width: Math.min(implicitWidth, parent.width - shareChip.width - 8); height: 22
                            anchors.verticalCenter: parent.verticalCenter
                            text: bt.modelData.name || ""; pixelSize: 14; bold: true
                            canEdit: bt.modelData.owned === true
                            onAskedChanged: if (asked) start()
                            onEditingChanged: if (!editing && asked) g.renameId = ""
                            commit: function (v) { return g.pp.renameBinderTo(bt.modelData.game, bt.modelData.id, v) }
                        }
                        Chip {   // like the lists: private / shared, click toggles
                            id: shareChip
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            text: bt.modelData.shared ? shell.text("shared") : shell.text("private")
                            lit: bt.modelData.shared === true
                            tip: bt.modelData.shared ? shell.text("Shared with friends – click: private")
                                                     : shell.text("Private – click: share with friends")
                            onClicked: g.pp.setBinderShared(bt.modelData.game, bt.modelData.id, !bt.modelData.shared)
                        }
                    }
                    Text { width: parent.width; elide: Text.ElideRight
                           text: (bt.modelData.value || "") + "  ·  " + (bt.modelData.info || "")
                           color: T.muted; font.family: T.font; font.pixelSize: 12 }
                }

                // ---------- „+ New binder“: field expands inside the tile ----------
                Rectangle {
                    visible: bt.isNew
                    width: parent.width; height: g.coverH - 6; radius: 12
                    color: Qt.rgba(0.07, 0.07, 0.08, 0.6 + 0.2 * bt.hv)
                    border.width: 2; border.color: Qt.tint(T.line2, Qt.rgba(1, 1, 1, 0.5 * bt.hv))
                    Column {
                        visible: !nask.open
                        anchors.centerIn: parent; spacing: 6
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "+"; color: T.dim
                               font.family: T.font; font.pixelSize: 48; font.bold: true }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("New binder")
                               color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true }
                    }
                    HoverHandler { id: nh; cursorShape: Qt.PointingHandCursor; onHoveredChanged: bt.hv = hovered ? 1 : 0 }
                    // (check justClosed in the click – as a binding it would never be free again after „Cancel“)
                    TapHandler { enabled: !nask.open
                                 onTapped: { if (nask.justClosed()) return
                                             nask.size = "3x3"; nask.game = g.pp.gameKey
                                             nask.start("new", "", shell.text("New binder"), "", shell.text("Create")) } }
                    InlineAsk {
                        id: nask
                        anchors.fill: parent; fill: true; z: 5
                        property string size: "3x3"
                        property string game: ""
                        placeholder: shell.text("Name")
                        onAccepted: function (mode, ident, text) { g.pp.newBinder(text, nask.size, nask.game) }
                        extra: Component { Column {   // (built only while open)
                            spacing: 8
                            Seg {   // for which game – only for those who have several
                                visible: g.pp.binderGames.length > 1
                                anchors.horizontalCenter: parent.horizontalCenter
                                items: g.pp.binderGames; current: nask.game
                                onPicked: function (k) { nask.game = k }
                            }
                            Seg {
                                anchors.horizontalCenter: parent.horizontalCenter
                                items: [{"key": "2x2", "text": "4"}, {"key": "3x3", "text": "9"}, {"key": "4x3", "text": "12"}]
                                current: nask.size; onPicked: function (k) { nask.size = k }
                            }
                        } }
                        Rectangle { anchors.fill: parent; z: -1; radius: 12; color: Qt.lighter(T.surface, 1.25)
                                    border.width: 1; border.color: T.line2 }
                    }
                }
            }
        }
    }
    ContextMenu {
        id: bmenu
        parent: g.Window.window ? g.Window.window.contentItem : g
        anchors.fill: parent
        z: 900
        property string game: ""
        property string bid: ""
        onPicked: function (k) { if (k === "rename") g.renameId = bid; else g.pp.binderAction(game, bid, k) }
    }
}
