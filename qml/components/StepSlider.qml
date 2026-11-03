// Slider with whole steps (like libview.StepSlider): the handle follows the mouse while dragging, released it glides
// softly to the nearest step; arrow keys jump one step; mouse wheel deliberately not. Number in the handle.
import QtQuick

Item {
    id: s
    property int from: 5
    property int to: 10
    property int value: 6
    property bool showNumber: true
    signal moved(int value)

    implicitWidth: 40 + 26 * (to - from)
    implicitHeight: 34
    activeFocusOnTab: true

    readonly property real a: 11
    readonly property real b: width - 11
    function xOf(v) { return a + (v - from) / Math.max(1, to - from) * (b - a) }
    function vOf(x) { return from + Math.max(0, Math.min(1, (x - a) / (b - a))) * (to - from) }

    // value stays bound (e.g. to lib.columns) – only the display is dragged; otherwise the slider would no longer
    // follow when the value changes from outside (other view = other value)
    property int shown: value
    property real pos: value
    Behavior on pos { enabled: !drag.active; NumberAnimation { duration: 220; easing.type: Easing.OutBack } }
    onValueChanged: { shown = value; if (!drag.active) pos = value }
    function set(v) {
        v = Math.max(from, Math.min(to, Math.round(v)))
        if (v !== shown) { shown = v; moved(v) }
    }

    readonly property real cy: 17
    Rectangle { x: s.a; y: s.cy - 2.5; width: s.b - s.a; height: 5; radius: 2.5; color: Qt.lighter(T.button, 1.25) }
    Rectangle {
        x: s.a; y: s.cy - 2.5; height: 5; radius: 2.5
        width: Math.max(0, s.xOf(s.pos) - s.a)
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: T.accent_deep }
            GradientStop { position: 1; color: T.accent } }
    }
    Repeater {
        model: s.to - s.from + 1
        Rectangle {
            readonly property int v: s.from + index
            readonly property real r: v === s.shown ? 3.2 : 2.4
            x: s.xOf(v) - r; y: s.cy - r
            width: r * 2; height: r * 2; radius: r
            color: v <= s.pos + 0.01 ? T.accent : T.line2
        }
    }
    Rectangle {   // handle
        id: knob
        readonly property real glow: Math.max(hover.hovered ? 1 : 0, drag.active ? 1 : 0)
        width: 22; height: 22; radius: 11
        x: s.xOf(s.pos) - 11; y: s.cy - 11
        color: T.surface2
        border.width: 2
        border.color: glow > 0 ? T.text : T.accent
        Behavior on border.color { ColorAnimation { duration: 160 } }
        Text {
            visible: s.showNumber
            anchors.centerIn: parent
            text: s.shown
            color: T.text; font.family: T.font; font.pixelSize: 11; font.bold: true
        }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    DragHandler {
        id: drag
        target: null
        xAxis.enabled: true; yAxis.enabled: false
        onActiveChanged: if (!active) s.pos = s.shown
        onCentroidChanged: if (active) { s.pos = s.vOf(centroid.position.x); s.set(s.pos) }
    }
    TapHandler { onTapped: function (ev) { s.forceActiveFocus(); s.set(s.vOf(ev.position.x)); s.pos = s.shown } }
    Keys.onLeftPressed: { set(shown - 1); pos = shown }
    Keys.onDownPressed: { set(shown - 1); pos = shown }
    Keys.onRightPressed: { set(shown + 1); pos = shown }
    Keys.onUpPressed: { set(shown + 1); pos = shown }
}
