// A longer text edited right where it stands (scan tiles: the log's stream text) – like InlineField, but over
// several lines: reads like plain text (placeholder in italics when empty), a quiet frame under the mouse; a click
// puts the cursor in, leaving the field (a click beside it) or Ctrl+Enter saves, Esc goes back. Enter = a new line.
// commit(text) -> the owner saves; returns false = not accepted (stays open).
import QtQuick

Item {
    id: f
    property string text
    property string placeholder
    property int pixelSize: 12
    property var commit: function (v) { return true }
    readonly property bool editing: input.visible

    Rectangle {
        anchors.fill: parent; anchors.margins: -2; anchors.topMargin: 3
        radius: 5
        color: f.editing ? Qt.rgba(0, 0, 0, 0.35) : "transparent"
        border.width: 1
        border.color: f.editing ? Qt.rgba(1, 1, 1, 0.7) : Qt.rgba(1, 1, 1, hov.hovered ? 0.22 : 0)
    }
    Rectangle { width: parent.width; height: T.tile.line; color: Qt.rgba(1, 1, 1, 0.09) }
    Text {
        id: label
        anchors.fill: parent; anchors.topMargin: 6; anchors.leftMargin: 2; anchors.rightMargin: 2
        visible: !f.editing
        text: f.text !== "" ? f.text : f.placeholder
        color: f.text !== "" ? T.text2 : T.dim
        font.italic: f.text === ""
        font.family: T.font; font.pixelSize: f.pixelSize
        wrapMode: Text.WordWrap; elide: Text.ElideRight; maximumLineCount: 3
    }
    TextEdit {
        id: input
        anchors.fill: parent; anchors.topMargin: 6; anchors.leftMargin: 2; anchors.rightMargin: 2
        visible: false
        color: T.text; selectionColor: Qt.rgba(1, 1, 1, 0.3); selectedTextColor: T.text
        font.family: T.font; font.pixelSize: f.pixelSize
        wrapMode: TextEdit.Wrap
        clip: true
        function done(save) {
            if (!visible) return
            if (save && !f.commit(text)) { selectAll(); return }
            visible = false
        }
        Keys.onPressed: function (e) {
            if (e.key === Qt.Key_Escape) { done(false); e.accepted = true }
            else if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && (e.modifiers & Qt.ControlModifier)) { done(true); e.accepted = true }
        }
        onActiveFocusChanged: if (!activeFocus) done(true)
    }
    HoverHandler { id: hov; cursorShape: Qt.IBeamCursor }
    MouseArea {   // a press on the field is the field's (it never moves the tile underneath)
        anchors.fill: parent
        enabled: !f.editing
        cursorShape: Qt.IBeamCursor
        onClicked: { input.text = f.text; input.visible = true; input.forceActiveFocus(); input.cursorPosition = input.length }
    }
}
