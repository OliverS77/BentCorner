// Input in place instead of a dialog: expands (height), inside fading in one after another – heading, field,
// below that OK / Cancel, all centred. Enter = OK, Esc or a click anywhere else = Cancel.
//   start(mode, ident, title, text, okText)   open (mode/ident: what for – the caller reads it back in accepted)
//   accepted(mode, ident, text) / canceled()
// fill: true = fills the caller's space (e.g. a tile) instead of expanding.
// extra: extra toggles below the field (centred), e.g. extra: Component { Column { spacing: 8; Seg { … } Seg { … } } }
// (a Component: like the rest it is built only while open)
import QtQuick

Item {
    id: ask
    property bool open: false
    property bool fill: false
    property string mode: ""
    property string ident: ""
    property string title: ""
    property string okText: ""
    property string placeholder: ""
    property Component extra: null
    signal accepted(string mode, string ident, string text)
    signal canceled()
    // the content is built only while open or closing (otherwise it would sit hidden in every tile/panel)
    readonly property Item field: body.item ? body.item.field : null

    function start(m, id, t, txt, ok) {
        mode = m; ident = id || ""; title = t; okText = ok || shell.text("OK")
        open = true
        field.text = txt || ""
        Qt.callLater(function () { if (field) field.focusAll() })
    }
    property real closedAt: 0   // just closed by a click beside it? (the button that opens it should then not reopen it)
    function cancel() { if (!open) return; open = false; closedAt = Date.now(); if (field) field.dropFocus(); canceled() }
    function justClosed() { return Date.now() - closedAt < 400 }
    function accept() {
        var t = field ? field.text.trim() : ""
        if (t === "") return
        open = false; field.dropFocus(); accepted(mode, ident, t)
    }

    width: parent ? parent.width : 300
    height: fill ? (parent ? parent.height : 160) : (open && body.item ? body.item.implicitHeight + 28 : 0)
    Behavior on height { enabled: shell.animate && !ask.fill; NumberAnimation { duration: 240 * shell.speed; easing.type: Easing.OutCubic } }
    clip: true
    visible: fill ? open : height > 0.5

    // click anywhere else = Cancel (the click still passes through)
    MouseArea {
        parent: ask.Window.window ? ask.Window.window.contentItem : ask
        anchors.fill: parent
        z: 10000
        enabled: ask.open; visible: ask.open
        acceptedButtons: Qt.AllButtons
        onPressed: function (m) {
            var p = mapToItem(ask, m.x, m.y)
            if (p.x < 0 || p.y < 0 || p.x > ask.width || p.y > ask.height) ask.cancel()
            m.accepted = false
        }
    }

    Loader {
        id: body
        active: ask.open || (!ask.fill && ask.height > 0.5)   // (no size: it would stretch the column)
        onLoaded: item.shownIn = true   // after the build: the parts still fade in one after another
        sourceComponent: Column {
            id: col
            property bool shownIn: false
            readonly property bool on: ask.open && shownIn
            property alias field: field
            width: Math.min(ask.width - 24, 320)
            x: (ask.width - width) / 2
            y: ask.fill ? (ask.height - implicitHeight) / 2 : 14
            spacing: 10
            Text {
                width: parent.width; horizontalAlignment: Text.AlignHCenter
                text: ask.title; color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true
                opacity: col.on ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 180 } }
            }
            SearchField {
                id: field
                width: parent.width; height: 36
                clearable: false
                placeholder: ask.placeholder
                opacity: col.on ? 1 : 0
                Behavior on opacity { SequentialAnimation { PauseAnimation { duration: 60 } NumberAnimation { duration: 180 } } }
                onAccepted: ask.accept()
                Keys.onEscapePressed: ask.cancel()
            }
            Loader {
                anchors.horizontalCenter: parent.horizontalCenter
                sourceComponent: ask.extra
                visible: ask.extra !== null
                opacity: col.on ? 1 : 0
                Behavior on opacity { SequentialAnimation { PauseAnimation { duration: 100 } NumberAnimation { duration: 180 } } }
            }
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 8
                opacity: col.on ? 1 : 0
                Behavior on opacity { SequentialAnimation { PauseAnimation { duration: 130 } NumberAnimation { duration: 180 } } }
                Btn { height: 32; width: 120; compact: true; primary: true; text: ask.okText; enabled: field.text.trim() !== ""
                      onClicked: ask.accept() }
                Btn { height: 32; width: 110; compact: true; text: shell.text("Cancel"); onClicked: ask.cancel() }
            }
        }
    }
}
