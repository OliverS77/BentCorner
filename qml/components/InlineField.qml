// A value edited right where it stands (scan tiles): reads like plain text, a quiet frame under the mouse says
// "you can change this"; a click puts the cursor in, Enter or leaving the field saves, Esc goes back. No edit mode,
// no save button (the user's rule). commit(text) -> the owner saves; returns false = not accepted (stays open, all selected).
import QtQuick

Item {
    id: f
    property string text
    property string placeholder
    property int pixelSize: 14
    property string family: T.font
    property bool bold: false
    property color color: T.text
    property int align: Text.AlignLeft
    property var commit: function (v) { return true }
    readonly property bool editing: input.visible
    implicitWidth: Math.max(label.implicitWidth, 24) + 6
    implicitHeight: label.implicitHeight + 2

    Rectangle {   // hover: a quiet frame; editing: a clear frame on a darker ground
        anchors.fill: parent; anchors.margins: -2
        radius: 5
        color: f.editing ? Qt.rgba(0, 0, 0, 0.35) : "transparent"
        border.width: 1
        border.color: f.editing ? Qt.rgba(1, 1, 1, 0.7) : Qt.rgba(1, 1, 1, hov.hovered ? 0.22 : 0)
    }
    Text {
        id: label
        anchors.fill: parent; anchors.leftMargin: 3; anchors.rightMargin: 3
        visible: !f.editing
        text: f.text !== "" ? f.text : f.placeholder
        color: f.text !== "" ? f.color : T.dim
        font.italic: f.text === ""
        font.family: f.family; font.pixelSize: f.pixelSize; font.bold: f.bold
        horizontalAlignment: f.align; verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    TextInput {
        id: input
        anchors.fill: parent; anchors.leftMargin: 3; anchors.rightMargin: 3
        visible: false
        color: T.text; selectionColor: Qt.rgba(1, 1, 1, 0.3); selectedTextColor: T.text
        font.family: f.family; font.pixelSize: f.pixelSize; font.bold: f.bold
        horizontalAlignment: f.align; verticalAlignment: Text.AlignVCenter
        clip: true
        function done(save) {
            if (!visible) return
            if (save && !f.commit(text)) { selectAll(); return }
            visible = false
        }
        Keys.onReturnPressed: done(true)
        Keys.onEnterPressed: done(true)
        Keys.onEscapePressed: done(false)
        onActiveFocusChanged: if (!activeFocus) done(true)
    }
    HoverHandler { id: hov; cursorShape: Qt.IBeamCursor }
    MouseArea {   // a press on the field is the field's (it never moves the tile underneath)
        anchors.fill: parent
        enabled: !f.editing
        cursorShape: Qt.IBeamCursor
        onClicked: { input.text = f.text; input.visible = true; input.forceActiveFocus(); input.selectAll() }
    }
}
