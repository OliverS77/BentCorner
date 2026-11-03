// Orbit (the Trade page – Oliver, 2026-10-29): at the top the Orbit line, on the left the friends bar, on the right depending on the selection
//   you     your wish and trade lists (tiles)
//   list    on the left the entries, on the right the library view – drag cards in and back out
//   friend  Trade · Wants · Has · Library of …
// Data and logic: tradePage (qtrade.py) via tradeview.TradePage.
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var tp: tradePage
    readonly property var tf: tradeFriends   // TRADE-SPLIT: FriendsBackend
    readonly property var ta: tradeAlarms   // TRADE-SPLIT: AlarmsBackend
    readonly property var tl: tradeLists   // TRADE-SPLIT: ListsBackend
    property string renameLid: ""   // menu „Rename“: this tile turns into an input field

    // Bent°Corner Orbit: what this page is and how far your data travels right now – "Change ›" leads to the slider
    Item {
        id: orbitLine
        readonly property var info: page.visible ? page.tp.orbitLine() : ({})
        x: 22; y: 10; width: page.width - 44; height: 26
        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Text { text: "Orbit"; color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
            Text { anchors.baseline: parent.children[0].baseline; text: shell.text("Friends · Trade · Lists · Prices")
                   color: T.dim; font.family: T.font; font.pixelSize: 13 }
        }
        Row {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            NavIcon { key: "orbit"; s: 0.8; color: T.text2; anchors.verticalCenter: parent.verticalCenter }
            Text { anchors.verticalCenter: parent.verticalCenter; text: orbitLine.info.text || ""
                   color: T.text2; font.family: T.font; font.pixelSize: 13 }
            Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Change ›")
                   color: oh.hovered ? T.hi : T.text; font.family: T.font; font.pixelSize: 13; font.underline: oh.hovered
                   HoverHandler { id: oh; cursorShape: Qt.PointingHandCursor }
                   TapHandler { onTapped: page.tp.openOrbit() } }
        }
    }

    FriendRail {
        id: rail
        tp: page.tp
        x: 18; y: 44
        height: page.height - 58
        onMenu: function (kind, ident, x, y) {
            var r = page.mapFromItem(null, x, y)
            rmenu.kind = kind; rmenu.ident = ident
            rmenu.items = tf.railMenu(kind, ident)
            rmenu.open(r.x, r.y)
        }
    }

    Item {
        id: right
        x: rail.x + rail.width + 16; y: 44
        width: page.width - x - 18; height: page.height - 58
        // binder opened from here: shown in its place – underneath stays as it was (Back = exactly back there)
        opacity: binderLd.open ? 0 : 1
        enabled: !binderLd.open

        // ================= your lists: tiles of the chosen folder (folders: on the left in your box) =================
        ViewPane {
            id: me
            anchors.fill: parent
            shown: tp.view === "me"
            depth: 0
            readonly property string fold: tp.folder
            readonly property var cur: {
                var fs = tp.folders
                for (var i = 0; i < fs.length; i++) if (fs[i].key === fold) return fs[i]
                return fs.length ? fs[0] : ({title: "", sub: "", icon: ""})
            }
            // content
            Item {
                id: fcontent
                width: parent.width; height: parent.height
                Loader {   // no friends yet: explain briefly (no frame – content next to the rail)
                    id: noFriends
                    active: !tf.hasFriends && me.fold !== "alarms"
                    visible: active
                    width: parent.width; height: visible ? 120 : 0
                    sourceComponent: Item {
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line }
                    Column {
                        anchors.centerIn: parent; spacing: 12; width: Math.min(parent.width - 60, 680)
                        Text { width: parent.width; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                               text: shell.text("Trading works with small files: send your friend your trade file and load theirs here – then you see right away who wants and has what.")
                               color: T.text2; font.family: T.font; font.pixelSize: 14 }
                        Row {
                            anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                            Btn { height: 36; width: 210; text: shell.text("Import friend …"); primary: true; onClicked: tf.importFriend() }
                            Btn { height: 36; width: 250; text: shell.text("Create my trade file …"); onClicked: tf.exportFriend() }
                        }
                    }
                    }
                }
                Row {
                    id: fhead2
                    y: noFriends.height + (noFriends.visible ? 14 : 0)
                    spacing: 12
                    Text { text: me.cur.title; color: T.text; font.family: T.font; font.pixelSize: 21; font.bold: true }
                    Text { anchors.baseline: parent.children[0].baseline; text: me.cur.sub; color: T.dim
                           font.family: T.font; font.pixelSize: 13; width: Math.max(0, fcontent.width - 260); elide: Text.ElideRight }
                }
                CheckBox {
                    id: wishDecks
                    visible: me.fold === "wish"
                    y: fhead2.y + fhead2.height + 8
                    text: shell.text("Missing cards of my decks count as wishes (when trading)")
                    checked: tl.wishDecks
                    onToggled: function (on) { tl.setWishDecks(on) }
                }
                // tiles: first „+ New list“
                GridView {
                    ScrollHint {}
                    EdgeFade {}
                    id: tgrid
                    visible: me.fold !== "alarms"
                    y: (wishDecks.visible ? wishDecks.y + wishDecks.height : fhead2.y + fhead2.height) + 14
                    width: parent.width; height: parent.height - y - (tundo.visible ? tundo.height + 10 : 0)
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    readonly property int cols: Math.max(1, Math.floor(width / 250))
                    cellWidth: Math.floor(width / cols); cellHeight: cellWidth * 1.08
                    model: me.fold === "alarms" || me.fold === "offers" || me.fold === "binders" ? [] : [{"new": true}].concat(tp.tiles)
                    delegate: Item {
                        id: tc
                        required property var modelData
                        required property int index
                        width: tgrid.cellWidth; height: tgrid.cellHeight
                        readonly property string kind: me.fold
                        readonly property string lid: modelData.lid || ""
                        property string newGame: ""
                        property bool newShared: false
                        Drag.active: tdrag.active
                        Drag.keys: ["tlist"]
                        Drag.source: tc
                        Drag.hotSpot.x: tdrag.gx; Drag.hotSpot.y: tdrag.gy   // drop target = under the mouse
                        FollowDrag {   // (follows the mouse itself – stays under the cursor while moved into the page)
                            id: tdrag
                            enabled: !tc.modelData["new"]
                            onActiveChanged: if (!active) { tc.Drag.drop()   // then back into its cell
                                settleIn(tgrid, tc.index) }
                        }
                        states: State {
                            when: tdrag.active
                            ParentChange { target: tc; parent: page }
                            PropertyChanges { target: tc; z: 200 }
                        }
                        DropArea {   // drag to the left edge = sort in before
                            id: tbefore
                            x: 0; width: parent.width * 0.24; height: parent.height; z: 3
                            keys: ["tlist"]
                            enabled: !tc.modelData["new"] && !tdrag.active
                            onDropped: function (ev) { var s = drag.source; if (s && s !== tc && s.kind === tc.kind)
                                Qt.callLater(tl.reorderList, tc.kind, s.lid, tc.lid, false) }
                        }
                        DropArea {   // to the right edge = after
                            id: tafter
                            x: parent.width * 0.76; width: parent.width * 0.24; height: parent.height; z: 3
                            keys: ["tlist"]
                            enabled: !tc.modelData["new"] && !tdrag.active
                            onDropped: function (ev) { var s = drag.source; if (s && s !== tc && s.kind === tc.kind)
                                Qt.callLater(tl.reorderList, tc.kind, s.lid, tc.lid, true) }
                        }
                        Rectangle { visible: tbefore.containsDrag; x: 1; y: 18; width: 4; height: parent.height - 36; radius: 2
                                    color: "#e6e6e6"; z: 4 }
                        Rectangle { visible: tdrop.containsDrag && !tbefore.containsDrag && !tafter.containsDrag   // merge
                                    x: 4; y: 4; width: parent.width - 8; height: parent.height - 8; radius: 18; z: 4
                                    color: "transparent"; border.width: 2; border.color: T.text }
                        Rectangle { visible: tafter.containsDrag; x: parent.width - 5; y: 18; width: 4; height: parent.height - 36
                                    radius: 2; color: "#e6e6e6"; z: 4 }
                        DropArea {   // drag another list into the middle = merge
                            id: tdrop
                            anchors.fill: parent
                            keys: ["tlist"]
                            enabled: !tc.modelData["new"] && !tdrag.active
                            onDropped: function (ev) {
                                var s = drag.source
                                if (!s || s === tc) return
                                var key = "merge:" + tc.kind + ":" + tc.lid
                                Qt.callLater(function () { tl.listAction(s.kind, s.lid, key) })
                            }
                        }
                        Rectangle {
                            id: tile
                            x: 6; y: 6; width: parent.width - 12; height: parent.height - 12
                            radius: 16; clip: true
                            opacity: tdrag.active ? 0.7 : 1
                            scale: tdrag.active ? 0.9 : 1
                            Behavior on scale { NumberAnimation { duration: 150 } }
                            color: tch.hovered || tdrop.containsDrag ? T.surface2 : T.surface
                            border.width: tdrop.containsDrag ? 2 : 1
                            border.color: tdrop.containsDrag ? T.text : (tch.hovered ? T.text2 : T.line)
                            HoverHandler { id: tch; cursorShape: Qt.PointingHandCursor }
                            TapHandler {
                                enabled: !tAsk.open
                                onTapped: function (ev) {
                                    var p = ev.position   // click on „⋯“ only opens the menu, not the list
                                    if (tmBtn.visible && p.x >= tmBtn.x - 4 && p.y <= tmBtn.y + tmBtn.height + 4) return
                                    if (!tc.modelData["new"] && p.y <= 36 && p.x <= tchips.x + tchips.width + 4) return   // chips
                                    if (tc.modelData["new"]) { tc.newGame = tp.gameKey; tc.newShared = false
                                                               tAsk.start("new", "", shell.text("Name of the new list"), "", shell.text("Create")) }
                                    else tl.openList(me.fold, tc.modelData.lid)
                                }
                            }
                            // „+ New list“ / rename: the tile itself turns into the field (no dialog)
                            InlineAsk {
                                id: tAsk
                                anchors.fill: parent; fill: true; z: 5
                                placeholder: shell.text("Name")
                                onAccepted: function (mode, ident, text) {
                                    if (mode === "new") tl.newListFull(me.fold, text, tc.newGame, tc.newShared)
                                    else tl.renameListTo(me.fold, ident, text)
                                }
                                extra: Component { Column {   // (built only while open)
                                    spacing: 8
                                    Seg {   // for which game – only those with several see the choice
                                        visible: tAsk.mode === "new" && tl.listGames.length > 1
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        items: tl.listGames; current: tc.newGame
                                        onPicked: function (k) { tc.newGame = k }
                                    }
                                    Seg {   // trade list: by hand / automatic (automatic comes later – greyed out)
                                        visible: tAsk.mode === "new" && me.fold === "have"
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        items: [{"key": "hand", "text": shell.text("by hand")},
                                                {"key": "auto", "text": shell.text("automatic"), "disabled": true,
                                                 "tip": shell.text("Coming soon: lists that fill themselves")}]
                                        current: "hand"
                                    }
                                    Seg {   // default: private (tile is narrow: „shared“)
                                        visible: tAsk.mode === "new" && me.fold !== "custom"
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        items: [{"key": "p", "text": shell.text("private")},
                                                {"key": "s", "text": shell.text("shared"),
                                                 "tip": shell.text("shared with friends – encrypted, visible only to them")}]
                                        current: tc.newShared ? "s" : "p"
                                        onPicked: function (k) { tc.newShared = k === "s" }
                                    }
                                } }
                                Rectangle { anchors.fill: parent; z: -1; radius: 16; color: Qt.lighter(T.surface, 1.25)
                                            border.width: 1; border.color: T.line2 }
                            }
                            readonly property bool wantRename: page.renameLid !== "" && page.renameLid === (tc.modelData.lid || "x")
                            onWantRenameChanged: if (wantRename) {
                                page.renameLid = ""
                                tname.start()   // the name on the tile becomes the field (review .101)
                            }
                            // „+ New list“
                            Column {
                                visible: tc.modelData["new"] === true
                                anchors.centerIn: parent; spacing: 6
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "+"; color: tch.hovered ? T.text : T.dim
                                       font.family: T.font; font.pixelSize: 56; font.bold: true }
                                Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("New list")
                                       color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
                            }
                            // list: image of the most valuable card, name, count · value
                            Item {
                                visible: !tc.modelData["new"]
                                anchors.fill: parent
                                Item {
                                    id: artBox
                                    width: parent.width; height: parent.height * 0.58
                                    clip: true
                                    Rectangle { anchors.fill: parent; color: Qt.darker(T.surface, 1.3) }
                                    Image {
                                        visible: (tc.modelData.art || "") !== ""
                                        source: tc.modelData.art || ""
                                        width: parent.width * 1.35; height: width * 88 / 63
                                        x: (parent.width - width) / 2; y: -height * 0.12
                                        fillMode: Image.PreserveAspectCrop; asynchronous: true; smooth: true
                                        sourceSize.width: 488
                                    }
                                    NavIcon { visible: (tc.modelData.art || "") === ""; anchors.centerIn: parent; s: 1.6
                                              key: me.cur.icon; color: T.line2 }
                                    ArtistTag { name: (tc.modelData.art || "") !== "" ? (tc.modelData.artist || "") : ""
                                                anchors.bottomMargin: 10; z: 2 }
                                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 40
                                                gradient: Gradient { GradientStop { position: 0; color: "transparent" }
                                                                     GradientStop { position: 1; color: tch.hovered ? T.surface2 : T.surface } } }
                                }
                                Column {
                                    x: 14; y: artBox.height + 4; width: parent.width - 28; spacing: 3
                                    RenameField {   // click on the name = rename right here (review .101)
                                        id: tname
                                        z: 30
                                        width: Math.min(implicitWidth, parent.width); height: 22
                                        text: tc.modelData.name || ""; pixelSize: 16; bold: true
                                        canEdit: (tc.modelData.lid || "") !== ""
                                        commit: function (v) { tl.renameListTo(me.fold, tc.modelData.lid, v); return true }
                                    }
                                    Text { width: parent.width; elide: Text.ElideRight; text: tc.modelData.info || ""
                                           color: T.muted; font.family: T.font; font.pixelSize: 13 }
                                    Text { visible: (tc.modelData.friends || "") !== ""; width: parent.width; elide: Text.ElideRight
                                           text: tc.modelData.friends || ""; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                                }
                                Row {   // top left: example / alert / automatic / private · shared
                                    id: tchips
                                    x: 10; y: 10; spacing: 6
                                    Rectangle { visible: tc.modelData.example === true; width: ext.implicitWidth + 16; height: 22; radius: 11
                                                color: Qt.rgba(0.04, 0.04, 0.04, 0.78); border.width: 1; border.color: Qt.rgba(0.8, 0.8, 0.8, 0.5)
                                                Text { id: ext; anchors.centerIn: parent; text: shell.text("EXAMPLE"); color: "#dedede"
                                                       font.family: T.font; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.2 } }
                                    Rectangle { visible: tc.modelData.alarm === true; width: 26; height: 22; radius: 11; color: "#dedede"
                                                NavIcon { anchors.centerIn: parent; key: "bell"; s: 0.6; color: T.onHi } }
                                    Rectangle { visible: tc.modelData.auto === true
                                                width: aux.implicitWidth + 16; height: 22; radius: 11
                                                color: Qt.rgba(0.04, 0.04, 0.04, 0.78); border.width: 1; border.color: Qt.rgba(0.8, 0.8, 0.8, 0.35)
                                                Text { id: aux; anchors.centerIn: parent; text: shell.text("automatic"); color: "#a6a6a6"
                                                       font.family: T.font; font.pixelSize: 11; font.bold: true } }
                                    Rectangle {   // click: private <-> shared with friends
                                                visible: tc.modelData.shareable === true && tc.modelData.example !== true
                                                width: shx.implicitWidth + 16; height: 22; radius: 11
                                                color: shh.hovered ? Qt.rgba(0.2, 0.2, 0.2, 0.9) : Qt.rgba(0.04, 0.04, 0.04, 0.78)
                                                border.width: 1; border.color: tc.modelData.shared ? "#dedede" : Qt.rgba(0.8, 0.8, 0.8, 0.35)
                                                Text { id: shx; anchors.centerIn: parent
                                                       text: tc.modelData.shared ? shell.text("shared with friends") : shell.text("private")
                                                       color: tc.modelData.shared ? "#ececec" : "#a6a6a6"
                                                       font.family: T.font; font.pixelSize: 11; font.bold: true }
                                                HoverHandler { id: shh; cursorShape: Qt.PointingHandCursor
                                                    onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 2)
                                                        shell.tip(tc.modelData.shared ? shell.text("Click: private") : shell.text("Click: share with friends"), p.x, p.y) }
                                                        else shell.tip("", 0, 0) }
                                                TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds
                                                             onTapped: { shell.tip("", 0, 0); tf.setShared(me.fold, tc.modelData.lid, !tc.modelData.shared) } } }
                                }
                                Rectangle {   // menu „⋯“ on hover – flat, semi-transparent (as with the decks)
                                    id: tmBtn
                                    visible: tch.hovered
                                    x: tile.width - width - 10; y: 10; width: 34; height: 26; radius: 13
                                    color: Qt.rgba(0.04, 0.04, 0.04, tmh.hovered ? 0.92 : 0.72)
                                    border.width: 1.5; border.color: Qt.rgba(0.85, 0.85, 0.85, tmh.hovered ? 1 : 0.7)
                                    Text { anchors.centerIn: parent; text: "⋯"; color: "#ededed"; font.pixelSize: 16; font.bold: true }
                                    HoverHandler { id: tmh; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: { tmenu.kind = me.fold
                                                             tmenu.lid = tc.modelData.lid
                                                             tmenu.items = tl.listMenu(me.fold, tc.modelData.lid)
                                                             tmenu.openAt(tmBtn) } }
                                }
                            }
                        }
                    }
                }
                // folder „Binders“: same tiles as in the profile (all games) – click shows it large in the profile
                Loader {
                    active: me.fold === "binders"
                    asynchronous: true   // (built over a few frames – no stutter when switching)
                    y: fhead2.y + fhead2.height + 18
                    width: parent.width; height: parent.height - y
                    sourceComponent: Flickable {
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        contentHeight: tbg.implicitHeight + 20
                        BinderGrid { id: tbg; width: Math.min(parent.width - 14, 1100) }
                    }
                }
                // folder „Trade offers“: each offer with status, version, trade ID and replies (form from Python)
                Loader {
                    active: me.fold === "offers"
                    asynchronous: true   // (built over a few frames – no stutter when switching)
                    y: fhead2.y + fhead2.height + 14
                    width: Math.min(parent.width, 980); height: parent.height - y
                    sourceComponent: Flickable {
                        clip: true
                        contentHeight: offersMirror.implicitHeight + 20
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollHint {}
                        Mirror { id: offersMirror; width: parent.width - 14; mirror: tp.offersForm }
                    }
                }
                // folder „Price alerts“: table in three sections (whole lists · wish cards · trade cards),
                // sortable via the column headers; click = detail view on the right, ✎ = editor expands in the row
                Loader {   // (built only while the folder is open)
                    active: me.fold === "alarms"
                    asynchronous: true   // (built over a few frames – no stutter when switching)
                    y: fhead2.y + fhead2.height + 14
                    width: parent.width; height: parent.height - y
                    sourceComponent: Item {
                    id: av
                    clip: true   // detail/compare slide in from the right
                    property string adding: ""   // "card" | "list" – the field expands in place
                    property string addErr: ""
                    readonly property real panelW: Math.max(360, Math.min(tp.tradeDetailWidth, (width - 620) / (ta.alarmCompareOpen ? 2 : 1)))
                    readonly property bool foreignOpen: tp.foreignCard.name !== undefined
                    property real detW: ta.alarmDetailOpen || foreignOpen ? panelW : 0
                    property real cmpW: ta.alarmCompareOpen && !foreignOpen ? panelW : 0
                    Behavior on detW { enabled: shell.animate; NumberAnimation { duration: 320 * shell.speed; easing.type: Easing.InOutCubic } }
                    Behavior on cmpW { enabled: shell.animate; NumberAnimation { duration: 320 * shell.speed; easing.type: Easing.InOutCubic } }
                    readonly property real mainW: width - detW - cmpW - (detW > 1 ? 14 : 0) - (cmpW > 1 ? 14 : 0)
                    // columns (shares of the table width)
                    readonly property real cName: 84
                    readonly property real cWhere: Math.max(cName + 160, mainW * 0.40)
                    readonly property real cNow: mainW * 0.62
                    readonly property real cRule: mainW * 0.74

                    // ---- new: card (type name) or list (click) ----
                    Row {
                        id: addRow
                        width: av.mainW; height: 38; spacing: 10
                        Item {
                            width: av.adding === "card" ? Math.min(460, av.mainW - 260) : cardBtn.implicitWidth + 30
                            Behavior on width { enabled: shell.animate; NumberAnimation { duration: 220 * shell.speed; easing.type: Easing.OutCubic } }
                            height: 38
                            Btn { id: cardBtn; anchors.fill: parent; visible: av.adding !== "card"; primary: true
                                  text: "+  " + shell.text("Alert for a card …")
                                  onClicked: { av.adding = "card"; av.addErr = ""; cardField.text = ""; cardField.focusAll() } }
                            SearchField {
                                id: cardField
                                anchors.fill: parent
                                visible: av.adding === "card"
                                placeholder: shell.text("Card name – e.g. Sol Ring")
                                onEdited: function (t) { sugTimer.q = t; sugTimer.restart(); av.addErr = "" }   // search only after a pause
                                Timer { id: sugTimer; property string q: ""; interval: 180
                                        onTriggered: sug.items = ta.alarmSuggest(q) }
                                onAccepted: { var e = sug.items.length ? ta.newCardAlarmIn(sug.items[0].name, sug.items[0].game || "")
                                                                       : ta.newCardAlarm(text)
                                              av.addErr = e; if (e === "") { av.adding = ""; sug.items = [] } }
                                Keys.onEscapePressed: { av.adding = ""; sug.items = [] }
                            }
                        }
                        Btn { visible: av.adding === "card"; height: 38; width: 110; text: shell.text("Cancel")
                              onClicked: { av.adding = ""; sug.items = []; av.addErr = "" } }
                        Btn { visible: av.adding !== "card"; height: 38; text: "+  " + shell.text("Alert for a list …")
                              active: av.adding === "list"
                              onClicked: av.adding = av.adding === "list" ? "" : "list" }
                        Text { visible: av.addErr !== ""; anchors.verticalCenter: parent.verticalCenter; text: av.addErr
                               color: "#d48a8a"; font.family: T.font; font.pixelSize: 13 }
                    }
                    // lists without an alert to click (expands below the buttons)
                    Item {
                        id: listPick
                        y: addRow.height + 8
                        width: av.mainW
                        height: av.adding === "list" ? lpFlow.implicitHeight + 16 : 0
                        Behavior on height { enabled: shell.animate; NumberAnimation { duration: 220 * shell.speed; easing.type: Easing.OutCubic } }
                        clip: true
                        Flow {
                            id: lpFlow
                            y: 4; width: parent.width; spacing: 8
                            Text { visible: ta.alarmListChoices.length === 0; text: shell.text("All lists already have an alert.")
                                   color: T.dim; font.family: T.font; font.pixelSize: 13 }
                            Repeater {
                                model: ta.alarmListChoices
                                Btn { required property var modelData
                                      height: 32; compact: true; width: implicitWidth + 30
                                      text: (modelData.chip ? modelData.chip + "  ·  " : "") + modelData.name + "  ·  " + modelData.kind
                                      onClicked: { av.adding = ""; ta.newListAlarm(modelData.key) } }
                            }
                        }
                    }
                    // search, games (chips), plus sorting: by game / triggered first (combinable with the column)
                    Flow {
                        id: afilter
                        y: listPick.y + listPick.height + 8
                        width: av.mainW; spacing: 10
                        SearchField { width: 240; height: 30; placeholder: shell.text("Search alerts …")
                                      onEdited: function (t) { ta.setAlarmQuery(t) } }
                        Seg { visible: ta.alarmGames.length > 0; items: ta.alarmGames; multi: ta.alarmGamesOn
                              onPicked: function (k) { ta.toggleAlarmGame(k) } }
                        Seg { items: [{"key": "game", "text": shell.text("by game")},
                                      {"key": "hits", "text": shell.text("triggered first")}]
                              multi: ta.alarmSortBy
                              onPicked: function (k) { ta.toggleAlarmSortBy(k) } }
                    }
                    // column headers (clickable = sort)
                    Item {
                        id: thead
                        y: afilter.y + afilter.height + 8
                        width: av.mainW; height: 28
                        visible: ta.alarmSections.length > 0
                        Repeater {
                            model: [{"k": "name", "t": shell.text("Card / list"), "x": av.cName},
                                    {"k": "where", "t": shell.text("What"), "x": av.cWhere},
                                    {"k": "now", "t": shell.text("Now"), "x": av.cNow},
                                    {"k": "rule", "t": shell.text("Alert"), "x": av.cRule}]
                            Text {
                                required property var modelData
                                x: modelData.x; anchors.verticalCenter: parent.verticalCenter
                                text: modelData.t.toUpperCase() + (ta.alarmSort === modelData.k ? (ta.alarmSortDesc ? "  ↓" : "  ↑") : "")
                                color: ta.alarmSort === modelData.k || hh.hovered ? T.text : T.muted
                                font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2
                                HoverHandler { id: hh; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: ta.setAlarmSort(parent.modelData.k) }
                            }
                        }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line }
                    }
                    Text {
                        visible: ta.alarmSections.length === 0
                        y: thead.y + 6; width: av.mainW; wrapMode: Text.Wrap
                        text: shell.text("No price alerts yet. Tip: click the bell in a card's detail view – or on any card in a list.")
                        color: T.dim; font.family: T.font; font.pixelSize: 14
                    }
                    Flickable {
                        ScrollHint {}
                        y: thead.y + thead.height + 6
                        width: av.mainW; height: av.height - y
                        contentHeight: secCol.implicitHeight + 20
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        Column {
                            id: secCol
                            width: parent.width; spacing: 18
                            Repeater {
                                model: ta.alarmSections
                                delegate: Item {   // one section each – list, wish and trade alerts: heading with a divider
                                    id: sec
                                    required property var modelData
                                    width: secCol.width; height: sc.implicitHeight + 20
                                    Rectangle { width: parent.width; height: 1; color: T.line }
                                    Column {
                                        id: sc
                                        x: 10; y: 10; width: parent.width - 20; spacing: 2
                                        Row {
                                            x: 6; height: 30; spacing: 10
                                            NavIcon { anchors.verticalCenter: parent.verticalCenter; s: 0.72; color: T.text2
                                                      key: sec.modelData.key === "list" ? "lists" : (sec.modelData.key === "wish" ? "star" : "trade") }
                                            Text { anchors.verticalCenter: parent.verticalCenter; text: sec.modelData.title
                                                   color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
                                            Text { anchors.verticalCenter: parent.verticalCenter; text: sec.modelData.sub
                                                   color: T.dim; font.family: T.font; font.pixelSize: 12 }
                                        }
                                        Repeater {
                                            model: sec.modelData.rows
                                            delegate: Rectangle {
                                                id: ar
                                                required property var modelData
                                                readonly property bool isOpen: ta.alarmOpenKeys.indexOf(modelData.key) >= 0
                                                width: sc.width; height: arCol.implicitHeight + (isOpen ? 4 : 0)
                                                radius: 12
                                                // expanded: row + editor one light box (they belong together)
                                                color: isOpen ? Qt.lighter(T.surface, 1.25) : "transparent"
                                                border.width: isOpen || modelData.hit ? 1 : 0; border.color: isOpen ? T.line2 : T.text2
                                                Behavior on color { ColorAnimation { duration: 220 } }
                                                Column {
                                                id: arCol
                                                width: parent.width
                                                Rectangle {
                                                    width: parent.width; height: 64; radius: 10
                                                    color: arh.hovered && !ar.isOpen ? T.surface2 : "transparent"
                                                    HoverHandler { id: arh; cursorShape: Qt.PointingHandCursor }
                                                    TapHandler { onTapped: ta.alarmClicked(ar.modelData.key) }
                                                    // image: for „cheapest print“ up to 9 prints as a fan – opens further on hover
                                                    Item {
                                                        id: stack
                                                        x: 14; y: 6; width: 60; height: 52
                                                        readonly property int n: ar.modelData.imgs.length
                                                        Rectangle {   // no image: empty card
                            visible: stack.n === 0
                            height: 50; width: 50 * 63 / 88; x: (stack.width - width) / 2; y: 1; radius: 3
                            color: Qt.darker(T.surface, 1.2); border.width: 1; border.color: T.line2
                            NavIcon { anchors.centerIn: parent; s: 0.55; key: ar.modelData.icon; color: T.line2 }
                        }
                                                        Repeater {
                                                            model: ar.modelData.imgs
                                                            Image {
                                                                required property var modelData
                                                                required property int index
                                                                source: modelData; asynchronous: true; smooth: true
                                                                sourceSize.height: 120
                                                                height: 50; width: 50 * 63 / 88
                                                                x: (stack.width - width) / 2; y: 1
                                                                transformOrigin: Item.Bottom
                                                                z: stack.n - index
                                                                rotation: (index - (stack.n - 1) / 2) * (arh.hovered ? 9 : 3.5)
                                                                Behavior on rotation { NumberAnimation { duration: 260; easing.type: Easing.OutBack } }
                                                            }
                                                        }
                                                    }
                                                    Row {
                                                        x: av.cName; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                                                        opacity: ar.modelData.other ? 0.6 : 1
                                                        Rectangle { visible: (ar.modelData.chip || "") !== ""; anchors.verticalCenter: parent.verticalCenter
                                                                    width: gch.implicitWidth + 12; height: 18; radius: 9
                                                                    color: "transparent"; border.width: 1; border.color: T.line2
                                                                    Text { id: gch; anchors.centerIn: parent; text: ar.modelData.chip || ""; color: T.text2
                                                                           font.family: T.font; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.8 } }
                                                        Text { width: av.cWhere - av.cName - 12 - (gch.parent.visible ? gch.parent.width + 8 : 0)
                                                               elide: Text.ElideRight; text: ar.modelData.name
                                                               color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true }
                                                    }
                                                    Text { x: av.cWhere; anchors.verticalCenter: parent.verticalCenter; width: av.cNow - av.cWhere - 12
                                                           elide: Text.ElideRight; text: ar.modelData.where
                                                           color: T.muted; font.family: T.font; font.pixelSize: 13 }
                                                    Text { x: av.cNow; anchors.verticalCenter: parent.verticalCenter; text: ar.modelData.now
                                                           color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
                                                    Text { x: av.cRule; anchors.verticalCenter: parent.verticalCenter
                                                           width: parent.width - av.cRule - (arh.hovered || ar.isOpen ? 90 : 12); elide: Text.ElideRight
                                                           text: (ar.modelData.hit ? "● " : "") + ar.modelData.rule
                                                           color: ar.modelData.hit ? T.text : (ar.modelData.draft ? T.dim : T.muted)
                                                           font.family: T.font; font.pixelSize: 13; font.italic: ar.modelData.draft }
                                                    Text { visible: ar.modelData.other === true && arh.hovered
                                                           anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                                                           text: shell.text("switch →"); color: T.muted; font.family: T.font; font.pixelSize: 12 }
                                                    Row {   // open: buttons always there (otherwise on hover)
                                                        visible: !ar.modelData.other && (arh.hovered || ar.isOpen)
                                                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                                                        spacing: 4
                                                        Btn { width: 34; height: 30; compact: true; text: "✎"; tip: shell.text("Change")
                                                              active: ar.isOpen
                                                              onClicked: ta.openAlarm(ar.modelData.key) }
                                                        Btn { visible: !ar.modelData.draft; width: 34; height: 30; compact: true; glyph: "trash"; danger: true
                                                              tip: shell.text("Delete alert"); onClicked: ta.deleteAlarm(ar.modelData.key) }
                                                    }
                                                }
                                                AlarmEditor { tp: page.tp; key: ar.modelData.key; width: parent.width }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    SuggestList {   // suggestions below the card field – above the table
                        id: sug
                        z: 50
                        x: 0; y: addRow.height + 4
                        width: Math.min(460, av.mainW - 260)
                        visible: av.adding === "card" && items.length > 0
                        onPicked: function (it) { var e = ta.newCardAlarmIn(it.name, it.game || ""); av.addErr = e
                                                  if (e === "") { av.adding = ""; items = [] } }
                    }
                    // as in the Library: full width right away (card at full size), only the layer slides in
                    Loader {   // (built only while it slides in or is open)
                        id: aDet
                        z: 3
                        x: av.width - av.detW
                        width: av.panelW; height: av.height
                        active: av.detW > 1 && !av.foreignOpen
                        sourceComponent: DetailView {
                            det: ta.alarmDetail
                            holdCard: av.detW < av.panelW - 1
                        }
                    }
                    // card of another game (or without a print online): just the card – without switching
                    Rectangle {
                        z: 4
                        visible: av.foreignOpen && av.detW > 1
                        x: av.width - av.detW; width: av.panelW; height: av.height
                        radius: 16; color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
                        Row {
                            x: 16; y: 14; spacing: 8; width: parent.width - 70
                            Rectangle { visible: tp.foreignCard.other === true; anchors.verticalCenter: parent.verticalCenter
                                        width: fch.implicitWidth + 12; height: 18; radius: 9
                                        color: "transparent"; border.width: 1; border.color: T.line2
                                        Text { id: fch; anchors.centerIn: parent; text: tp.foreignCard.chip || ""; color: T.text2
                                               font.family: T.font; font.pixelSize: 10; font.bold: true } }
                            Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - 60; elide: Text.ElideRight
                                   text: tp.foreignCard.name || ""; color: T.text; font.family: T.font; font.pixelSize: 19; font.bold: true }
                        }
                        Btn { x: parent.width - 46; y: 10; width: 34; height: 32; compact: true; glyph: "close"
                              tip: shell.text("Close"); onClicked: tp.closeForeign() }
                        Text { x: 16; y: 46; width: parent.width - 32; elide: Text.ElideRight
                               text: (tp.foreignCard.line || "") + "  ·  " + (tp.foreignCard.price || "")
                               color: T.muted; font.family: T.font; font.pixelSize: 13 }
                        Item {
                            id: fimg
                            x: 16; y: 74; width: parent.width - 32
                            height: Math.min(parent.height - y - 70, width * 88 / 63)
                            readonly property real cw: height * 63 / 88
                            NoImage {   // no image: crossed-out card ("Image not available" at this size)
                                visible: (tp.foreignCard.img || "") === "" || fimgI.status === Image.Error
                                width: fimg.cw; height: fimg.height; x: (fimg.width - width) / 2; radius: 14
                            }
                            Rectangle {   // still loading: empty card with the name
                                visible: (tp.foreignCard.img || "") !== "" && fimgI.status === Image.Loading
                                width: fimg.cw; height: fimg.height; x: (fimg.width - width) / 2; radius: 14
                                color: Qt.darker(T.surface, 1.25); border.width: 1; border.color: T.line2
                                Text { anchors.centerIn: parent; width: parent.width - 40; horizontalAlignment: Text.AlignHCenter
                                       wrapMode: Text.Wrap; text: tp.foreignCard.name || ""; color: T.dim
                                       font.family: T.font; font.pixelSize: 15; font.bold: true }
                            }
                            Image {
                                id: fimgI
                                visible: (tp.foreignCard.img || "") !== ""
                                source: tp.foreignCard.img || ""
                                width: fimg.cw; height: fimg.height; x: (fimg.width - width) / 2
                                fillMode: Image.PreserveAspectFit; asynchronous: true; smooth: true; sourceSize.height: 680
                            }
                        }
                        Btn { visible: tp.foreignCard.other === true
                              x: 16; y: parent.height - 52; height: 36; width: parent.width - 32
                              text: shell.text("Open in ") + (tp.foreignCard.nick || "") + shell.text(" →")
                              tip: shell.text("Switches the game – price alerts stay open")
                              onClicked: tp.foreignSwitch() }
                    }
                    Loader {
                        z: 2   // slides out from behind the detail view
                        x: aDet.x - av.cmpW - (av.cmpW > 1 ? 14 * Math.min(1, av.cmpW / 40) : 0)
                        width: av.panelW; height: av.height
                        active: av.cmpW > 1
                        sourceComponent: DetailView {
                            det: ta.alarmCompare
                            holdCard: av.cmpW < av.panelW - 1
                        }
                    }
                    Shortcut { sequence: "Escape"; enabled: av.visible && page.visible && (ta.alarmDetailOpen || av.foreignOpen)
                               onActivated: av.foreignOpen ? tp.closeForeign() : ta.alarmEscape() }
                    }
                }
                // undo after copy / move / merge / clear
                Rectangle {
                    id: tundo
                    visible: tp.undoText !== "" && me.fold !== "alarms"
                    y: parent.height - height; width: Math.min(parent.width, 600); height: 40
                    radius: 10; color: T.surface2; border.width: 1; border.color: T.line2
                    Text { x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 140; elide: Text.ElideRight
                           text: tp.undoText; color: T.text2; font.family: T.font; font.pixelSize: 13 }
                    Btn { anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                          height: 28; width: 120; compact: true; text: "↺  " + shell.text("Undo"); onClicked: tp.undo() }
                }
            }
        }

        // ================= List editor =================
        ViewPane {
            id: editor
            anchors.fill: parent
            shown: tp.view === "editor"
            lazy: Component { Item {   // content only when shown (see ViewPane.lazy)
            Component.onCompleted: { ghost.dropList = listPanel; ghost.dropEdit = edView }   // target for dragging
            Btn { id: backBtn; height: 34; width: 170; compact: true; backDir: -1; text: shell.text("Your lists")
                  onClicked: tl.backToLists() }
            Rectangle {
                id: listPanel
                y: backBtn.height + 10
                width: Math.max(420, Math.min(560, editor.width * 0.36)); height: editor.height - y
                radius: 16
                color: Qt.darker(T.surface, 1.1)
                border.width: 1; border.color: dropHere ? T.text2 : T.line
                readonly property bool dropHere: ghost.visible && ghost.fromGrid && ghost.over(listPanel)
                Rectangle {   // header + expanded list alert belong together: one light box
                    x: 6; y: 4; width: parent.width - 12; height: listEd.y + listEd.height - 4 + (listEd.open ? 6 : 4)
                    radius: 12
                    color: listEd.open ? Qt.lighter(T.surface, 1.25) : "transparent"
                    border.width: listEd.open ? 1 : 0; border.color: T.line2
                    Behavior on color { ColorAnimation { duration: 220 } }
                }
                Text { id: lt; x: 14; y: 14; width: lshare.x - x - 10; elide: Text.ElideRight
                       text: tl.listTitle; color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
                Seg {
                    id: lshare
                    visible: tf.listShareable
                    x: (tf.listShareable ? parent.width - 54 - width : parent.width - 54); y: 8
                    items: [{"key": "p", "text": shell.text("private")},
                            {"key": "s", "text": shell.text("shared with friends"),
                             "tip": shell.text("Friends see the list – encrypted, visible only to them")}]
                    current: tf.listShared ? "s" : "p"
                    onPicked: function (k) { tf.setListShared(k === "s") }
                }
                Btn { x: parent.width - 46; y: 8; width: 34; height: 28; compact: true; glyph: "bell"; inverted: ta.listAlarmOn
                      tip: ta.listAlarmOn ? shell.text("Price alert for the whole list – click: change")
                                          : shell.text("Price alert for the whole list")
                      onClicked: ta.editorListAlarm() }
                Text { id: li; x: 14; y: 48; text: tl.listInfo; color: T.muted; font.family: T.font; font.pixelSize: 13 }
                DropList {   // order cards in the list (last added, name, price, set, count – again = reverse)
                    id: lsort
                    x: parent.width - width - 12; y: 42
                    height: 28; width: 200; minWidth: 200
                    items: tl.listSorts; current: tl.listSort
                    directional: true; dir: tl.listSortDir; reversed: tl.listSortReversed
                    onPicked: function (k) { tl.setListSort(k) }
                    onPickedDir: function (k, d) { tl.setListSortDir(k, d) }
                    onReverse: tl.toggleListSortDir()
                }
                AlarmEditor { id: listEd; x: 6; y: lsort.y + lsort.height + 8; width: parent.width - 12; tp: page.tp; key: ta.editorAlarmKey
                              fadeColor: Qt.lighter(T.surface, 1.25) }
                ListView {
                    ScrollHint {}
                    EdgeFade { color: Qt.darker(T.surface, 1.1) }
                    id: entries
                    x: 6; y: listEd.y + listEd.height + 10
                    width: parent.width - 12; height: parent.height - y - hint.height - 18
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    // rows stay, only the values change (otherwise every +/− would rebuild everything – the
                    // drawn pins flickered)
                    model: tp.entries.length
                    reuseItems: true   // scrolling hands a row that leaves to the one coming in (no new build)
                    delegate: Rectangle {
                        id: er
                        required property int index
                        readonly property var modelData: tp.entries[index] || ({})
                        readonly property real baseH: (er.modelData.alarm || "") !== "" ? 50 : 40
                        readonly property bool picking: tp.printPick !== "" && tp.printPick === er.modelData.key
                        readonly property bool unfolded: erEd.open || picking
                        // a reused row starts like a new one: no animation from the entry it showed before (a print
                        // choice or alert editor closing would show the other card's content for a moment)
                        // (switched off when the row goes into the pool – Qt gives it its new entry before onReused)
                        property bool reused: false
                        ListView.onPooled: reused = true
                        ListView.onReused: { pick.mode = "pin"; Qt.callLater(function () { er.reused = false }) }
                        width: entries.width; height: baseH + pick.height + erEd.height + (unfolded ? 4 : 0); radius: 10
                        // expanded (prints / alert): row + content as one light box
                        color: unfolded ? Qt.lighter(T.surface, 1.25) : (erh.hovered ? T.surface2 : "transparent")
                        border.width: unfolded ? 1 : 0; border.color: T.line2
                        Behavior on color { enabled: !er.reused; ColorAnimation { duration: 220 } }
                        readonly property color ink: modelData.missing ? "#d48a8a" : T.text
                        HoverHandler { id: erh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: function (ev) { if (ev.position.y <= er.baseH) tp.entryClicked(er.modelData.key) } }
                        Item {   // prints to pin / as another version
                            id: pick
                            y: er.baseH; x: 8; width: er.width - 16
                            height: er.picking ? pick.pickH + 10 : 0
                            Behavior on height { enabled: shell.animate && !er.reused; NumberAnimation { duration: 240 * shell.speed; easing.type: Easing.OutCubic } }
                            clip: true
                            property string mode: "pin"
                            readonly property real pickH: pickLd.item ? pickLd.item.implicitHeight : 0
                            Loader {   // built only while this row picks a print (every row had Seg + PrintPicker: scrolling stalled)
                                id: pickLd
                                width: parent.width
                                active: er.picking || pick.height > 0.5
                                sourceComponent: Column {
                                id: pickCol
                                width: parent.width; spacing: 6
                                opacity: er.picking ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: 200 } }
                                Flow {
                                    width: parent.width; spacing: 6
                                    Seg { items: [{"key": "pin", "text": shell.text("pin this row")}, {"key": "add", "text": shell.text("add as another version")}]
                                          current: pick.mode; onPicked: function (k) { pick.mode = k } }
                                    Btn { visible: er.modelData.pinned === true; height: 24; compact: true; width: implicitWidth + 20
                                          text: shell.text("any version"); onClicked: tp.pickPrint(er.modelData.key, "", "any") }
                                }
                                PrintPicker {
                                    width: parent.width
                                    fadeColor: Qt.lighter(T.surface, 1.25)
                                    prints: er.picking ? tp.printPickRows : []
                                    onPicked: function (id) { tp.pickPrint(er.modelData.key, id, pick.mode) }
                                }
                                }
                            }
                        }
                        AlarmEditor { id: erEd; y: er.baseH + pick.height; x: 0; width: er.width; tp: page.tp; key: er.modelData.alarmKey || ""
                                      instant: er.reused
                                      fadeColor: Qt.lighter(T.surface, 1.25) }
                        DragHandler {   // drag an entry back onto the grid = remove from the list
                            target: null; dragThreshold: 12
                            property point last
                            onCentroidChanged: if (active) { last = centroid.scenePosition; ghost.move(er.modelData.key, "", last.x, last.y, false, er.modelData.name) }
                            onActiveChanged: if (!active) ghost.drop(last.x, last.y)
                        }
                        Row {
                            id: hold
                            x: 8; y: (er.baseH - height) / 2
                            spacing: -6
                            Repeater { model: er.modelData.holders || []
                                Image { required property var modelData; height: 22; width: 22 * 63 / 88; source: modelData.img; sourceSize.height: 88 } }
                        }
                        Text {
                            x: 8 + (hold.width > 0 ? hold.width + 6 : 0); y: (er.baseH - height) / 2
                            width: parent.width - x - 190; elide: Text.ElideRight
                            textFormat: Text.StyledText
                            text: er.modelData.name + "  ·  " + er.modelData.extra
                                  + (er.modelData.alarm ? "<br><font color='" + T.dim + "'>" + shell.text("Alert") + ": " + er.modelData.alarm + "</font>" : "")
                            color: er.ink; font.family: T.font; font.pixelSize: 13
                        }
                        Text { anchors.right: parent.right; anchors.rightMargin: 156; y: (er.baseH - height) / 2
                               text: er.modelData.count + "×"; color: er.ink; font.family: T.font; font.pixelSize: 13; font.bold: true }
                        Row {
                            anchors.right: parent.right; anchors.rightMargin: 4; y: (er.baseH - height) / 2
                            spacing: 2
                            Btn { width: 26; height: 26; compact: true; text: "−"; tip: shell.text("One less"); onClicked: tp.change(er.modelData.key, -1) }
                            Btn { width: 26; height: 26; compact: true; text: "+"; enabled: er.modelData.plusOk !== false
                                  tip: er.modelData.plusOk === false ? shell.text("All your copies are already on the list") : shell.text("One more")
                                  onClicked: tp.change(er.modelData.key, 1) }
                            Item {
                                width: 26; height: 26
                                NavIcon { anchors.centerIn: parent; width: 16; height: 16; key: er.modelData.pinned ? "pinOn" : "pin"
                                          color: er.modelData.missing ? "#d48a8a" : (er.modelData.pinned ? T.hi : (ph.hovered && er.modelData.pinEnabled ? "#9a9a9a" : "#5e5e5e"))
                                          play: ph.hovered && er.modelData.pinEnabled }
                                Rectangle { anchors.fill: parent; radius: 8; color: er.picking ? T.button : "transparent" }
                                HoverHandler { id: ph; cursorShape: er.modelData.pinEnabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(er.modelData.pinTip, p.x, p.y) } else shell.tip("", 0, 0) }
                                TapHandler { enabled: er.modelData.pinEnabled; gesturePolicy: TapHandler.ReleaseWithinBounds
                                             onTapped: tp.openPrintPick(er.modelData.key) }
                            }
                            Btn { enabled: er.modelData.canAlarm === true; width: 26; height: 26; compact: true
                                  glyph: "bell"; inverted: (er.modelData.alarm || "") !== ""
                                  tip: er.modelData.alarm ? shell.text("Price alert: ") + er.modelData.alarm : shell.text("Price alert for this card")
                                  onClicked: ta.entryAlarm(er.modelData.key) }
                            Btn { width: 26; height: 26; compact: true; text: "✕"; danger: true
                                  tip: shell.text("Remove from the list"); onClicked: tp.change(er.modelData.key, 0) }
                        }
                    }
                }
                Text { id: hint; x: 14; width: parent.width - 28; anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                       text: tl.listHint; wrapMode: Text.Wrap; color: T.dim; font.family: T.font; font.pixelSize: 12 }
            }
            Loader {   // grid only while a list is being edited (saves memory, no building in the background)
                id: edView
                x: listPanel.width + 10; y: listPanel.y - 14
                width: editor.width - x; height: editor.height - y
                active: tp.view === "editor"
                sourceComponent: Component {
                    LibraryView {
                        lib: tp.edLib
                        pad: 6
                        gridMinimum: 400
                        draggable: true
                        onTileDoubleClicked: function (i) { tp.addFromGrid(i) }
                        onTileDragMoved: function (i, img, sx, sy) { ghost.move(i, img, sx, sy, true, "") }
                        onTileDropped: function (i, sx, sy) { ghost.drop(sx, sy) }
                    }
                }
            }
            Rectangle {   // entry is being dragged onto the grid: highlight the grid slightly
                x: edView.x; y: edView.y; width: edView.width; height: edView.height
                radius: 16; color: "transparent"
                border.width: 2; border.color: T.text2
                visible: ghost.visible && !ghost.fromGrid && ghost.over(edView)
            }
            } }   // lazy
        }

        // ================= Friend =================
        ViewPane {
            id: friend
            anchors.fill: parent
            shown: tp.view === "friend"
            lazy: Component { Item {   // content only when shown (see ViewPane.lazy)
            Item {   // header: who + tabs (beside, or below if too narrow) – below that THEIR games as toggles
                id: fhead
                readonly property bool fits: fwho.width + 20 + ftabs.width <= friend.width
                readonly property bool cardTab: tf.friendTab === "has" || tf.friendTab === "wants" || tf.friendTab === "library"
                readonly property real top2: fits ? 44 : 44 + 8 + 36
                // their games in the order of the game button at the top (+ installed / loading from there)
                readonly property var gameRow: {
                    var fg = tf.friendGames, ch = shell.gameChoices, out = []
                    for (var i = 0; i < ch.length; i++)
                        for (var j = 0; j < fg.length; j++)
                            if (fg[j].key === ch[i].key)
                                out.push({ key: fg[j].key, name: fg[j].name, on: fg[j].on, cards: fg[j].cards, icon: ch[i].icon,
                                           installed: ch[i].installed, loading: ch[i].loading, progress: ch[i].progress })
                    return out
                }
                readonly property bool showGames: cardTab && gameRow.length > 0
                width: friend.width; height: top2 + (showGames ? 12 + 36 : 0)
            Row {
                id: fwho
                height: 44; spacing: 10
                Image { height: 40; width: 40 * 63 / 88; anchors.verticalCenter: parent.verticalCenter
                        source: tf.friendBack; sourceSize.height: 88; smooth: true }
                Text { anchors.verticalCenter: parent.verticalCenter; text: tf.friendName
                       color: T.text; font.family: T.font; font.pixelSize: 19; font.bold: true }
                Text { anchors.verticalCenter: parent.verticalCenter; text: tf.foreign === "" ? tf.friendInfo : ""
                       color: T.muted; font.family: T.font; font.pixelSize: 13 }
            }
            Row {
                id: ftabs
                spacing: 10
                x: fhead.fits ? fwho.width + 20 : 0; y: fhead.fits ? 4 : 44 + 8
                Repeater {
                    model: tf.friendTabs
                    Btn { required property var modelData
                          height: 36; width: Math.max(84, implicitWidth + 18)
                          text: modelData.text; checkable: true; checked: tf.friendTab === modelData.key
                          onClicked: tf.setFriendTab(modelData.key) }
                }
            }
            Row {   // games: one at a time (a click chooses) – with ∞ on several at once (toggles, mixed); dim + ↓ = not installed yet
                id: fgames
                visible: fhead.showGames
                y: fhead.top2 + 12; height: 36; spacing: 8
                Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("GAMES")
                       color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.5 }
                Repeater {
                    model: fhead.gameRow
                    Btn { id: gchip
                          required property var modelData
                          height: 36; width: implicitWidth + 22 + (modelData.installed ? 0 : 26)
                          iconSource: modelData.icon || ""
                          text: modelData.name + (modelData.loading ? "  " + Math.round((modelData.progress || 0) * 100) + " %"
                                                  : (modelData.cards > 0 ? "  ·  " + modelData.cards : ""))
                          checkable: true; checked: modelData.on
                          opacity: modelData.installed ? 1 : 0.6
                          Text {   // not installed: a small orange arrow inside on the right (covers nothing)
                              visible: !gchip.modelData.installed
                              anchors.right: gchip.right; anchors.rightMargin: 11; anchors.verticalCenter: gchip.verticalCenter
                              text: "↓"; color: "#ffa24a"; font.family: T.font; font.pixelSize: 14; font.bold: true }
                          tip: !modelData.installed ? modelData.name + " " + shell.text("isn't installed on your PC – switch it on to download it.")
                               : !tf.friendMulti ? (modelData.on ? "" : shell.text("Click: show this game instead"))
                               : modelData.on ? shell.text("Click: hide this game") : shell.text("Click: show this game too (several = mixed)")
                          onClicked: tf.toggleFriendGame(modelData.key) }
                }
                Rectangle {   // divider as between the tabs at the top
                    visible: fhead.gameRow.length > 1
                    anchors.verticalCenter: parent.verticalCenter
                    width: 5; height: 5; radius: 2.5; color: T.line2
                }
                Btn {   // multi-game view: all their games at once – orange on purpose (like the hint dots), the one colour in the row
                    visible: fhead.gameRow.length > 1
                    height: 36; width: implicitWidth + 22
                    text: "∞  " + shell.text("Multi-game view"); alertInk: "#ffa24a"
                    checkable: true; checked: tf.friendMulti
                    tip: tf.friendMulti ? shell.text("Back to one game") : shell.text("All their games at once")
                    onClicked: tf.setFriendMulti(!tf.friendMulti)
                }
                Text { visible: tf.friendMixed; anchors.verticalCenter: parent.verticalCenter; leftPadding: 6
                       text: "∞  " + shell.text("Mixed – advanced search only with one game")
                       color: T.muted; font.family: T.font; font.pixelSize: 12 }
            }
            }
            ForeignFriend {   // other game or several games: plain view (cards of the open tab)
                visible: tf.foreign !== "" && (fhead.cardTab || tf.friendTab === "trade")
                y: fhead.height + 10
                width: friend.width; height: friend.height - y
                tp: tradePage
            }
            Item {
                id: fbody
                visible: !(tf.foreign !== "" && (fhead.cardTab || tf.friendTab === "trade"))
                y: fhead.height + 10
                width: friend.width; height: friend.height - y

                // ---- Trade ----
                Item {
                    id: tradeTab
                    clip: true
                    anchors.fill: parent
                    visible: tf.friendTab === "trade"
                    readonly property real panelW: Math.max(360, Math.min(tp.tradeDetailWidth, (width - 560) / (tp.tradeCompareOpen ? 2 : 1)))
                    property real detW: tp.tradeDetailOpen ? panelW : 0
                    property real cmpW: tp.tradeCompareOpen ? panelW : 0
                    Behavior on detW { enabled: shell.animate; NumberAnimation { duration: 320 * shell.speed; easing.type: Easing.InOutCubic } }
                    Behavior on cmpW { enabled: shell.animate; NumberAnimation { duration: 320 * shell.speed; easing.type: Easing.InOutCubic } }
                    readonly property real mainW: width - detW - cmpW - (detW > 1 ? 14 : 0) - (cmpW > 1 ? 14 : 0)
                    TradeBrowser {
                        id: getBox
                        width: (tradeTab.mainW - 14) / 2; height: tradeTab.height - sumBox.height - tradeTip.height - 18
                        br: tp.getSide
                        cols: width > 700 ? 4 : (width > 420 ? 3 : 2)
                        onCardClicked: function (i) { tp.getSide.click(i) }
                    }
                    Rectangle { x: getBox.width + 6; y: 12; width: 1; height: getBox.height - 24; color: T.line }   // get | give
                    TradeBrowser {
                        x: getBox.width + 14
                        width: getBox.width; height: getBox.height
                        br: tp.giveSide
                        cols: getBox.cols
                        onCardClicked: function (i) { tp.giveSide.click(i) }
                    }
                    Text {   // legal 03.11.2026 (minors): always there, grey, no start hint
                        id: tradeTip
                        x: 14; width: tradeTab.mainW - 28; y: sumBox.y - height - 6
                        wrapMode: Text.Wrap; color: T.muted; font.family: T.font; font.pixelSize: 12
                        text: shell.text("Tip: Trade only with people you know and check the value first. Don't give your address to people you only know online. If you're under 18, talk to your parents first.")
                    }
                    Rectangle {
                        id: sumBox
                        y: tradeTab.height - height
                        width: tradeTab.mainW - offer.width - book.width - cash.width - 36; height: 46
                        color: "transparent"
                        Rectangle { width: parent.width; height: 1; color: T.line }   // divider instead of a frame
                        Text { x: 14; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 28
                               text: tp.tradeSum; textFormat: Text.StyledText; elide: Text.ElideRight
                               color: T.text; font.family: T.font; font.pixelSize: 14 }
                    }
                    Btn {
                        id: cash
                        x: sumBox.width + 12; y: sumBox.y; height: 46; width: tp.priced ? 120 : -12   // Orbit's Core: no money
                        visible: tp.priced
                        text: tp.money > 0.004 ? "+ " + tp.money.toFixed(2).replace(".", ",") + " €"
                            : tp.money < -0.004 ? "− " + (-tp.money).toFixed(2).replace(".", ",") + " €" : shell.text("Add € …")
                        tip: shell.text("Money in the trade: + you pay extra, − you get money")
                        onClicked: tp.moneyDialog()
                    }
                    Btn {
                        id: book
                        x: cash.x + cash.width + 12; y: sumBox.y; height: 46; width: 170
                        text: shell.text("Book directly …")
                        enabled: tp.canOffer
                        tip: shell.text("Book right away without a ticket (e.g. when you sit together): given cards leave your collection, the new ones arrive as a log “Trade with …”. The usual way is “Share as ticket”.")
                        onClicked: tp.bookOffer()
                    }
                    Btn {
                        id: offer
                        x: book.x + book.width + 12; y: sumBox.y; height: 46; width: 200
                        text: tp.offerCtx !== "" ? shell.text("Share counteroffer …") : shell.text("Share as ticket …")
                        enabled: tp.canOffer
                        tip: shell.text("The checked cards of both sides as a trade ticket – to copy into WhatsApp/Discord or as PNG. Your partner loads it under Orbit → Import and books the trade with one click")
                        onClicked: tp.shareOffer()
                    }
                    DetailView {
                        id: tDet
                        z: 3
                        det: tp.tradeDetail
                        x: tradeTab.width - tradeTab.detW
                        width: tradeTab.panelW; height: tradeTab.height
                        visible: tradeTab.detW > 1
                        holdCard: tradeTab.detW < tradeTab.panelW - 1
                    }
                    DetailView {
                        z: 2
                        det: tp.tradeCompare
                        x: tDet.x - tradeTab.cmpW - (tradeTab.cmpW > 1 ? 14 * Math.min(1, tradeTab.cmpW / 40) : 0)
                        width: tradeTab.panelW; height: tradeTab.height
                        visible: tradeTab.cmpW > 1
                        holdCard: tradeTab.cmpW < tradeTab.panelW - 1
                    }
                    Shortcut { sequence: "Escape"; enabled: tradeTab.visible && page.visible && tp.tradeDetailOpen; onActivated: tp.tradeEscape() }
                }
                // ---- Wants / Has / Library ----
                // The grids of the friend tabs only exist while you look at them (Loader): before, all three
                // were always there – more memory, and with many cards the background build sometimes crashed
                Loader {
                    width: parent.width; y: -14; height: parent.height + 14
                    active: tp.view === "friend" && tf.foreign === "" && tf.friendTab === "wants"
                    visible: active
                    sourceComponent: Component { LibraryView { lib: tl.wantsLib; pad: 0; gridMinimum: 400 } }
                }
                Loader {
                    width: parent.width; y: -14; height: parent.height + 14
                    active: tp.view === "friend" && tf.foreign === "" && tf.friendTab === "has" && tf.hasNote === ""
                    visible: active
                    sourceComponent: Component { LibraryView { lib: tp.hasLib; pad: 0; gridMinimum: 400 } }
                }
                Loader {
                    anchors.fill: parent; anchors.topMargin: -14
                    active: tp.view === "friend" && tf.foreign === "" && tf.friendTab === "library" && tf.libNote === ""
                    visible: active
                    sourceComponent: Component { LibraryView { lib: tf.friendLib; pad: 0; gridMinimum: 400 } }
                }
                // ---- Note: only for you, never shared ----
                Item {   // click outside the field: stop writing (saved on leave)
                    visible: tf.friendTab === "note"
                    anchors.fill: parent
                    TapHandler { onTapped: { noteEd.focus = false; noteBox.forceActiveFocus() } }
                }
                Column {
                    id: noteBox
                    visible: tf.friendTab === "note"
                    anchors.fill: parent
                    spacing: 10
                    Text { width: parent.width; wrapMode: Text.Wrap
                           text: shell.text("Your note about this friend – only you see it, it is never shared.")
                           color: T.muted; font.family: T.font; font.pixelSize: 13 }
                    Rectangle {
                        width: Math.min(parent.width, 760); height: Math.max(180, Math.min(parent.height - 60, 420))
                        radius: 12; color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: noteEd.activeFocus ? T.text2 : T.line
                        Flickable {
                            id: noteFl
                            x: 12; y: 10; width: parent.width - 24; height: parent.height - 20
                            contentHeight: noteEd.implicitHeight; clip: true; boundsBehavior: Flickable.StopAtBounds
                            TextEdit {
                                id: noteEd
                                width: noteFl.width
                                height: Math.max(implicitHeight, noteFl.height)   // whole field clickable
                                Keys.onEscapePressed: { focus = false; noteBox.forceActiveFocus() }
                                onVisibleChanged: if (!visible && activeFocus) { tf.setFriendNote(text); focus = false }
                                wrapMode: TextEdit.Wrap; selectByMouse: true
                                color: T.text; selectionColor: T.line2; font.family: T.font; font.pixelSize: 15
                                text: tf.friendNote
                                onTextChanged: if (activeFocus) noteSave.restart()
                                onActiveFocusChanged: if (!activeFocus) tf.setFriendNote(text)
                                Text { visible: noteEd.text === ""; text: shell.text("Write a note …")
                                       color: T.dim; font: noteEd.font }
                            }
                        }
                        Timer { id: noteSave; interval: 700; onTriggered: tf.setFriendNote(noteEd.text) }
                        TapHandler { onTapped: { noteEd.forceActiveFocus(); noteEd.cursorPosition = noteEd.text.length } }
                    }
                }
                // ---- Friend's profile ----
                Flickable {
                    visible: tf.friendTab === "profile"
                    anchors.fill: parent
                    contentHeight: fpCol.implicitHeight + 20
                    clip: true; boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: fpCol
                        width: parent.width; spacing: 18
                        Row {
                            spacing: 22
                            Image { width: 150; height: 210; source: tf.friendProfile.back || ""; smooth: false
                                    fillMode: Image.PreserveAspectFit; sourceSize.height: 420 }
                            Column {
                                anchors.verticalCenter: parent.verticalCenter; spacing: 6
                                Text { text: tf.friendProfile.name || ""; color: T.text; font.family: T.font; font.pixelSize: 24; font.bold: true }
                                Text { width: Math.max(200, fpCol.width - 200); wrapMode: Text.Wrap
                                       text: tf.friendProfile.line || ""; color: T.muted; font.family: T.font; font.pixelSize: 13 }
                            }
                        }
                        Text { visible: tf.friendProfile.shared === true
                               text: shell.text("BINDERS"); color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true
                               font.letterSpacing: 1.5 }
                        Text { visible: tf.friendProfile.shared === true && (tf.friendProfile.binders || []).length === 0
                               text: shell.text("Hasn't shared a binder with you yet.")
                               color: T.dim; font.family: T.font; font.pixelSize: 13 }
                        Flow {
                            width: parent.width; spacing: 12
                            Repeater {
                                model: tf.friendProfile.binders || []
                                Btn { required property var modelData
                                      height: 40; width: implicitWidth + 30; iconSource: modelData.icon || ""
                                      text: modelData.title + (modelData.old ? "  ·  " + shell.text("expired") : "")
                                      enabled: !modelData.old && modelData.have !== false
                                      opacity: modelData.have === false ? 0.45 : 1
                                      tip: modelData.tip || ""
                                      onClicked: tf.openFriendBinder(modelData.slot, modelData.game || "") }
                            }
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent; width: parent.width - 80
                    visible: (tf.friendTab === "has" && tf.hasNote !== "") || (tf.friendTab === "library" && tf.libNote !== "")
                    text: tf.friendTab === "has" ? tf.hasNote : tf.libNote
                    wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                    color: T.muted; font.family: T.font; font.pixelSize: 15
                }
            }
            } }   // lazy
        }
    }

    // card (from the grid) or entry (from the list) is being dragged
    Item {
        id: ghost
        z: 100
        visible: false
        property var what: null
        property bool fromGrid: true
        property Item dropList: null   // list and entries in the list editor (the editor sets these when it appears)
        property Item dropEdit: null
        property real sx: 0
        property real sy: 0
        width: 110; height: 110 * 88 / 63
        x: sx - width / 2; y: sy - 30
        function move(w, img, px, py, grid, name) {
            var p = page.mapFromItem(null, px, py)
            what = w; fromGrid = grid; sx = p.x; sy = p.y
            gimg.source = img; gname.text = name
            visible = true
        }
        function over(item) {
            var p = item.mapFromItem(page, sx, sy)
            return p.x >= 0 && p.y >= 0 && p.x <= item.width && p.y <= item.height
        }
        function drop(px, py) {
            if (!visible) return
            var p = page.mapFromItem(null, px, py)
            sx = p.x; sy = p.y
            if (fromGrid && dropList && over(dropList)) tp.addFromGrid(what)
            else if (!fromGrid && dropEdit && over(dropEdit)) tp.change(what, 0)
            visible = false
        }
        opacity: 0.88
        Image { id: gimg; anchors.fill: parent; visible: ghost.fromGrid; sourceSize.width: 240; smooth: true }
        Rectangle {
            visible: !ghost.fromGrid
            width: Math.min(260, gname.implicitWidth + 24); height: 32; radius: 10
            color: T.surface2; border.width: 1; border.color: T.line2
            Text { id: gname; anchors.centerIn: parent; color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
        }
    }
    // binder (yours or a friend's) opened in the trade: shown right here instead of jumping to the profile page
    Loader {
        id: binderLd
        readonly property var bv: profilePage.binderView
        readonly property bool open: bv.isOpen && bv.hostPage === "trade"
        property bool warm: false
        onOpenChanged: if (open) { binderCool.stop(); warm = true } else binderCool.restart()
        active: open || warm
        visible: open
        focus: open
        x: right.x; y: right.y; width: right.width; height: right.height
        sourceComponent: BinderView { bd: binderLd.bv }
    }
    Timer { id: binderCool; interval: 60000; onTriggered: binderLd.warm = false }

    ContextMenu {
        id: tmenu
        z: 900
        property string kind: ""
        property string lid: ""
        onPicked: function (k) {
            if (k === "rename") { page.renameLid = lid; return }   // the tile turns into the field
            tl.listAction(kind, lid, k)
        }
    }
    ContextMenu {   // menus of the bar: friend, friend folders, sorting
        id: rmenu
        z: 900
        property string kind: ""
        property string ident: ""
        onPicked: function (k) {
            var a = kind, b = ident
            if (k === "rename") { rail.rename(a, b); return }   // field expands in the bar, no dialog
            Qt.callLater(function () { tf.railAction(a, b, k) })
        }
    }
}
