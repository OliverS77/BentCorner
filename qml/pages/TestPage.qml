// Play: pick a deck and play it alone (a placeholder until you can play against friends) – library, prize
// cards (Pokémon), Extra Deck (Yu-Gi-Oh!), inkwell (Lorcana), play area, discard pile and your hand; cards are dragged
// between them.
// Logic: testingPage (qtesting.py, collection/playtest.py).
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var tp: testingPage
    readonly property bool table: tp.mode === "table"
    onVisibleChanged: tp.setActive(visible)
    Component.onCompleted: tp.setActive(visible)

    Row {
        id: head
        x: 22; y: 14
        spacing: 12
        Text { text: shell.text("Play"); color: T.text; font.family: T.font; font.pixelSize: 21; font.bold: true }
        Text { anchors.baseline: parent.children[0].baseline
               text: shell.text("Test your decks – soon against friends too")
               color: T.dim; font.family: T.font; font.pixelSize: 13 }
    }
    Flickable {   // deck picker (the chances live in the deck info now)
        id: fl
        ScrollHint {}
        x: 20; y: head.y + head.height + 14
        width: page.width - 40
        height: page.table ? Math.min(body.height + 4, 60) : page.height - y - 10
        contentHeight: body.height + (page.table ? 0 : 20)
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3500
        Mirror { id: body; width: fl.width - 14; mirror: page.tp.body }
    }

    // ---------- table ----------
    component Card: Item {
        id: cd
        property var card
        property string zone
        property real h: 150
        width: Math.round(h * 63 / 88); height: h
        Drag.active: cdrag.active
        Drag.keys: ["pt"]
        Drag.source: cd
        Drag.hotSpot.x: cdrag.gx; Drag.hotSpot.y: cdrag.gy   // drop target = under the mouse
        FollowDrag { id: cdrag; onActiveChanged: if (!active) { cd.Drag.drop(); cd.x = cd.x } }
        states: State {
            when: cdrag.active
            ParentChange { target: cd; parent: page }
            PropertyChanges { target: cd; z: 300 }
        }
        Rectangle {
            anchors.fill: parent; radius: 8; color: T.surface; clip: true
            opacity: cdrag.active ? 0.85 : 1
            scale: cdrag.active ? 1.05 : (ch.hovered ? 1.02 : 1)
            Behavior on scale { NumberAnimation { duration: 120 } }
            Image { id: cdImg; anchors.fill: parent; source: cd.card ? cd.card.img : ""; asynchronous: true; smooth: true
                    mipmap: true; fillMode: Image.PreserveAspectFit }
            NoImage {
                id: cdMissing
                anchors.fill: parent; thumb: true
                visible: !cd.card || (cd.card.img || "") === "" || cdImg.status === Image.Error
                Rectangle {   // the table has no name under the cards: small at the bottom (exception to "no text")
                    visible: cdMissing.visible && cd.card
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 5; anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.min(parent.width - 8, cdName.implicitWidth + 8); height: cdName.implicitHeight + 4
                    radius: 3; color: T.bg; opacity: 0.92
                    Text { id: cdName; anchors.centerIn: parent; width: parent.width - 6; elide: Text.ElideRight
                           horizontalAlignment: Text.AlignHCenter; text: cd.card ? cd.card.name : ""
                           color: T.text2; font.family: T.font; font.pixelSize: 10 }
                }
            }
            Text { visible: cdImg.status === Image.Loading; anchors.centerIn: parent; width: parent.width - 10
                   text: cd.card ? cd.card.name : ""; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                   color: T.text2; font.family: T.font; font.pixelSize: 11 }
        }
        HoverHandler { id: ch; cursorShape: Qt.OpenHandCursor }
        TapHandler { onTapped: if (cd.zone === "hand") page.tp.handClicked(cd.card.i) }
    }
    component Zone: Rectangle {   // drop target: a card dragged here moves into this zone
        id: zn
        property string name
        property string title
        radius: 14
        color: Qt.darker(T.surface, 1.1)
        // a mat without a frame (no boxes) – the outline only shows while a card is dragged over it
        border.width: drop.containsDrag ? 2 : 0; border.color: T.text
        Text { x: 12; y: 8; text: zn.title; color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true }
        DropArea {
            id: drop
            anchors.fill: parent
            keys: ["pt"]
            onDropped: function (ev) { var s = drag.source
                if (s && s.zone && s.zone !== zn.name) Qt.callLater(page.tp.move, s.zone, s.card.i, zn.name) }
        }
    }

    Item {
        id: tbl
        visible: page.table
        x: 20; y: fl.y + fl.height + 10
        width: page.width - 40; height: page.height - y - 10

        Text { visible: !page.tp.hasGame; anchors.centerIn: parent; color: T.muted; font.family: T.font
               font.pixelSize: 14; text: shell.text("Pick a deck with cards above.") }

        Row {   // actions + status
            id: bar
            visible: page.tp.hasGame
            spacing: 8
            Btn { height: 36; width: 130; compact: true; primary: true; text: shell.text("New game"); onClicked: page.tp.newGame() }
            Btn { height: 36; width: 100; compact: true; text: shell.text("Draw"); onClicked: page.tp.draw() }
            Btn { height: 36; width: 120; compact: true; text: shell.text("Next turn"); onClicked: page.tp.nextTurn() }
            Btn { visible: page.tp.canMulligan; height: 36; width: 120; compact: true; text: page.tp.mulliganText
                  active: page.tp.picking; onClicked: page.tp.mulligan() }
            Text { anchors.verticalCenter: parent.verticalCenter; leftPadding: 8; text: page.tp.status
                   color: page.tp.toBottom > 0 || page.tp.picking ? "#ffb347" : T.text2; font.family: T.font
                   font.pixelSize: 13 }
        }

        Column {   // left: library, prize cards, Extra Deck
            id: left
            visible: page.tp.hasGame
            y: bar.height + 12
            width: 200
            spacing: 12
            Item {
                width: parent.width; height: 170
                Image { id: lib; width: 110; height: 154; source: page.tp.back; smooth: true; mipmap: true
                        fillMode: Image.PreserveAspectFit; opacity: page.tp.libraryCount > 0 ? 1 : 0.25 }
                Text { x: lib.width + 10; y: 50; text: page.tp.libraryCount; color: T.text; font.family: T.font
                       font.pixelSize: 24; font.bold: true }
                Text { x: lib.width + 10; y: 82; text: shell.text("Library"); color: T.muted; font.family: T.font
                       font.pixelSize: 12 }
                TapHandler { onTapped: page.tp.draw() }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
            }
            Column {
                visible: page.tp.prizeCount > 0
                spacing: 6
                Text { text: page.tp.prizeLabel + "  (" + page.tp.prizeCount + ")"; color: T.muted
                       font.family: T.font; font.pixelSize: 12; font.bold: true }
                Grid {
                    columns: 3; spacing: 6
                    Repeater {
                        model: page.tp.prizeCount
                        Image { required property int index
                                width: 58; height: 81; source: page.tp.back; smooth: true; mipmap: true
                                fillMode: Image.PreserveAspectFit
                                TapHandler { onTapped: page.tp.takePrize(index) }
                                HoverHandler { cursorShape: Qt.PointingHandCursor } }
                    }
                }
            }
            Zone {   // Lorcana: inkwell – cards dragged here lie face down
                visible: page.tp.hasInkwell
                name: "inkwell"; title: shell.text("Inkwell") + "  (" + page.tp.inkwell.length + ")"
                width: left.width; height: page.tp.hasInkwell ? Math.max(130, 40 + Math.ceil(page.tp.inkwell.length / 3) * 74) : 0
                Grid {
                    x: 10; y: 30; columns: 3; spacing: 6
                    Repeater { model: page.tp.inkwell
                        Card { required property var modelData; card: modelData; zone: "inkwell"; h: 68 } }
                }
            }
            Column {
                visible: page.tp.extra.length > 0
                spacing: 4
                Text { text: shell.text("Extra Deck") + "  (" + page.tp.extra.length + ")"; color: T.muted
                       font.family: T.font; font.pixelSize: 12; font.bold: true }
                Repeater {
                    model: page.tp.extra
                    Text { required property var modelData; width: left.width; elide: Text.ElideRight
                           text: modelData.name; color: T.text2; font.family: T.font; font.pixelSize: 12 }
                }
            }
        }

        readonly property bool pk: page.tp.benchSize > 0   // Pokémon: Active spot + Bench above the play area
        Zone {   // Pokémon: Active Pokémon (one)
            id: activeZone
            visible: page.tp.hasGame && tbl.pk
            name: "active"; title: shell.text("Active")
            x: left.width + 16; y: bar.height + 12
            width: 150; height: tbl.pk ? 196 : 0
            Repeater { model: page.tp.active
                Card { required property var modelData; card: modelData; zone: "active"; h: 150; x: 24; y: 32 } }
        }
        Zone {   // Pokémon: Bench (5 places)
            id: benchZone
            visible: page.tp.hasGame && tbl.pk
            name: "bench"; title: shell.text("Bench") + "  (" + page.tp.bench.length + "/" + page.tp.benchSize + ")"
            x: activeZone.x + activeZone.width + 12; y: activeZone.y
            width: tbl.width - x - discardZone.width - 16; height: activeZone.height
            Row {
                x: 12; y: 32; spacing: 8
                Repeater { model: page.tp.bench
                    Card { required property var modelData; card: modelData; zone: "bench"; h: 150 } }
            }
        }
        Zone {   // play area (Pokémon: Stadium, Tools … – everything that isn't Active or on the Bench)
            id: playZone
            visible: page.tp.hasGame
            name: "play"; title: tbl.pk ? shell.text("Stadium & other cards") : shell.text("Play area")
            x: left.width + 16; y: tbl.pk ? activeZone.y + activeZone.height + 12 : bar.height + 12
            width: tbl.width - x - discardZone.width - 16
            height: tbl.height - y - handZone.height - 12
            Flow {
                x: 12; y: 30; width: parent.width - 24; height: parent.height - 40
                spacing: 8
                Repeater { model: page.tp.play
                    Card { required property var modelData; card: modelData; zone: "play"; h: 140 } }
            }
        }
        Zone {   // discard pile: the top card shows, how many below
            id: discardZone
            visible: page.tp.hasGame
            name: "discard"; title: shell.text("Discard pile") + "  (" + page.tp.discard.length + ")"
            anchors.right: parent.right
            y: bar.height + 12
            width: 160; height: tbl.height - y - handZone.height - 12
            Repeater { model: page.tp.discard
                Card { required property var modelData; required property int index
                       visible: index === page.tp.discard.length - 1
                       card: modelData; zone: "discard"; h: 160; x: 25; y: 34 } }
        }
        Zone {   // hand
            id: handZone
            visible: page.tp.hasGame
            name: "hand"; title: shell.text("Hand") + "  (" + page.tp.hand.length + ")"
            anchors.bottom: parent.bottom
            width: tbl.width; height: 210
            Flickable {
                x: 12; y: 28; width: parent.width - 24; height: parent.height - 34
                contentWidth: handRow.width; clip: true; boundsBehavior: Flickable.StopAtBounds
                interactive: contentWidth > width
                Row { id: handRow; spacing: 8
                    Repeater { model: page.tp.hand
                        Card { required property var modelData; card: modelData; zone: "hand"; h: 170 } } }
            }
        }
    }
}
