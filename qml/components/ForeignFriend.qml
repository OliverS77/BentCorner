// Friend in another game or in several games at once (game toggles at the top) – without switching the app:
// the open tab's cards (Has · Wants · Library) as a grid, image/name/price from each game's own database, a game
// chip on every card when games are mixed. Click = card on the right: onto MY list of THAT game, or into the
// trade (mixed ticket). Advanced search only exists in the open game (∞ = games mixed). A switched-on game that
// isn't installed: download strip with progress, like the game picker at the top.
import QtQuick

Item {
    id: ff
    property var tp
    readonly property var tf: tradeFriends   // TRADE-SPLIT: FriendsBackend
    readonly property var tl: tradeLists   // TRADE-SPLIT: ListsBackend
    readonly property var fd: tp ? tf.friendForeign : ({})
    readonly property string game: fd.game || ""
    readonly property var rows: fd.rows || []
    readonly property bool wants: fd.key === "wants"
    property int sel: -1                       // clicked card (index in rows) – panel on the right
    readonly property var cur: sel >= 0 && sel < rows.length ? rows[sel] : null
    onFdChanged: if (sel >= rows.length) sel = -1
    // entries of the game picker (installed? loading? progress? size?) – update themselves
    function pickOf(key) {
        var a = shell.gameChoices
        for (var i = 0; i < a.length; i++) if (a[i].key === key) return a[i]
        return null
    }
    // a game finished loading: rebuild with images and prices
    Connections { target: shell; function onGamesChanged() { if ((ff.fd.missing || []).length) ff.tf.refreshForeign() } }

    // ---------------- Trade tab without the open game ----------------
    Text {
        visible: ff.fd.tab === "trade"
        anchors.centerIn: parent; width: Math.min(parent.width - 80, 620)
        horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        text: shell.text("Trading works in a game you both share. Cards from Has or Library still go into the trade (mixed ticket).")
        color: T.muted; font.family: T.font; font.pixelSize: 15
    }

    Item {
        id: body
        visible: ff.fd.tab !== "trade"
        anchors.fill: parent

        // ---- bar: search · advanced search (off: ∞) · count ----
        Row {
            id: bar
            width: parent.width; height: 38; spacing: 10
            SearchField {
                id: q
                width: Math.min(360, bar.width * 0.4); height: 38
                placeholder: shell.text("Search (name, set) …")
                onEdited: function (t) { qT.restart() }
                Timer { id: qT; interval: 180; onTriggered: ff.tf.setForeignQuery(q.text) }
                Connections { target: ff; function onFdChanged() { if ((ff.fd.query || "") === "" && !q.inputFocus) q.text = "" } }
            }
            Btn {   // greyed out with ∞ over it – a click leads to the full library (open game) with advanced search
                id: advB
                height: 38; width: implicitWidth + 30
                text: shell.text("Advanced search")
                opacity: 0.55
                tip: ff.fd.switchTip || ""
                onClicked: ff.tf.fullLibrary()
                Text { anchors.centerIn: parent; text: "∞"; opacity: 0.28; color: T.text   // big and faint: the text stays readable
                       font.family: T.font; font.pixelSize: 44 }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: (ff.fd.title || "") + "  ·  " + ff.rows.length + (ff.fd.more ? " +" + ff.fd.more : "")
                color: T.muted; font.family: T.font; font.pixelSize: 13
            }
        }

        // ---- switched-on games that aren't installed: download right here ----
        Column {
            id: missCol
            y: bar.height + 12; width: parent.width; spacing: 8
            Repeater {
                model: ff.fd.missing || []
                Rectangle {
                    id: miss
                    required property var modelData
                    readonly property var pick: ff.pickOf(modelData.game)
                    property bool asking: false
                    width: Math.min(missCol.width, 640); height: 44; radius: 12
                    color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
                    Text { x: 14; anchors.verticalCenter: parent.verticalCenter
                           text: miss.modelData.nick + " " + shell.text("isn't installed on your PC.")
                           color: T.text2; font.family: T.font; font.pixelSize: 13 }
                    Row {
                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        visible: !(miss.pick && miss.pick.loading)
                        Text { visible: miss.asking; anchors.verticalCenter: parent.verticalCenter
                               text: shell.text("Download?") + (miss.pick && miss.pick.mb > 0 ? " ca. " + miss.pick.mb + " MB" : "")
                               color: T.text2; font.family: T.font; font.pixelSize: 13 }
                        Btn { visible: !miss.asking; height: 30; compact: true; width: implicitWidth + 20; primary: true
                              text: shell.text("Download"); onClicked: miss.asking = true }
                        Btn { visible: miss.asking; height: 30; compact: true; width: implicitWidth + 16; primary: true
                              text: shell.text("Yes"); onClicked: { miss.asking = false; shell.downloadGame(miss.modelData.game) } }
                        Btn { visible: miss.asking; height: 30; compact: true; width: implicitWidth + 16
                              text: shell.text("No"); onClicked: miss.asking = false }
                    }
                    Item {   // loading: percent + thin bar (progress also on the download key at the top)
                        visible: !!(miss.pick && miss.pick.loading)
                        anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter
                        width: 200; height: 26
                        Text { anchors.right: parent.right; y: 0
                               text: miss.pick && miss.pick.progress > 0 ? Math.round(miss.pick.progress * 100) + " %" : shell.text("waiting …")
                               color: T.muted; font.family: T.font; font.pixelSize: 12 }
                        Rectangle { y: 20; width: parent.width; height: 4; radius: 2; color: T.line
                                    Rectangle { width: parent.width * Math.max(0, Math.min(1, miss.pick ? miss.pick.progress : 0))
                                                height: parent.height; radius: 2; color: T.hi } }
                    }
                }
            }
        }

        Text {
            visible: ff.rows.length === 0 && ff.fd.installed === true
            anchors.centerIn: parent; width: parent.width - 80
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
            text: ff.fd.empty || ""; color: T.muted; font.family: T.font; font.pixelSize: 15
        }

        // ---- the cards ----
        readonly property real panelW: ff.cur && !ff.wants ? Math.min(380, width * 0.42) : 0
        GridView {
            id: grid
            visible: !ff.wants
            y: missCol.y + missCol.height + (missCol.height > 0 ? 12 : 0)
            width: body.width - body.panelW - (body.panelW > 0 ? 16 : 0); height: body.height - y
            readonly property int cols: Math.max(2, Math.floor(width / 168))
            cellWidth: Math.floor(width / cols); cellHeight: (cellWidth - 16) * 88 / 63 + 58
            clip: true; boundsBehavior: Flickable.StopAtBounds
            model: ff.wants ? [] : ff.rows
            ScrollHint {}
            // the same tile as in the library (hover lift, fade in, chips on the image)
            delegate: CardTile {
                id: tile
                required property var modelData
                required property int index
                width: grid.cellWidth; height: grid.cellHeight
                name: modelData.name; price: modelData.price || ""
                setLine: modelData.setLine || ""
                img: modelData.img || ""
                chips: (ff.fd.mixed === true || modelData.game !== ff.tf.gameKeyNow ? [modelData.chip] : [])
                       .concat([modelData.count + "× " + String(modelData.lang || "en").toUpperCase() + (modelData.foil ? " Foil" : "")])
                selected: ff.sel === index
                onClicked: ff.sel = ff.sel === index ? -1 : index
            }
        }
        // „Wants“: names only (no image) – click = menu: onto my list of that game
        Flickable {
            visible: ff.wants
            y: grid.y; width: body.width; height: body.height - y
            contentHeight: wFlow.implicitHeight + 12
            clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollHint {}
            Flow {
                id: wFlow
                width: parent.width - 12; spacing: 6
                Repeater {
                    model: ff.wants ? ff.rows : []
                    Rectangle {
                        id: wt
                        required property var modelData
                        required property int index
                        width: wtx.implicitWidth + 18 + (wch.visible ? wch.width + 8 : 0); height: 28; radius: 8
                        color: wh.hovered ? T.surface2 : Qt.darker(T.surface, 1.05)
                        border.width: 1; border.color: wh.hovered ? T.text2 : T.line
                        Rectangle { id: wch; visible: ff.fd.mixed === true; x: 6; anchors.verticalCenter: parent.verticalCenter
                                    height: 16; width: wcht.implicitWidth + 10; radius: 8; color: "transparent"
                                    border.width: 1; border.color: T.line2
                                    Text { id: wcht; anchors.centerIn: parent; text: wt.modelData.chip; color: T.text2
                                           font.family: T.font; font.pixelSize: 9; font.bold: true } }
                        Text { id: wtx; x: wch.visible ? wch.width + 14 : 9; anchors.verticalCenter: parent.verticalCenter
                               text: wt.modelData.name + "  ·  " + wt.modelData.info
                               color: T.text2; font.family: T.font; font.pixelSize: 12 }
                        HoverHandler { id: wh; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: function (ev) {
                                var p = wt.mapToItem(ff, ev.position.x, ev.position.y)
                                menu.idx = wt.index; menu.items = ff.listItems(wt.modelData.game, false)
                                menu.open(p.x, p.y)
                            }
                        }
                    }
                }
            }
        }

        // ---- clicked card: on the right (as far as possible like the detail view) ----
        Rectangle {
            id: panel
            visible: body.panelW > 1
            x: body.width - body.panelW; y: grid.y
            width: body.panelW; height: body.height - y
            radius: 14; color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
            readonly property var c: ff.cur || ({})
            Flickable {
                anchors.fill: parent; anchors.margins: 14
                contentHeight: pc.implicitHeight; clip: true; boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: pc
                    width: parent.width; spacing: 10
                    Item {
                        width: parent.width; height: 30
                        Row {
                            anchors.verticalCenter: parent.verticalCenter; spacing: 8
                            Rectangle { anchors.verticalCenter: parent.verticalCenter; height: 18; width: pcc.implicitWidth + 12; radius: 9
                                        color: "transparent"; border.width: 1; border.color: T.line2
                                        Text { id: pcc; anchors.centerIn: parent; text: panel.c.chip || ""; color: T.text2
                                               font.family: T.font; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.8 } }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: panel.c.setName || ""
                                   color: T.muted; font.family: T.font; font.pixelSize: 12 }
                        }
                        Btn { anchors.right: parent.right; glyph: "close"; compact: true; width: 30; height: 30
                              tip: shell.text("Close"); onClicked: ff.sel = -1 }
                    }
                    Text { width: parent.width; wrapMode: Text.Wrap; text: panel.c.name || ""
                           color: T.text; font.family: T.font; font.pixelSize: 20; font.bold: true }
                    Rectangle {
                        width: parent.width; height: width * 88 / 63; radius: 12; color: T.surface2; clip: true
                        Image { id: pim; anchors.fill: parent; source: panel.c.img || ""; fillMode: Image.PreserveAspectFit
                                asynchronous: true; smooth: true; mipmap: true; sourceSize.width: 640 }
                        NoImage { anchors.fill: parent; radius: parent.radius
                                  visible: (panel.c.img || "") === "" || pim.status === Image.Error }
                        Text { visible: pim.status === Image.Loading; anchors.centerIn: parent; width: parent.width - 30
                               horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                               text: panel.c.name || ""; color: T.dim; font.family: T.font; font.pixelSize: 15 }
                    }
                    Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.StyledText
                           text: (panel.c.facts || "") + (panel.c.price ? "<br><b>" + panel.c.price + "</b>" : "")
                           color: T.text2; font.family: T.font; font.pixelSize: 13; lineHeight: 1.15 }
                    Text { text: shell.text("To your list") + " (" + (ff.tp ? ff.tf.gameNick(panel.c.game || "") : "") + ")"
                           color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2 }
                    Flow {
                        width: parent.width; spacing: 6
                        Repeater {
                            model: ff.cur && ff.tp ? ff.tl.listsOf(panel.c.game) : []
                            Btn { required property var modelData
                                  height: 30; compact: true; width: implicitWidth + 18
                                  text: "+ " + modelData.name
                                  onClicked: ff.tl.foreignToList(ff.fd.key, ff.sel, modelData.id) }
                        }
                    }
                    Btn { width: parent.width; height: 40; primary: true
                          text: shell.text("Add to the trade – you get it")
                          onClicked: ff.tf.foreignToTrade(ff.fd.key, ff.sel) }
                }
            }
        }
    }

    function listItems(game, trade) {
        var out = [{ text: shell.text("To your list") + " (" + ff.tf.gameNick(game) + ")", enabled: false }]
        var ls = ff.tl.listsOf(game)
        for (var i = 0; i < ls.length; i++) out.push({ text: ls[i].name, key: "list:" + ls[i].id, indent: true })
        return out
    }
    ContextMenu {
        id: menu
        property int idx: -1
        onPicked: function (key) {
            if (key.indexOf("list:") === 0) ff.tl.foreignToList(ff.fd.key, idx, key.slice(5))
            close()
        }
    }
}
