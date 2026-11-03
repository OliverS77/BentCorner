// Input field (search): placeholder, ✕ to clear, Enter = apply. Looks like the app's fields.
import QtQuick

Rectangle {
    id: f
    property alias text: input.text
    property string placeholder
    property bool clearable: true
    property var keyHook: null
    signal edited(string text)
    signal accepted()
    signal upPressed()
    signal downPressed()
    readonly property bool inputFocus: input.activeFocus
    function focusAll() { input.forceActiveFocus(); input.selectAll() }
    function dropFocus() { if (input.activeFocus) input.focus = false }

    implicitHeight: 36
    opacity: enabled ? 1 : 0.5
    implicitWidth: 300
    radius: Math.min(height / 2, T.btnRadius * height / 34)
    color: Qt.darker(T.surface, 1.15)
    border.width: 1
    border.color: input.activeFocus ? T.line2 : T.line
    Behavior on border.color { ColorAnimation { duration: 150 } }

    TextInput {
        id: input
        anchors.left: parent.left; anchors.right: clear.left
        anchors.leftMargin: 12; anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        color: T.text
        selectionColor: T.line2
        selectedTextColor: T.text
        font.family: T.font; font.pixelSize: 14
        clip: true
        activeFocusOnTab: f.enabled
        // entered via Tab (not clicked): everything selected, typing replaces
        onActiveFocusChanged: if (activeFocus && !clickIn.active) selectAll()
        PointHandler { id: clickIn }
        onTextEdited: f.edited(text)
        onAccepted: f.accepted()
        // a key the owner takes before the field types it (keyHook(event) -> true = taken), e.g. 1–9 picking a row
        Keys.onPressed: function (ev) { if (f.keyHook && f.keyHook(ev)) ev.accepted = true }
        Keys.onEscapePressed: { if (text !== "") { text = ""; f.edited("") } else focus = false }
        Keys.onUpPressed: f.upPressed()
        Keys.onDownPressed: f.downPressed()
    }
    Text {
        anchors.fill: input
        verticalAlignment: Text.AlignVCenter
        visible: input.text === "" && !input.inputMethodComposing
        text: f.placeholder
        color: T.dim; font.family: T.font; font.pixelSize: 14
        elide: Text.ElideRight
    }
    Text {
        id: clear
        visible: f.clearable && input.text !== ""
        width: visible ? 26 : 0
        anchors.right: parent.right; anchors.rightMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        text: "✕"
        horizontalAlignment: Text.AlignHCenter
        color: clearHover.hovered ? T.text : T.dim
        font.pixelSize: 13
        HoverHandler { id: clearHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: { input.text = ""; f.edited(""); input.forceActiveFocus() } }
    }
    TapHandler { onTapped: input.forceActiveFocus() }
}
