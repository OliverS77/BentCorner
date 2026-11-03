// Rail on the left in Trade – two bento boxes:
//   you      card back, name, profile · your four list folders (lists can be dragged onto them) · import, export
//   friends  folders as in deck building („General“ always there), sortable; per friend an eye (marks their cards in
//            your lists) and „⋯“ (rename, move, remove)
// Collapsible to the icons. Menus are reported via menu(kind, ident, x, y) – the page shows them in the window.
import QtQuick

Item {
    id: rail
    property var tp
    readonly property var tf: tradeFriends   // TRADE-SPLIT: FriendsBackend
    readonly property var tl: tradeLists   // TRADE-SPLIT: ListsBackend
    readonly property bool open: tf.railOpen
    signal menu(string kind, string ident, real x, real y)
    width: open ? 300 : 72
    Behavior on width { enabled: shell.animate; NumberAnimation { duration: 240 * shell.speed; easing.type: Easing.OutCubic } }
    clip: true

    // rename from the menu: a field slides in at the top of the friends box (no dialog)
    function rename(kind, ident) {
        if (kind === "friend") {
            var fr = tf.friends, nm = ""
            for (var i = 0; i < fr.length; i++) if (fr[i].fid === ident) nm = fr[i].name
            ask.start("friend", ident, shell.text("New name"), nm, shell.text("Rename"))
        } else if (kind === "folder") {
            ask.start("folderRename", ident, shell.text("Rename folder"), ident, shell.text("Rename"))
        }
    }
    function menuAt(kind, ident, item) {
        var q = item.mapToItem(null, 0, item.height + 4)
        rail.menu(kind, ident, q.x, q.y)
    }

    component Box: Rectangle {
        radius: 16
        color: Qt.darker(T.surface, 1.1)
        border.width: 1; border.color: T.line
    }
    component Entry: Rectangle {
        id: en
        property bool sel: false
        property bool drop: false
        property alias hovered: eh.hovered
        signal tapped()
        radius: 12
        color: sel ? T.surface2 : (eh.hovered || drop ? Qt.lighter(T.surface, 1.15) : "transparent")
        border.width: 1; border.color: drop ? T.text : (sel ? T.line2 : "transparent")
        HoverHandler { id: eh; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: en.tapped() }
    }
    component Head: Text {
        color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1.2
    }

    // Low window (e.g. 1280×680): if not everything fits stacked, the whole rail scrolls instead of the
    // friends box being squeezed to header + button (list and sorting were hidden then). Otherwise as always.
    Flickable {
        id: railFlick
        anchors.fill: parent
        contentWidth: width; contentHeight: frBox.y + frBox.height
        interactive: contentHeight > height + 1
        clip: true; boundsBehavior: Flickable.StopAtBounds
        ScrollHint {}

    // ================= you =================
    Box {
        id: meBox
        width: rail.width; height: mcol.implicitHeight + 16
        Column {
            id: mcol
            x: 8; y: 8; width: parent.width - 16
            spacing: 4
            // no title any more – the Orbit line above the page names it (2026-10-29); the box starts with "You",
            // collapse « sits in that row; collapsed, this row holds only »
            Item {
                width: mcol.width; height: rail.open ? 0 : 28
                visible: !rail.open
                Text {
                    anchors.right: parent.right; width: parent.width; height: parent.height
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    text: rail.open ? "«" : "»"
                    color: th.hovered ? T.text : T.muted; font.pixelSize: 16; font.bold: true
                    HoverHandler { id: th; cursorShape: Qt.PointingHandCursor
                        onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height)
                            shell.tip(rail.open ? shell.text("Collapse sidebar") : shell.text("Expand sidebar"), p.x, p.y) }
                            else shell.tip("", 0, 0) }
                    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: tf.toggleRail() }
                }
            }
            Entry {
                id: meEntry
                width: mcol.width; height: 58
                sel: false   // the folder below is the marked one
                onTapped: tp.openMe()
                Image { x: 6; y: 6; height: 44; width: 44 * 63 / 88; source: tp.meBack; sourceSize.height: 88; smooth: true }
                Text {
                    visible: rail.open
                    x: 52; y: 6; height: 44; width: parent.width - 52 - 82
                    verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
                    text: tp.meName; color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true
                }
                Btn {
                    id: profBtn
                    visible: rail.open
                    x: parent.width - width - 36; y: 12; width: 38; height: 34; compact: true; glyph: "sliders"
                    tip: shell.text("Edit profile: name and card back")
                    onClicked: tp.editProfile()
                }
                Text {   // collapse the rail
                    visible: rail.open
                    x: parent.width - 32; y: 12; width: 28; height: 34
                    horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                    text: "«"; color: ch.hovered ? T.text : T.muted; font.pixelSize: 16; font.bold: true
                    HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor
                        onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height)
                            shell.tip(shell.text("Collapse sidebar"), p.x, p.y) } else shell.tip("", 0, 0) }
                    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: tf.toggleRail() }
                }
            }
            Head { visible: rail.open; x: 10; topPadding: 6; bottomPadding: 2
                   text: (tp.gameName || "").toUpperCase() }   // the open game – the folders below belong to it
            // the four folders of your lists – dragging a list here moves it
            Repeater {
                model: tp.folders.filter(function (f) { return f.key !== "binders" })
                delegate: Entry {
                    id: fr
                    required property var modelData
                    readonly property bool canDrop: modelData.key !== "alarms"
                    width: mcol.width; height: 38
                    sel: tp.view !== "friend" && tp.folder === modelData.key
                    drop: da.containsDrag && da.ok
                    onTapped: { frIcon.kick(); tp.showFolder(modelData.key) }
                    NavIcon { id: frIcon; x: rail.open ? 12 : (fr.width - width) / 2; anchors.verticalCenter: parent.verticalCenter; s: 0.7
                              key: fr.modelData.icon; color: fr.sel ? T.text : T.muted; play: fr.hovered }
                    Text { visible: rail.open; x: 42; anchors.verticalCenter: parent.verticalCenter
                           width: parent.width - 84; elide: Text.ElideRight
                           text: fr.modelData.title; color: fr.sel ? T.top : T.text2
                           font.family: T.font; font.pixelSize: 14; font.bold: fr.sel }
                    Text { visible: rail.open; anchors.right: parent.right; anchors.rightMargin: 12
                           anchors.verticalCenter: parent.verticalCenter
                           text: fr.modelData.count; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                    DropArea {
                        id: da
                        anchors.fill: parent
                        keys: ["tlist"]
                        readonly property bool ok: fr.canDrop && drag.source !== null && drag.source.kind !== fr.modelData.key
                        onDropped: function (ev) {
                            if (!ok) return
                            var s = drag.source, k = fr.modelData.key
                            Qt.callLater(function () { tl.listAction(s.kind, s.lid, "move:" + k) })
                        }
                    }
                }
            }
            // divider, then the binders as their own item
            Rectangle { width: mcol.width - 20; x: 10; height: 1; color: T.line }
            Repeater {
                model: tp.folders.filter(function (f) { return f.key === "binders" })
                delegate: Entry {
                    id: bfr
                    required property var modelData
                    width: mcol.width; height: 38
                    sel: tp.view !== "friend" && tp.folder === "binders"
                    onTapped: { bfrIcon.kick(); tp.showFolder("binders") }
                    NavIcon { id: bfrIcon; x: rail.open ? 12 : (bfr.width - width) / 2; anchors.verticalCenter: parent.verticalCenter; s: 0.7
                              key: "binder"; color: bfr.sel ? T.text : T.muted; play: bfr.hovered }
                    Text { visible: rail.open; x: 42; anchors.verticalCenter: parent.verticalCenter
                           width: parent.width - 84; elide: Text.ElideRight
                           text: bfr.modelData.title; color: bfr.sel ? T.top : T.text2
                           font.family: T.font; font.pixelSize: 14; font.bold: bfr.sel }
                    Text { visible: rail.open; anchors.right: parent.right; anchors.rightMargin: 12
                           anchors.verticalCenter: parent.verticalCenter
                           text: bfr.modelData.count; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                }
            }
        }
    }

    // ================= Comparison with friends: own box between „you“ and „friends“ =================
    function explainSync() {   // locked button clicked: open the bar (if collapsed) and the explanation
        if (!rail.open) tf.toggleRail()
        syncInfo.open = true
    }
    function waitText(s) { return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2) }
    Box {
        id: syncBox
        y: meBox.height + 12
        width: rail.width; height: scol.implicitHeight + 16
        Column {
            id: scol
            x: 8; y: 8; width: parent.width - 16
            spacing: 6
            Item {
                visible: rail.open
                width: scol.width; height: 26
                Head { x: 8; anchors.verticalCenter: parent.verticalCenter; text: shell.text("SYNC") }
                Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                      width: 30; height: 26; compact: true; text: "i"; fontPx: 14; active: syncInfo.open
                      tip: shell.text("How does it work?"); onClicked: syncInfo.open = !syncInfo.open }
            }
            // the two buttons only work once „I understand“ is ticked below the explanation – until then a click opens it
            Btn { width: scol.width; height: 34; compact: true
                  text: !rail.open ? "↑" : tf.shareWait > 0 ? "↑  " + shell.text("Shared") + " · " + rail.waitText(tf.shareWait)
                                                          : "↑  " + shell.text("Share with friends")
                  enabled: tf.shareWait <= 0
                  opacity: tf.syncUnderstood ? 1 : 0.5
                  tip: tf.syncUnderstood ? shell.text("Send your shared lists (and your library, if you share it) to your friends now")
                                         : shell.text("First read how it works (opens the explanation)")
                  onClicked: tf.syncUnderstood ? tf.shareNow() : rail.explainSync() }
            Btn { width: scol.width; height: 34; compact: true
                  text: !rail.open ? "↓" : tf.fetchWait > 0 ? "↓  " + shell.text("Fetched") + " · " + rail.waitText(tf.fetchWait)
                                                          : "↓  " + shell.text("Get from friends")
                  enabled: tf.fetchWait <= 0
                  opacity: tf.syncUnderstood ? 1 : 0.5
                  tip: tf.syncUnderstood ? shell.text("Check what your friends have shared – right now")
                                         : shell.text("First read how it works (opens the explanation)")
                  onClicked: tf.syncUnderstood ? tf.fetchNow() : rail.explainSync() }
            Item {
                id: syncInfo
                property bool open: false
                visible: rail.open
                width: scol.width; height: open ? siT.implicitHeight + 14 + siOk.height : 0
                clip: true
                Behavior on height { NumberAnimation { duration: 200 * shell.speed; easing.type: Easing.OutCubic } }
                CheckBox { id: siOk; x: 6; y: siT.y + siT.implicitHeight + 8; width: parent.width - 12
                           text: shell.text("I understand"); checked: tf.syncUnderstood
                           onToggled: function (on) { tf.setSyncUnderstood(on); if (on) syncInfo.open = false } }
                Text { id: siT; x: 6; y: 4; width: parent.width - 12; wrapMode: Text.Wrap
                       text: shell.text("Bent°Corner syncs by itself: when your shared lists change, only the changes go to your friends every few minutes – small and encrypted. Once a day the full state follows (including your library, if you share it). What your friends share is picked up every three minutes.\n\nThe buttons do it right away – for example while you're trading on Discord. Afterwards each rests for five minutes.")
                       color: T.muted; font.family: T.font; font.pixelSize: 12 }
            }
        }
    }

    // ================= Friends =================
    Box {
        id: frBox
        y: syncBox.y + syncBox.height + 12
        width: rail.width; height: Math.max(250, rail.height - y)   // header, at least two friends, button
        Item {
            id: fhead
            x: 8; y: 8; width: parent.width - 16; height: 34
            Head { visible: rail.open; x: 8; anchors.verticalCenter: parent.verticalCenter; text: shell.text("FRIENDS")
                   color: noFolder.containsDrag ? T.text : T.muted }
            DropArea {   // drag a friend onto „FRIENDS“ = take out of the folder
                id: noFolder
                anchors.fill: parent; keys: ["friend"]
                onDropped: function (ev) { var s = drag.source
                    if (s && s.modelData) Qt.callLater(tf.railAction, "friend", s.modelData.fid, "move:") }
            }
            Row {
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                Btn { id: sortBtn; visible: rail.open; width: 34; height: 30; compact: true; glyph: "sort"
                      tip: shell.text("Sort friends")
                      onClicked: rail.menuAt("sort", "", sortBtn) }
                Btn { visible: rail.open; width: 26; height: 30; compact: true; text: tf.friendSortReversed ? "↑" : "↓"
                      tip: tf.friendSortReversed ? shell.text("Reversed order – click: normal") : shell.text("Click: reverse the order")
                      onClicked: tf.toggleFriendSort() }
                Btn { visible: rail.open; width: 34; height: 30; compact: true; glyph: "folderPlus"
                      active: ask.open && ask.mode === "folder"
                      tip: shell.text("New folder for friends")
                      onClicked: ask.open && ask.mode === "folder" ? ask.cancel()
                                 : (ask.justClosed() ? undefined
                                    : ask.start("folder", "", shell.text("Name of the new folder"), "", shell.text("Create"))) }
            }
        }
        // slides in below the header: new folder / rename – separated from the rest by lines
        InlineAsk {
            id: ask
            x: 8; y: fhead.y + fhead.height + 6; width: parent.width - 16
            onAccepted: function (mode, ident, text) {
                if (mode === "folder") tf.newFriendFolderNamed(text)
                else if (mode === "friend") tf.renameFriendTo(ident, text)
                else if (mode === "folderRename") tf.renameFriendFolderTo(ident, text)
            }
            Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: T.line; visible: ask.height > 1 }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line; visible: ask.height > 1 }
        }
        Flickable {
            ScrollHint {}
            x: 8; y: ask.y + ask.height + (ask.height > 1 ? 6 : 0)
            width: parent.width - 16; height: parent.height - y - addBtn.height - 16
            contentHeight: col.implicitHeight
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: col
                width: parent.width
                spacing: 2
                Repeater {
                    model: tf.friendGroups
                    delegate: Column {
                        id: grp
                        required property var modelData
                        width: col.width
                        spacing: 2
                        // folder header: arrow, name, count, „⋯“ (only for own folders) – „General“ is always there
                        Rectangle {
                            visible: rail.open
                            width: grp.width; height: 30; radius: 8
                            color: fdrop.containsDrag ? T.surface2 : (gh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent")
                            border.width: fdrop.containsDrag ? 1 : 0; border.color: T.text
                            Rectangle {   // while dragging: the whole folder glows
                                visible: fdrop.containsDrag
                                width: grp.width; height: grp.height; radius: 10
                                color: "transparent"; border.width: 1; border.color: T.text2
                            }
                            DropArea {   // drag a friend into the folder – the whole area of the folder counts
                                id: fdrop
                                width: grp.width; height: grp.height; keys: ["friend"]
                                onDropped: function (ev) { var s = drag.source
                                    if (s && s.modelData) Qt.callLater(tf.railAction, "friend", s.modelData.fid, "move:" + grp.modelData.folder) }
                            }
                            HoverHandler { id: gh; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: tf.toggleFriendFolder(grp.modelData.folder) }
                            Chevron { x: 6; anchors.verticalCenter: parent.verticalCenter; size: 12; open: grp.modelData.open
                                      color: T.muted }
                            Text { x: 24; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 80; elide: Text.ElideRight
                                   text: grp.modelData.title; color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
                            Text { anchors.right: parent.right; anchors.rightMargin: gm.visible ? 40 : 10
                                   anchors.verticalCenter: parent.verticalCenter
                                   text: grp.modelData.count; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                            Btn { id: gm; visible: gh.hovered && grp.modelData.folder !== ""
                                  anchors.right: parent.right; anchors.rightMargin: 2; anchors.verticalCenter: parent.verticalCenter
                                  width: 32; height: 24; compact: true; text: "⋯"; tip: shell.text("Rename or delete folder")
                                  onClicked: rail.menuAt("folder", grp.modelData.folder, gm) }
                        }
                        Repeater {
                            model: grp.modelData.open || !rail.open ? grp.modelData.friends : []
                            delegate: Entry {
                                id: fe
                                required property var modelData
                                width: grp.width; height: 58
                                // drag: onto a folder (or onto „FRIENDS“ = no folder) – the „⋯“ menu can do it too
                                Drag.active: fdrag.active
                                Drag.keys: ["friend"]
                                Drag.source: fe
                                Drag.hotSpot.x: fdrag.gx; Drag.hotSpot.y: fdrag.gy   // drop target = under the mouse
                                FollowDrag { id: fdrag; enabled: rail.open
                                              onActiveChanged: if (!active) { fe.Drag.drop(); fe.x = 0; fe.y = 0 } }
                                states: State { when: fdrag.active
                                                ParentChange { target: fe; parent: rail.Window.window ? rail.Window.window.contentItem : rail }
                                                PropertyChanges { target: fe; z: 300; opacity: 0.85 } }
                                // friends from other games normal too (click shows their cards there, no switch)
                                sel: tp.current === modelData.fid || (tp.currentId !== "" && tp.currentId === modelData.id)
                                onTapped: tf.openFriend(modelData.fid)
                                onHoveredChanged: if (hovered) tipT.restart(); else { tipT.stop(); shell.tip("", 0, 0) }
                                Timer { id: tipT; interval: 700; onTriggered: { var p = fe.mapToItem(null, fe.width / 2, fe.height); shell.tip(fe.modelData.tip, p.x, p.y) } }
                                Image { x: rail.open ? 6 : (fe.width - width) / 2; y: 6; height: 44; width: 44 * 63 / 88
                                        source: fe.modelData.img; sourceSize.height: 88; smooth: true }
                                Column {
                                    visible: rail.open
                                    x: 52; anchors.verticalCenter: parent.verticalCenter
                                    width: parent.width - 52 - 80
                                    spacing: 1
                                    Row {
                                        spacing: 6
                                        Text { text: fe.modelData.name; color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true
                                               elide: Text.ElideRight; width: Math.min(implicitWidth, fe.width - 132 - (ex.visible ? ex.width + 6 : 0)) }
                                        Rectangle {
                                            id: ex
                                            visible: fe.modelData.example
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: exT.implicitWidth + 8; height: 16; radius: 5
                                            color: "transparent"; border.width: 1; border.color: T.line2
                                            Text { id: exT; anchors.centerIn: parent; text: shell.text("EXAMPLE"); color: T.text2
                                                   font.family: T.font; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1 }
                                        }
                                    }
                                    Item {   // the friend's games („MTG · PKM · OP“) – too long: scrolls through on hover
                                        width: parent.width; height: infoT.implicitHeight; clip: true
                                        Text {
                                            id: infoT
                                            text: fe.modelData.info; color: T.muted; font.family: T.font; font.pixelSize: 12
                                            readonly property real over: Math.max(0, implicitWidth - parent.width)
                                            width: over > 0 && fe.hovered ? implicitWidth : parent.width
                                            elide: over > 0 && fe.hovered ? Text.ElideNone : Text.ElideRight
                                            SequentialAnimation on x {
                                                running: infoT.over > 0 && fe.hovered
                                                loops: Animation.Infinite
                                                onRunningChanged: if (!running) infoT.x = 0
                                                PauseAnimation { duration: 600 }
                                                NumberAnimation { from: 0; to: -infoT.over; duration: 40 * infoT.over }
                                                PauseAnimation { duration: 900 }
                                                NumberAnimation { to: 0; duration: 300 }
                                            }
                                        }
                                    }
                                }
                                Btn {
                                    id: fm
                                    visible: rail.open
                                    x: parent.width - 37; anchors.verticalCenter: parent.verticalCenter
                                    width: 32; height: 30; compact: true; text: "⋯"
                                    tip: shell.text("Note, folder, report, remove – or drag onto a folder")
                                    onClicked: rail.menuAt("friend", fe.modelData.fid, fm)
                                }
                            }
                        }
                        Item { width: 1; height: 4 }
                    }
                }
                Text {
                    visible: rail.open && tf.friends.length === 0
                    x: 6; width: col.width - 12
                    text: shell.text("No friends yet – have them send you a file (Export on their side) and load it with “Import …”.")
                    wrapMode: Text.Wrap; color: T.dim; font.family: T.font; font.pixelSize: 13
                }
            }
        }
        Btn {
            id: addBtn
            x: 8; y: parent.height - height - 8
            width: parent.width - 16; height: 36; compact: true
            text: rail.open ? shell.text("+ Import friend") : "+"
            onClicked: tf.importFriend()
        }
    }
    }   // railFlick
}
