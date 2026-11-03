// Deck tile of the overview (like deckview.DeckTileDelegate). kind "deck": image of the title card (upper part) with
// soft fade, chip BUILT/NOT BUILT (click toggles), name, format · cards, price, colours, bracket.
// kind "new": „+ New deck“ (suggestion · build yourself · import), on hover three parts – one way each (two without
// suggestions: games other than Magic).
import QtQuick
import QtQuick.Effects

Item {
    id: t
    property var d: ({})
    signal open(int half)
    signal builtToggled()
    signal menuRequested(real x, real y)
    signal selectToggled()
    property bool selecting: false     // mark mode: click marks instead of opening
    property bool selected: false
    readonly property bool isNew: d.kind === "new"
    property bool suggest: true                // deck suggestions from the collection (Magic)
    property string importHint: shell.text("Moxfield, Archidekt, text …")
    // parts of the new-deck tile; "half" = what openTile expects (0 suggestion, 1 build yourself, 2 import)
    readonly property var parts: [{sym: "spark", t: shell.text("Bent°Corner suggestion"), s: shell.text("from your collection"), half: 0},
                                  {sym: "plus", t: shell.text("Build it yourself"), s: shell.text("empty deck"), half: 1},
                                  {sym: "import", t: shell.text("Import deck list"), s: t.importHint, half: 2}].slice(t.suggest ? 0 : 1)
    property real hv: hover.hovered ? 1 : 0
    Behavior on hv { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    property int half: Math.max(0, Math.min(t.parts.length - 1, Math.floor(hover.point.position.y / Math.max(1, height / t.parts.length))))
    readonly property var mana: ({W: "#f4ecc8", U: "#4a90d9", B: "#8c7f86", R: "#e0553d", G: "#3f9b5a", C: "#b6b6b6"})

    Item {
        id: card
        x: 10; y: 12 - 6 * t.hv
        width: t.width - 20; height: t.height - 22
        readonly property real rad: Math.min(18, T.panelRadius)

        // ---------- New deck ----------
        Rectangle {
            visible: t.isNew
            anchors.fill: parent
            radius: card.rad
            color: Qt.rgba(0.07, 0.07, 0.08, 0.6 + 0.2 * t.hv)
            border.width: 2
            border.color: Qt.tint(T.line2, Qt.rgba(1, 1, 1, 0.5 * t.hv))
            Column {   // at rest: large plus
                anchors.centerIn: parent
                opacity: 1 - t.hv
                spacing: 6
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: "+"; color: T.dim
                       font.family: T.font; font.pixelSize: 64; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("New deck"); color: T.text
                       font.family: T.font; font.pixelSize: 17; font.bold: true }
                Text { anchors.horizontalCenter: parent.horizontalCenter
                       text: t.suggest ? shell.text("Suggestion · build your own · import") : shell.text("Build your own · import")
                       color: T.muted
                       font.family: T.font; font.pixelSize: 12 }
            }
            Repeater {   // hover: three parts (two without suggestions)
                model: t.parts
                Item {
                    required property var modelData
                    required property int index
                    x: 0; y: index * card.height / t.parts.length
                    width: card.width; height: card.height / t.parts.length
                    opacity: t.hv
                    Rectangle { anchors.fill: parent; anchors.margins: 6; radius: card.rad * 0.7
                                color: Qt.rgba(1, 1, 1, t.half === index ? 0.08 * t.hv : 0) }
                    Column {
                        anchors.centerIn: parent; spacing: 4
                        NavIcon { anchors.horizontalCenter: parent.horizontalCenter; key: modelData.sym; s: 1.25
                                  color: t.half === index ? T.text : T.dim; play: t.half === index }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.t; color: T.text
                               font.family: T.font; font.pixelSize: 16; font.bold: true }
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.s; color: T.muted
                               font.family: T.font; font.pixelSize: 12 }
                    }
                }
            }
            Repeater {
                model: t.parts.length - 1
                Rectangle { required property int index
                            visible: t.hv > 0.02; opacity: t.hv; x: 14; width: card.width - 28; height: 1
                            y: (index + 1) * card.height / t.parts.length; color: T.line2 }
            }
        }

        // ---------- Deck ----------
        Item {
            visible: !t.isNew
            anchors.fill: parent
            Rectangle {   // glow on hover
                anchors.fill: parent; anchors.margins: -5
                radius: card.rad + 5; color: "transparent"
                border.width: 5; border.color: Qt.rgba(1, 1, 1, 0.12 * t.hv)
            }
            Rectangle {
                id: body
                anchors.fill: parent
                radius: card.rad
                color: Qt.darker(T.surface, 1.05)
                clip: true
                layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                layer.effect: MultiEffect { maskEnabled: true; maskSource: bodyMask }
                Item {   // upper part of the title card (illustration)
                    id: art
                    width: body.width; height: body.height * 0.62
                    clip: true
                    readonly property real sw: 0.84   // image crop (relative to the card width)
                    readonly property real sh: 0.45 * 88 / 63
                    readonly property real k: Math.max(width / sw, height / sh)   // card width in px
                    Image {
                        source: t.d.art || ""
                        asynchronous: true; smooth: true; mipmap: true
                        sourceSize.width: 480
                        width: art.k; height: art.k * 88 / 63
                        x: -art.k * 0.08 - (art.k * art.sw - art.width) / 2
                        y: -art.k * 88 / 63 * 0.11 - (art.k * art.sh - art.height) / 2
                    }
                    Rectangle { anchors.fill: parent; visible: !t.d.art; gradient: Gradient {
                        GradientStop { position: 0; color: T.accent_deep } GradientStop { position: 1; color: T.surface2 } } }
                    Rectangle {   // soft fade downwards
                        anchors.bottom: parent.bottom; width: parent.width; height: 60
                        gradient: Gradient { GradientStop { position: 0; color: "transparent" }
                                             GradientStop { position: 1; color: body.color } }
                    }
                    ArtistTag { name: t.d.art ? (t.d.artist || "") : ""; anchors.bottomMargin: 14 }
                }
                Text {
                    x: 14; y: art.height + 6; width: parent.width - 28; height: 24
                    verticalAlignment: Text.AlignVCenter
                    text: t.d.name || ""; elide: Text.ElideRight
                    color: T.text; font.family: T.font; font.pixelSize: 17; font.bold: true
                }
                Text {
                    x: 14; y: art.height + 32; width: parent.width - 28
                    text: (t.d.fmt || "") + " · " + (t.d.count || "") + " " + shell.text("Cards")
                    color: T.muted; font.family: T.font; font.pixelSize: 12
                }
                Text {
                    anchors.right: parent.right; anchors.rightMargin: 14; y: art.height + 32
                    text: t.d.price || ""
                    color: T.text; font.family: T.font; font.pixelSize: 12; font.bold: true
                }
                Row {
                    x: 14; y: art.height + 56; spacing: 4
                    Repeater { model: (t.d.identity || "").split("")
                        Rectangle { required property string modelData; width: 14; height: 14; radius: 7
                                    color: t.mana[modelData] || "#b6b6b6" } }
                }
                Text {
                    visible: t.d.bracket > 0
                    anchors.right: parent.right; anchors.rightMargin: 14; y: art.height + 54
                    text: shell.text("Bracket") + " " + t.d.bracket
                    color: T.text2; font.family: T.font; font.pixelSize: 12
                }
            }
            Item { id: bodyMask; anchors.fill: parent; layer.enabled: true; visible: false
                   Rectangle { anchors.fill: parent; radius: card.rad; color: "black" } }
            Rectangle {
                anchors.fill: parent; radius: card.rad; color: "transparent"
                border.width: 1.3; border.color: Qt.tint(T.line, Qt.rgba(1, 1, 1, 0.35 * t.hv))
            }
            Rectangle {   // chip BUILT / NOT BUILT
                id: chip
                x: 10; y: 10
                width: chipText.implicitWidth + 18; height: 22; radius: 11
                color: t.d.built ? (ch.hovered ? "#f5f5f5" : "#e1e1e1") : Qt.rgba(0.04, 0.04, 0.04, 0.78)
                border.width: 1
                border.color: t.d.built ? Qt.rgba(0, 0, 0, 0.6) : Qt.rgba(0.78, 0.78, 0.78, ch.hovered ? 0.86 : 0.43)
                Text {
                    id: chipText
                    anchors.centerIn: parent
                    text: t.d.built ? shell.text("BUILT") : shell.text("NOT BUILT")
                    color: t.d.built ? T.onHi : Qt.rgba(0.92, 0.92, 0.92, ch.hovered ? 1 : 0.67)
                    font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2
                }
                HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: t.builtToggled() }
            }
        }
    }
    // selection mode: no checkmarks – not selected = slightly dimmed, hovering = almost normal, selected = normal
    // (like every selection in the program, e.g. the deck tiles in Import/Export)
    // (review .90: the unselected ones clearly darker – 0.62 was too close to "selected")
    readonly property real selOpacity: !t.selecting ? 1 : t.isNew ? 0.15 : (t.selected ? 1 : (t.hv > 0.5 ? 0.7 : 0.3))
    opacity: selOpacity
    Behavior on opacity { NumberAnimation { duration: 160 } }
    Rectangle {   // menu „⋯“ (the same as via right click) – on hover, left of the mark circle
        id: menuDot
        visible: !t.isNew && t.hv > 0.01 && !t.selecting
        x: card.x + card.width - width - 10; y: card.y + 10
        width: 34; height: 26; radius: 13
        color: Qt.rgba(0.04, 0.04, 0.04, mdh.hovered ? 0.92 : 0.72)
        border.width: 1.5; border.color: Qt.rgba(0.85, 0.85, 0.85, mdh.hovered ? 1 : 0.7)
        Text { anchors.centerIn: parent; text: "⋯"; color: "#ededed"; font.pixelSize: 16; font.bold: true }
        HoverHandler { id: mdh; cursorShape: Qt.PointingHandCursor }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: function (ev) {
            var p = ev.position
            if (menuDot.visible && p.x >= menuDot.x && p.x <= menuDot.x + menuDot.width && p.y >= menuDot.y && p.y <= menuDot.y + menuDot.height) {
                var q = t.mapToItem(null, menuDot.x, menuDot.y + menuDot.height + 4); t.menuRequested(q.x, q.y); return }
            if (!t.isNew && p.x >= card.x + chip.x && p.x <= card.x + chip.x + chip.width && p.y >= card.y + chip.y && p.y <= card.y + chip.y + chip.height) return
            if (t.selecting && t.isNew) return
            if (!t.isNew && (t.selecting || (ev.modifiers & Qt.ControlModifier))) { t.selectToggled(); return }
            t.open(t.isNew ? t.parts[Math.max(0, Math.min(t.parts.length - 1, Math.floor(p.y / (t.height / t.parts.length))))].half : -1)
        }
    }
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: function (ev) { if (!t.isNew) { var p = t.mapToItem(null, ev.position.x, ev.position.y); t.menuRequested(p.x, p.y) } }
    }
}
