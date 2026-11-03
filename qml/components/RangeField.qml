// Number for a range in the advanced search: empty/„–“ = not set (value −1).
import QtQuick

Rectangle {
    id: f
    property real value: -1
    property int decimals: 0
    signal committed(real value)
    height: 28
    radius: 8
    color: Qt.darker(T.surface, 1.15)
    border.width: 1; border.color: input.activeFocus ? T.line2 : T.line
    function fmt(v) { return v < 0 ? "–" : (decimals > 0 ? v.toFixed(decimals).replace(".", ",") : "" + Math.round(v)) }
    TextInput {
        id: input
        anchors.fill: parent; anchors.margins: 6
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        text: f.fmt(f.value)
        color: f.value < 0 ? T.dim : T.text
        font.family: T.font; font.pixelSize: 13
        selectByMouse: true
        onActiveFocusChanged: if (activeFocus && f.value < 0) { text = ""; color = T.text }
        onEditingFinished: {
            var t = text.replace(",", ".").trim()
            var v = (t === "" || t === "–") ? -1 : parseFloat(t)
            if (isNaN(v)) v = -1
            f.committed(v)
            text = f.fmt(v)
        }
    }
    onValueChanged: if (!input.activeFocus) input.text = fmt(value)
}
