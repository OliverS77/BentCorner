// Number field: − value +; value can be typed directly (Enter/leave = apply), mouse wheel only with focus.
import QtQuick

Rectangle {
    id: s
    property real value: 0
    property real from: 0
    property real to: 999
    property real step: 1
    property int decimals: 0
    property string suffix: ""
    property string prefix: ""
    signal committed(real value)
    implicitWidth: 120
    implicitHeight: 32
    radius: Math.min(height / 2, T.btnRadius * height / 34)
    color: Qt.darker(T.surface, 1.15)
    border.width: 1; border.color: input.activeFocus ? T.line2 : T.line
    opacity: enabled ? 1 : 0.5

    function fmt(v) { return s.prefix + (s.decimals > 0 ? v.toFixed(s.decimals).replace(".", ",") : Math.round(v)) + s.suffix }
    function commit(v) {
        v = Math.max(s.from, Math.min(s.to, v))
        if (s.decimals === 0) v = Math.round(v)
        s.value = v
        input.text = fmt(v)
        s.committed(v)
    }
    Text {
        id: minus
        width: 26; height: parent.height
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        text: "−"; color: mh.hovered ? T.text : T.muted; font.pixelSize: 15
        HoverHandler { id: mh; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: s.commit(s.value - s.step) }
    }
    TextInput {
        id: input
        anchors.left: minus.right; anchors.right: plus.left
        anchors.verticalCenter: parent.verticalCenter
        horizontalAlignment: Text.AlignHCenter
        text: s.fmt(s.value)
        color: T.text; font.family: T.font; font.pixelSize: 13
        selectByMouse: true
        onEditingFinished: {
            var t = text.replace(s.suffix, "").replace(s.prefix, "").replace(",", ".").trim()
            var v = parseFloat(t)
            if (!isNaN(v)) s.commit(v); else text = s.fmt(s.value)
        }
    }
    onValueChanged: if (!input.activeFocus) input.text = fmt(value)
    // decimals/unit may arrive after the value (bindings) – then reformat
    onDecimalsChanged: if (!input.activeFocus) input.text = fmt(value)
    onSuffixChanged: if (!input.activeFocus) input.text = fmt(value)
    onPrefixChanged: if (!input.activeFocus) input.text = fmt(value)
    Text {
        id: plus
        anchors.right: parent.right
        width: 26; height: parent.height
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        text: "+"; color: ph.hovered ? T.text : T.muted; font.pixelSize: 15
        HoverHandler { id: ph; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: s.commit(s.value + s.step) }
    }
    WheelHandler {
        enabled: input.activeFocus
        onWheel: function (ev) { s.commit(s.value + (ev.angleDelta.y > 0 ? s.step : -s.step)) }
    }
}
