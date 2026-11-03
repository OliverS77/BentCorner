// Bent°Corner Brew – the deck helper: choose a format, optionally colours and a play style (each shows how many
// of your cards fit and which colours they are in), then suggestions with „Create as deck“. „Surprise me“
// is the old way (Bent°Corner searches itself). Logic: br (qdeckmore.BrewBackend), sg (qdeckmore.SuggestBackend).
import QtQuick

Item {
    id: root
    property var sg
    property var br
    readonly property var mana: ({"W": "#f4ecc8", "U": "#4a90d9", "B": "#8c7f86", "R": "#e0553d", "G": "#3f9b5a", "C": "#b6b6b6"})
    readonly property var colorNames: ({"W": shell.text("White"), "U": shell.text("Blue"), "B": shell.text("Black"),
                                        "R": shell.text("Red"), "G": shell.text("Green")})

    component Section: Text {
        color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1.5
    }

    component IdeaTile: Rectangle {
        id: ic
        property string title
        property string info
        property string img
        property string tag: ""
        property bool owned: true
        signal pick()
        width: 250; height: icCol.implicitHeight + 24
        radius: 14
        color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: ich.hovered ? T.line2 : T.line
        HoverHandler { id: ich }
        Column {
            id: icCol
            x: 12; y: 12; width: parent.width - 24
            spacing: 8
            Rectangle {
                width: 226; height: 316; radius: 10; color: "#0b0b0b"
                Image { id: icImg; anchors.fill: parent; source: ic.img; fillMode: Image.PreserveAspectFit
                        asynchronous: true; smooth: true; mipmap: true; sourceSize.width: 480
                        opacity: ic.owned ? 1 : 0.75 }
                NoImage { anchors.fill: parent; radius: parent.radius
                          visible: (ic.img || "") === "" || icImg.status === Image.Error }
                Rectangle {
                    visible: ic.tag !== ""
                    x: 8; y: 8; height: 22; radius: 7; width: tagT.implicitWidth + 14
                    color: ic.owned ? T.hi : Qt.rgba(0.07, 0.07, 0.07, 0.9)
                    border.width: 1; border.color: ic.owned ? T.hi : T.line2
                    Text { id: tagT; anchors.centerIn: parent; text: ic.tag; color: ic.owned ? T.onHi : T.text2
                           font.family: T.font; font.pixelSize: 11; font.bold: true }
                }
            }
            Text { width: parent.width; wrapMode: Text.Wrap; text: ic.title; textFormat: Text.StyledText
                   color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
            Text { width: parent.width; wrapMode: Text.Wrap; text: ic.info; textFormat: Text.StyledText
                   color: T.text2; font.family: T.font; font.pixelSize: 13 }
            Btn { width: parent.width; height: 38; primary: true; text: shell.text("Create deck"); onClicked: ic.pick() }
        }
    }

    Row {
        id: head
        x: 20; y: 12; spacing: 14
        Btn { height: 38; width: 150; backDir: -1; text: shell.text("All decks"); onClicked: root.sg.back() }
        Text { anchors.verticalCenter: parent.verticalCenter; text: "Bent°Corner Brew"
               color: T.text; font.family: T.display; font.pixelSize: 26 }
        Text { anchors.verticalCenter: parent.verticalCenter
               text: shell.text("What can you build from your cards? Pick a format, then color and/or play style – or let us surprise you.")
               color: T.dim; font.family: T.font; font.pixelSize: 13 }
    }
    Flickable {
        ScrollHint {}
        id: fl
        x: 20; y: head.y + head.height + 16
        width: root.width - 40; height: root.height - y - 12
        contentHeight: col.implicitHeight + 24
        clip: true; boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3500
        Column {
            id: col
            width: fl.width - 10
            spacing: 14

            // ---- 1. Format ----
            Section { text: shell.text("1 · FORMAT") }
            Row {
                spacing: 8
                Repeater {
                    model: root.sg.kinds
                    Btn { required property var modelData
                          height: 36; width: Math.max(120, implicitWidth); text: modelData.text
                          checkable: true; checked: root.br.fmt === modelData.key
                          onClicked: root.br.setFmt(modelData.key) }
                }
            }

            // ---- 2. Colours ----
            Item { width: 1; height: 2 }
            Row {
                spacing: 12
                Section { anchors.verticalCenter: parent.verticalCenter; text: shell.text("2 · COLORS (OPTIONAL)") }
                Text { anchors.verticalCenter: parent.verticalCenter
                       text: root.br.colors === "" ? shell.text("none selected = all colors")
                             : (root.br.fmt === "commander" ? shell.text("commanders with exactly these colors") : shell.text("only cards in these colors"))
                       color: T.dim; font.family: T.font; font.pixelSize: 12 }
            }
            Row {
                spacing: 14
                Repeater {
                    model: ["W", "U", "B", "R", "G"]
                    delegate: Item {
                        id: cp
                        required property string modelData
                        readonly property bool on: root.br.colors.indexOf(modelData) >= 0
                        width: 78; height: 92
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 54; height: 54; radius: 27
                            color: root.mana[cp.modelData]
                            opacity: cp.on || root.br.colors === "" ? 1 : 0.35
                            border.width: cp.on ? 3 : 0; border.color: T.hi
                            scale: cph.hovered ? 1.06 : 1
                            Behavior on scale { NumberAnimation { duration: 120 } }
                            Text { anchors.centerIn: parent; text: cp.modelData; color: T.onHi; font.pixelSize: 20; font.bold: true }
                        }
                        Text { y: 60; width: parent.width; horizontalAlignment: Text.AlignHCenter
                               text: root.colorNames[cp.modelData]; color: cp.on ? T.text : T.text2
                               font.family: T.font; font.pixelSize: 12; font.bold: cp.on }
                        Text { y: 76; width: parent.width; horizontalAlignment: Text.AlignHCenter
                               text: (root.br.counts[cp.modelData] || 0) + " " + shell.text("Cards")
                               color: T.dim; font.family: T.font; font.pixelSize: 11 }
                        HoverHandler { id: cph; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: root.br.toggleColor(cp.modelData) }
                    }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 6
                    Text { text: shell.text("%1 cards fit").arg(root.br.counts.total || 0)
                           color: T.text; font.family: T.font; font.pixelSize: 16; font.bold: true }
                    Btn { visible: root.br.colors !== ""; height: 30; compact: true; text: shell.text("Reset colors")
                          onClicked: root.br.clearColors() }
                }
            }

            // ---- 3. Play style ----
            Item { width: 1; height: 2 }
            Row {
                spacing: 12
                Section { anchors.verticalCenter: parent.verticalCenter; text: shell.text("3 · PLAY STYLE (OPTIONAL)") }
                Text { anchors.verticalCenter: parent.verticalCenter
                       text: shell.text("sorted by how many of your cards fit")
                       color: T.dim; font.family: T.font; font.pixelSize: 12 }
            }
            Grid {
                id: arch
                width: parent.width
                columns: Math.max(2, Math.floor((width + 10) / 300))
                spacing: 10
                readonly property real tw: (width - (columns - 1) * spacing) / columns
                Repeater {
                    model: root.br.archetypes
                    delegate: Rectangle {
                        id: at
                        required property var modelData
                        width: arch.tw; height: 118; radius: 14
                        color: modelData.sel ? T.surface2 : (ath.hovered ? Qt.lighter(T.surface, 1.12) : T.surface)
                        border.width: modelData.sel ? 2 : 1; border.color: modelData.sel ? T.hi : (ath.hovered ? T.line2 : T.line)
                        HoverHandler { id: ath; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: root.br.setKey(at.modelData.key) }
                        Text { x: 14; y: 10; width: parent.width - 28 - pips.width; elide: Text.ElideRight
                               text: at.modelData.name; color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true }
                        Row {
                            id: pips
                            anchors.right: parent.right; anchors.rightMargin: 12; y: 12
                            spacing: 3
                            Repeater { model: at.modelData.colors.split("")
                                Rectangle { required property var modelData; width: 14; height: 14; radius: 7; color: root.mana[modelData] || "#b6b6b6" } }
                        }
                        Text { x: 14; y: 32; width: parent.width - 28; height: 34; wrapMode: Text.Wrap; elide: Text.ElideRight
                               maximumLineCount: 2; text: at.modelData.desc; color: T.text2; font.family: T.font; font.pixelSize: 12 }
                        Rectangle { x: 14; y: 72; width: parent.width - 28; height: 6; radius: 3; color: Qt.rgba(1, 1, 1, 0.07)
                                    Rectangle { width: parent.width * at.modelData.frac; height: parent.height; radius: 3; color: at.modelData.sel ? T.hi : T.text2 } }
                        Text { x: 14; y: 84; width: parent.width - 28; elide: Text.ElideRight
                               text: "<b>" + at.modelData.count + "</b> " + (at.modelData.count === 1 ? shell.text("matching card") : shell.text("matching cards")) + (at.modelData.examples.length ? "  ·  " + at.modelData.examples.join(", ") : "")
                               textFormat: Text.StyledText; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                    }
                }
            }
            Text { visible: root.br.empty; width: parent.width; wrapMode: Text.Wrap
                   text: shell.text("Your collection is still empty – scan or import some cards first.")
                   color: T.text2; font.family: T.font; font.pixelSize: 14 }

            // ---- go ----
            Row {
                spacing: 10
                Btn { height: 44; width: 230; primary: true; enabled: !root.br.empty && !root.br.busy
                      text: root.br.busy ? shell.text("Searching …") : shell.text("Show suggestions")
                      onClicked: root.br.run() }
                Btn { height: 44; width: 200; enabled: !root.br.empty; text: shell.text("Surprise me")
                      tip: shell.text("Bent°Corner picks the best candidates itself (commanders by the good cards you own in their colors, 60-card decks by color + theme)")
                      onClicked: root.br.surprise() }
            }
            Text { width: parent.width; wrapMode: Text.Wrap; text: root.br.warning; visible: text !== ""
                   textFormat: Text.StyledText; color: "#d9b46a"; font.family: T.font; font.pixelSize: 14 }
            Text { width: parent.width; wrapMode: Text.Wrap; text: root.sg.status; visible: text !== ""
                   textFormat: Text.StyledText; color: T.muted; font.family: T.font; font.pixelSize: 14 }

            // ---- „Surprise me“ for Commander: candidates + own commander ----
            Column {
                visible: root.sg.picking
                width: parent.width
                spacing: 8
                Rectangle { width: parent.width; height: 1; color: T.line }
                Text { width: parent.width; wrapMode: Text.Wrap
                       text: shell.text("Your commanders – pre-sorted. At most %1 are checked in detail (this takes a moment, you can keep working):").arg(root.sg.checkMax)
                       color: T.muted; font.family: T.font; font.pixelSize: 13 }
                Flow {
                    width: parent.width; spacing: 6
                    Repeater {
                        model: root.sg.picks
                        delegate: Rectangle {
                            required property var modelData
                            height: 30; radius: 15; width: pt.implicitWidth + 28
                            color: modelData.on ? "#d9d9d9" : (ph.hovered ? T.surface2 : T.surface)
                            border.width: 1; border.color: modelData.on ? "#d9d9d9" : T.line2
                            Text { id: pt; anchors.centerIn: parent; text: modelData.text; color: modelData.on ? T.onHi : T.text2
                                   font.family: T.font; font.pixelSize: 13; font.bold: true }
                            HoverHandler { id: ph; cursorShape: Qt.PointingHandCursor
                                onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(modelData.tip, p.x, p.y) } else shell.tip("", 0, 0) }
                            TapHandler { onTapped: root.sg.togglePick(modelData.i) }
                        }
                    }
                }
                Btn { height: 34; compact: true; text: shell.text("Check these"); onClicked: root.sg.check() }
                Row {
                    spacing: 10
                    Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Or pick your own commander:")
                           color: T.text2; font.family: T.font; font.pixelSize: 14 }
                    SearchField { width: 360; height: 34; placeholder: shell.text("Search a commander, e.g. Atraxa")
                                  onEdited: function (t) { root.sg.setOwnSearch(t) } }
                }
                Flow {
                    width: parent.width; spacing: 6
                    Repeater {
                        model: root.sg.ownHits
                        Btn { required property var modelData
                              height: 32; compact: true; text: modelData.text; tip: modelData.tip
                              onClicked: root.sg.ownPick(modelData.i) }
                    }
                    Text { visible: root.sg.ownNone; text: shell.text("No matching commander found.")
                           color: T.dim; font.family: T.font; font.pixelSize: 13 }
                }
            }

            // ---- Suggestions (Brew or „Surprise me“) ----
            Flow {
                width: parent.width; spacing: 14
                Repeater {
                    model: root.br.results
                    delegate: IdeaTile {
                        required property var modelData
                        required property int index
                        title: modelData.title; info: modelData.info; img: modelData.img; tag: modelData.tag; owned: modelData.owned
                        onPick: root.br.pick(index)
                    }
                }
                Repeater {
                    model: root.sg.ideas
                    delegate: IdeaTile {
                        required property var modelData
                        title: modelData.title; info: modelData.info; img: modelData.img
                        onPick: root.sg.pickIdea(modelData.i)
                    }
                }
            }
        }
    }
}
