// Dialogs as a page in the window (no pop-ups): dimmed background, on top „← Back“ and the title, below the
// content centred in a card. Side prompts (while scanning) as a bar on the right edge – the camera stays.
import QtQuick

Item {
    id: sheetLayer   // not „layer“: that is a built-in property of every Item and shadows the id
    property var sheets
    anchors.fill: parent
    visible: rep.count > 0
    // all dialogs closed: focus back to the window (a field in the closed dialog must not receive keys any more)
    onVisibleChanged: if (!visible && sheetLayer.Window.contentItem) sheetLayer.Window.contentItem.forceActiveFocus()
    function typing() {   // is someone typing into a text field right now?
        var f = sheetLayer.Window.activeFocusItem
        return !!f && f.cursorPosition !== undefined
    }

    Repeater {
        id: rep
        model: sheetLayer.sheets ? sheetLayer.sheets.model : []   // one row per dialog (qsheets._Model)
        delegate: Item {
            id: sh
            required property var modelData
            anchors.fill: parent
            // fade in and out: new = from 0, closing = to 0, all others stay still
            readonly property bool closing: sh.modelData.closing === true
            opacity: sh.modelData.fresh && !closing ? 0 : (closing ? 1 : 1)
            enabled: !closing
            Component.onCompleted: opacity = closing ? 0 : 1
            onClosingChanged: if (closing) opacity = 0
            Behavior on opacity { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }
            // the card settles gently on opening (only with animations)
            scale: shell.animate ? (sh.closing ? 0.985 : 1) : 1
            Behavior on scale { enabled: shell.animate; NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

            readonly property bool isMenu: sh.modelData.kind === "menu"
            Rectangle {   // background
                anchors.fill: parent
                visible: !sh.modelData.side && !sh.isMenu
                color: T.bg
                // clicks stay here – a TapHandler does NOT stop them (then you'd click what's behind as well)
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true
                            onWheel: function (w) { w.accepted = true } }
            }
            Rectangle {
                id: panel
                visible: !sh.isMenu
                readonly property bool side: sh.modelData.side
                x: side ? parent.width - width : 0
                y: side ? 56 : 0
                width: side ? Math.min(620, Math.max(460, parent.width * 0.34)) : parent.width
                height: side ? parent.height - 56 : parent.height
                color: side ? T.bg : "transparent"
                border.width: side ? 1 : 0; border.color: T.line
                MouseArea { anchors.fill: parent; visible: panel.side; acceptedButtons: Qt.AllButtons; hoverEnabled: true
                            onWheel: function (w) { w.accepted = true } }   // sidebar: clicks stay here
                Row {
                    id: head
                    x: 24; y: 14
                    spacing: 14
                    Btn { text: panel.side ? "✕" : "←  " + shell.text("Back"); height: 34
                          onClicked: sheetLayer.sheets.back(sh.modelData.i) }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: sh.modelData.title
                           color: T.text; font.family: T.font; font.pixelSize: 20; font.bold: true }
                }
                Flickable {
                    ScrollHint {}
                    id: fl
                    x: 0; y: head.y + head.height + 14
                    width: parent.width; height: parent.height - y - 18
                    contentHeight: Math.max(height, card.height + 40)
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Rectangle {
                        id: card
                        readonly property string kind: sh.modelData.kind || ""
                        width: kind === "file" ? Math.min(fl.width - 48, 1200)
                               : kind === "color" ? 680
                               : panel.side ? fl.width - 28
                               : Math.min(fl.width - 48, sh.modelData.wide > 1 ? sh.modelData.wide : sh.modelData.wide ? 1100 : 680)
                        x: (fl.width - width) / 2
                        y: panel.side || kind === "file" ? 0 : Math.max(0, (fl.height - height) / 3)
                        height: kind === "file" ? fl.height - 4 : kind === "color" ? 366 : body.height + 34
                        radius: Math.min(16, T.panelRadius)
                        color: panel.side ? "transparent" : T.surface
                        border.width: panel.side ? 0 : 1; border.color: T.line
                        Mirror {
                            id: body
                            visible: card.kind === ""
                            x: 18; y: 16
                            width: card.width - 36
                            mirror: sh.modelData.mirror
                        }
                        Loader {   // file browser or colour picker (only if the dialog is one of those)
                            active: card.kind === "file" || card.kind === "color"
                            x: 18; y: 16; width: card.width - 36; height: card.height - 32
                            sourceComponent: card.kind === "file" ? fileC : colorC
                            Component { id: fileC; FileBrowser { fb: sh.modelData.tool } }
                            Component { id: colorC; ColorPicker { cp: sh.modelData.tool } }
                        }
                    }
                }
                Repeater {   // keyboard shortcuts of the dialog (e.g. 1–9)
                    model: sh.modelData.keys || []
                    Item {
                        required property var modelData
                        Shortcut {
                            sequence: modelData.seq
                            enabled: sh.modelData.i === rep.count - 1 && !sh.closing && !(modelData.notext && sheetLayer.typing())
                            onActivated: sheetLayer.sheets.key(sh.modelData.i, modelData.seq)
                        }
                    }
                }
                Shortcut { sequence: "Escape"; enabled: !sh.isMenu && sh.modelData.i === rep.count - 1 && !sh.closing
                           onActivated: sheetLayer.sheets.back(sh.modelData.i) }
                Component.onCompleted: if (!sh.isMenu) forceActiveFocus()
            }
            // ---- a menu (qdialogs.menu): light – the page stays as it is (no veil), a click beside it or
            // Esc closes, arrows + Enter choose, the first entry has the focus; a submenu lies over it with "<-" ----
            Loader {
                anchors.fill: parent
                active: sh.isMenu
                sourceComponent: Item {
                    Rectangle {   // clear surface: a click beside the menu closes it
                        anchors.fill: parent
                        color: "transparent"   // menus don't darken (only serious sheets do) – the clear surface still closes on a click beside
                        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true
                                    onPressed: sheetLayer.sheets.back(sh.modelData.i)
                                    onWheel: function (w) { w.accepted = true } }
                    }
                    MenuCard {
                        id: mcard
                        // at the click that opened it (a point on the screen; a submenu a little further in), moved
                        // inwards only where the window ends – without a point in the upper middle as before
                        readonly property var at: sh.modelData.at || []
                        readonly property var spot: at.length === 2 ? (function () {
                            var p = parent.mapFromGlobal(at[0], at[1])
                            return mcard.placeAt({x: p.x + (sh.modelData.sub ? 24 : 0), y: p.y + (sh.modelData.sub ? 18 : 0), w: 0, h: 0},
                                                 parent.width, parent.height)
                        })() : null
                        x: spot ? spot.x : (parent.width - width) / 2 + (sh.modelData.sub ? 24 : 0)
                        y: spot ? spot.y : Math.max(40, parent.height * 0.18) + (sh.modelData.sub ? 18 : 0)
                        maxHeight: at.length === 2 ? parent.height - 16 : parent.height - y - 40
                        title: sh.modelData.title
                        items: sh.modelData.items
                        sub: sh.modelData.sub
                        multi: sh.modelData.multi === true
                        freeText: sh.modelData.freeText === true
                        enabled: sh.modelData.i === rep.count - 1 && !sh.closing
                        onPicked: function (i) { sheetLayer.sheets.pick(sh.modelData.i, i) }
                        onBack: sheetLayer.sheets.back(sh.modelData.i)
                        onDone: sheetLayer.sheets.back(sh.modelData.i)
                        onTakeText: function (t) { sheetLayer.sheets.text(sh.modelData.i, t) }
                    }
                }
            }
        }
    }
}
