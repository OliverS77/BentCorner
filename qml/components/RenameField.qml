// Renaming everywhere the same way (Oliver, review .101): a click on the name puts it in a text field, all of it
// selected – just type. Below, a strip with Confirm / Cancel slides out. Enter = Confirm, Esc or a click
// anywhere else = Cancel. No "Rename" button anywhere.
//   text, commit(newName) -> true = taken (false: stays open, all selected); canEdit: off = plain text
// The strip lies over what is below (it doesn't push the layout), so it fits into any header row.
import QtQuick

Item {
    id: f
    property string text
    property string placeholder
    property int pixelSize: 14
    property string family: T.font
    property bool bold: false
    property color color: T.text
    property bool canEdit: true
    property string tip: shell.text("Click to rename")
    property var commit: function (v) { return true }
    property bool editing: false
    implicitWidth: label.implicitWidth + 8
    implicitHeight: label.implicitHeight + 4

    function start() {
        if (!canEdit || editing) return
        input.text = f.text
        editing = true
        input.forceActiveFocus()
        input.selectAll()
    }
    function cancel() { if (!editing) return; editing = false; input.focus = false }
    function confirm() {
        var t = input.text.trim()
        if (t === "" || t === f.text) { cancel(); return }
        if (!f.commit(t)) { input.forceActiveFocus(); input.selectAll(); return }
        editing = false; input.focus = false
    }

    readonly property color ink: T.text   // T holds strings – as a color it has .r/.g/.b
    Rectangle {   // hover: a quiet frame; editing: a clear one
        anchors.fill: parent; anchors.margins: -3
        radius: 6
        color: f.editing ? T.surface2 : "transparent"
        border.width: 1
        border.color: Qt.rgba(f.ink.r, f.ink.g, f.ink.b, f.editing ? 0.6 : (hov.hovered && f.canEdit ? 0.22 : 0))
    }
    Text {
        id: label
        anchors.fill: parent; anchors.leftMargin: 4; anchors.rightMargin: 4
        visible: !f.editing
        text: f.text !== "" ? f.text : f.placeholder
        color: f.text !== "" ? f.color : T.dim
        font.family: f.family; font.pixelSize: f.pixelSize; font.bold: f.bold
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    TextInput {
        id: input
        anchors.fill: parent; anchors.leftMargin: 4; anchors.rightMargin: 4
        visible: f.editing
        color: f.color; selectionColor: Qt.rgba(f.ink.r, f.ink.g, f.ink.b, 0.3); selectedTextColor: f.color
        font.family: f.family; font.pixelSize: f.pixelSize; font.bold: f.bold
        verticalAlignment: Text.AlignVCenter
        clip: true
        Keys.onReturnPressed: f.confirm()
        Keys.onEnterPressed: f.confirm()
        Keys.onEscapePressed: f.cancel()
    }
    HoverHandler { id: hov; enabled: f.canEdit && !f.editing; cursorShape: Qt.IBeamCursor
        onHoveredChanged: if (hovered && f.tip !== "") { var q = f.mapToItem(null, f.width / 2, f.height); shell.tip(f.tip, q.x, q.y) }
                          else shell.tip("", 0, 0) }
    // (exclusive: a click on the name renames – it doesn't also open the tile or row it sits on)
    TapHandler { enabled: f.canEdit && !f.editing; gesturePolicy: TapHandler.ReleaseWithinBounds
                 onTapped: { shell.tip("", 0, 0); f.start() } }

    // the strip with Confirm / Cancel – slides out below the field
    Rectangle {
        id: strip
        z: 50
        x: -3; y: f.height + 6
        width: Math.max(f.width + 6, btns.implicitWidth + 16)
        height: f.editing ? btns.implicitHeight + 14 : 0
        Behavior on height { enabled: shell.animate; NumberAnimation { duration: 200 * shell.speed; easing.type: Easing.OutCubic } }
        visible: height > 0.5
        clip: true
        radius: 8; color: T.surface2; border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }   // clicks stay in the strip
        Row {
            id: btns
            x: 8; y: 7
            spacing: 6
            opacity: f.editing ? 1 : 0
            Behavior on opacity { SequentialAnimation { PauseAnimation { duration: 80 } NumberAnimation { duration: 160 } } }
            Btn { height: 30; compact: true; primary: true; text: shell.text("Confirm"); onClicked: f.confirm() }
            Btn { height: 30; compact: true; text: shell.text("Cancel"); onClicked: f.cancel() }
        }
    }
    // a click anywhere else = Cancel (the click still passes through)
    MouseArea {
        parent: f.Window.window ? f.Window.window.contentItem : f
        anchors.fill: parent
        z: 10000
        enabled: f.editing; visible: f.editing
        acceptedButtons: Qt.AllButtons
        onPressed: function (m) {
            var a = mapToItem(f, m.x, m.y), b = mapToItem(strip, m.x, m.y)
            var inField = a.x >= -3 && a.y >= -3 && a.x <= f.width + 3 && a.y <= f.height + 3
            var inStrip = b.x >= 0 && b.y >= 0 && b.x <= strip.width && b.y <= strip.height
            if (!inField && !inStrip) f.cancel()
            m.accepted = false
        }
    }
}
