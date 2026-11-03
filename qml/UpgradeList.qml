// Upgrade mode in deck building: one row = one swap. Left the card going out, right the new one, in the middle
// arrow + reason + button. Clicking a row shows both cards large (comparison left, detail right).
// Data: upModel (roles see deckview.UpgradeModel), actions: upBridge.select/act/toggleChoose/chooseOut,
// texts: upTexts. As a separate QQuickWidget they come from the context (upgradeModel, bridge, texts).
import QtQuick
import QtQuick.Effects
import "components"

Item {
    id: root
    property int current: -1
    property var upModel: typeof upgradeModel !== "undefined" ? upgradeModel : null
    property var upBridge: typeof bridge !== "undefined" ? bridge : null
    property var upTexts: typeof texts !== "undefined" ? texts : ({})
    // Row under a point (window coordinates) – for „drag card from the deck list here“
    function rowAt(px, py) {
        var p = list.mapFromItem(null, px, py)
        if (p.x < 0 || p.y < 0 || p.x > list.width || p.y > list.height) return -1
        return list.indexAt(p.x + list.contentX, p.y + list.contentY)
    }

    ListView {
        id: list
        ScrollHint {}
        anchors.fill: parent
        anchors.rightMargin: 10
        model: root.upModel
        spacing: 12
        clip: true
        cacheBuffer: 1600
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 4000
        maximumFlickVelocity: 5000
        currentIndex: root.current
        highlightFollowsCurrentItem: false

        // when filling: rows glide in one after another
        populate: Transition {
            id: pop
            SequentialAnimation {
                PauseAnimation { duration: Math.min(pop.ViewTransition.index, 10) * 35 }
                ParallelAnimation {
                    NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 260; easing.type: Easing.OutCubic }
                    NumberAnimation { property: "y"; from: pop.ViewTransition.destination.y + 26
                                      duration: 320; easing.type: Easing.OutCubic }
                }
            }
        }

        delegate: Item {
            id: row
            required property int index
            required property string outName
            required property string outImg
            required property string outPrice
            required property bool hasOut
            required property string inName
            required property string inImg
            required property string inPrice
            required property string why
            required property bool done
            required property bool choosing
            required property var options

            width: list.width
            height: body.height + (choosing ? chooser.height + 10 : 0)
            Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

            readonly property bool selected: index === root.current
            readonly property real midW: Math.min(150, width * 0.28)
            readonly property real cardW: (width - midW - 36) / 2
            readonly property real cardH: cardW * 88 / 63

            Rectangle {   // row surface: selected = bright outline, hover slightly brighter
                anchors.fill: parent
                radius: 14
                color: row.selected ? T.surface2 : (hover.hovered ? T.surface : "transparent")
                border.width: 1.2
                border.color: row.selected ? T.line2 : "transparent"
                Behavior on color { ColorAnimation { duration: 160 } }
                Behavior on border.color { ColorAnimation { duration: 160 } }
            }
            HoverHandler { id: hover }
            TapHandler { onTapped: root.upBridge.select(row.index) }

            Item {
                id: body
                width: parent.width
                height: row.cardH + 84
                opacity: row.done ? 0.42 : 1.0
                Behavior on opacity { NumberAnimation { duration: 240 } }

                // left: out (or free slot)
                Card {
                    id: leftCard
                    x: 12; y: 12
                    width: row.cardW; height: row.cardH
                    source: row.outImg; name: row.hasOut ? row.outName : ""
                    empty: !row.hasOut
                    emptyText: root.upTexts.free
                }
                Text {
                    anchors.horizontalCenter: leftCard.horizontalCenter
                    y: leftCard.y + leftCard.height + 6
                    text: row.hasOut ? row.outPrice : ""
                    color: T.muted; font.family: T.font; font.pixelSize: 12
                }
                SmallButton {
                    anchors.horizontalCenter: leftCard.horizontalCenter
                    y: leftCard.y + leftCard.height + 28
                    visible: !row.done && row.options.length > 0
                    text: row.choosing ? root.upTexts.closeChoice : root.upTexts.otherOut
                    active: row.choosing
                    onClicked: root.upBridge.toggleChoose(row.index)
                }

                // middle: arrow, reason, button
                Item {
                    id: mid
                    x: 12 + row.cardW + 6; y: 12
                    width: row.midW; height: row.cardH
                    Column {
                        anchors.centerIn: parent
                        width: parent.width
                        spacing: 10
                        Canvas {   // arrow to the right, same stroke width as the nav icons
                            id: arrow
                            width: 54; height: 22
                            anchors.horizontalCenter: parent.horizontalCenter
                            property color c: row.selected ? T.text : T.text2
                            onCChanged: requestPaint()
                            onPaint: {
                                var g = getContext("2d"); g.reset()
                                g.strokeStyle = c; g.lineWidth = 2.2; g.lineCap = "round"; g.lineJoin = "round"
                                g.beginPath(); g.moveTo(3, 11); g.lineTo(width - 4, 11)
                                g.moveTo(width - 12, 4); g.lineTo(width - 4, 11); g.lineTo(width - 12, 18); g.stroke()
                            }
                            transform: Translate {
                                x: row.selected ? 4 : 0
                                Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutBack } }
                            }
                        }
                        Text {
                            width: parent.width
                            text: row.why
                            color: T.muted; font.family: T.font; font.pixelSize: 12
                            wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                            maximumLineCount: 6; elide: Text.ElideRight
                        }
                        SmallButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: row.done ? root.upTexts.undo : (row.hasOut ? root.upTexts.swap : root.upTexts.add)
                            active: !row.done
                            strong: true
                            onClicked: root.upBridge.act(row.index)
                        }
                    }
                }

                // right: in
                Card {
                    id: rightCard
                    x: mid.x + mid.width + 6; y: 12
                    width: row.cardW; height: row.cardH
                    source: row.inImg; name: row.inName
                }
                Text {
                    anchors.horizontalCenter: rightCard.horizontalCenter
                    y: rightCard.y + rightCard.height + 6
                    text: row.inPrice
                    color: T.muted; font.family: T.font; font.pixelSize: 12
                }
                Text {   // done
                    visible: row.done
                    anchors.horizontalCenter: rightCard.horizontalCenter
                    y: rightCard.y + rightCard.height + 30
                    text: "✓ " + root.upTexts.swapped
                    color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true
                }
            }

            // other card out: picker directly below the row (no pop-up)
            Column {
                id: chooser
                visible: row.choosing
                opacity: row.choosing ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
                x: 12; y: body.height
                width: row.width - 24
                spacing: 4
                // search: every card in the deck (not just the suggestions)
                property string q: ""
                readonly property var hits: q.trim() !== "" && root.upBridge ? root.upBridge.deckChoices(q) : []
                SearchField {
                    width: Math.min(360, chooser.width); height: 30
                    placeholder: shell.text("Search another card in the deck …")
                    text: chooser.q
                    onEdited: function (t) { chooser.q = t }
                }
                Repeater {
                    model: chooser.hits
                    delegate: OptionRow {
                        required property var modelData
                        width: chooser.width
                        label: modelData.name + (modelData.price ? "   ·   " + modelData.price : "")
                        current: false
                        onClicked: { chooser.q = ""; root.upBridge.chooseOutSid(row.index, modelData.sid) }
                    }
                }
                Repeater {
                    model: chooser.q.trim() === "" ? row.options : []
                    delegate: OptionRow {
                        required property var modelData
                        required property int index
                        width: chooser.width
                        label: modelData.name + (modelData.price ? "   ·   " + modelData.price : "")
                        current: modelData.current === true
                        onClicked: root.upBridge.chooseOut(row.index, index)
                    }
                }
                OptionRow {
                    width: chooser.width
                    label: root.upTexts.noneOut
                    current: !row.hasOut
                    onClicked: root.upBridge.chooseOut(row.index, -1)
                }
            }
        }

    }

    Text {   // empty
        anchors.centerIn: parent
        visible: list.count === 0
        width: parent.width * 0.8
        text: root.upTexts.empty
        color: T.dim; font.family: T.font; font.pixelSize: 14
        wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
    }

    // ---------- Building blocks ----------
    component Card: Item {
        id: card
        property string source
        property string name
        property bool empty: false
        property string emptyText
        // software renderer (no graphics card) can't do the mask shader: then the image without rounded corners
        readonly property bool fx: GraphicsInfo.api !== GraphicsInfo.Software
        scale: cardHover.hovered && !empty ? 1.03 : 1.0
        Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        HoverHandler { id: cardHover }

        Rectangle {   // shadow
            anchors.fill: parent; anchors.topMargin: 6; anchors.bottomMargin: -6
            radius: card.width * 0.05; color: "#000000"; opacity: card.empty ? 0 : 0.45
        }
        Rectangle {   // placeholder / free slot
            anchors.fill: parent
            radius: card.width * 0.05
            color: card.empty ? "transparent" : T.button
            border.width: card.empty ? 1.4 : 0
            border.color: T.line2
            visible: card.empty || img.status !== Image.Ready
            Text {
                anchors.fill: parent; anchors.margins: 12
                text: card.empty ? card.emptyText : card.name
                color: card.empty ? T.dim : T.text2
                font.family: T.font; font.pixelSize: 13
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            }
        }
        Image {
            id: img
            anchors.fill: parent
            source: card.empty ? "" : card.source
            asynchronous: true
            smooth: true; mipmap: true
            fillMode: Image.PreserveAspectFit
            sourceSize.width: 480  // fixed (= thumbnail): only stretched when scaling, not reloaded
            visible: !card.fx && status === Image.Ready && !card.empty
        }
        MultiEffect {   // rounded corners like real cards
            anchors.fill: img
            source: img
            visible: card.fx && img.status === Image.Ready && !card.empty
            maskEnabled: true
            maskSource: mask
            opacity: visible ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 220 } }
        }
        Item {
            id: mask
            anchors.fill: parent
            layer.enabled: true
            visible: false
            Rectangle { anchors.fill: parent; radius: card.width * 0.05; color: "black" }
        }
    }

    component SmallButton: Item {
        id: btn
        property string text
        property bool active: false
        property bool strong: false
        signal clicked()
        width: label.implicitWidth + 28
        height: 30
        Rectangle {
            anchors.fill: parent
            radius: 9
            gradient: Gradient {
                GradientStop { position: 0; color: tap.pressed ? Qt.darker(T.button, 1.6)
                                                       : Qt.lighter(T.button, btnHover.hovered ? 1.55 : 1.3) }
                GradientStop { position: 1; color: tap.pressed ? Qt.darker(T.button, 1.1) : Qt.darker(T.button, 1.18) }
            }
            border.width: 1
            border.color: btn.active && btn.strong ? T.line2 : "#000000"
        }
        Rectangle {   // status light like on the app's buttons
            visible: btn.active && btn.strong
            width: 4; height: 4; radius: 2
            x: 9; anchors.verticalCenter: parent.verticalCenter
            color: T.hi
        }
        Text {
            id: label
            anchors.centerIn: parent
            anchors.horizontalCenterOffset: btn.active && btn.strong ? 4 : 0
            text: btn.text
            color: T.text; font.family: T.font; font.pixelSize: 12; font.bold: true
        }
        HoverHandler { id: btnHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: tap; onTapped: btn.clicked() }
    }

    component OptionRow: Rectangle {
        id: opt
        property string label
        property bool current: false
        signal clicked()
        height: 30
        radius: 8
        color: optHover.hovered ? T.surface2 : T.surface
        border.width: current ? 1.2 : 0
        border.color: T.line2
        Behavior on color { ColorAnimation { duration: 120 } }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            x: 12
            text: (opt.current ? "✓  " : "") + opt.label
            color: T.text2; font.family: T.font; font.pixelSize: 12
        }
        HoverHandler { id: optHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: opt.clicked() }
    }
}
