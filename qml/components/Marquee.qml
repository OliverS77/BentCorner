// Text in one line: too long -> at rest with „…“, on hover it starts briskly, scrolls evenly, slows at the end
// gently and stays there; on leave it eases back (like libview.MarqueeLabel). Edges softly faded out.
import QtQuick

Item {
    id: m
    property string text
    property color color: T.text
    property int px: 13
    property bool bold: false
    property bool running: false
    property int align: Text.AlignLeft
    property int format: Text.AutoText
    readonly property real over: Math.max(0, full.implicitWidth - width)
    clip: true

    Text {   // at rest: truncated
        anchors.fill: parent
        visible: m.off < 0.5
        text: m.text
        textFormat: m.format
        color: m.color; font.family: T.font; font.pixelSize: m.px; font.bold: m.bold
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
        horizontalAlignment: m.over > 0 ? Text.AlignLeft : m.align
    }
    property real off: 0
    Text {
        id: full
        visible: m.off >= 0.5
        x: -m.off
        height: parent.height
        verticalAlignment: Text.AlignVCenter
        text: m.text
        textFormat: m.format
        color: m.color; font.family: T.font; font.pixelSize: m.px; font.bold: m.bold
    }
    states: State { name: "run"; when: m.running && m.over > 0.5; PropertyChanges { target: m; off: m.over } }
    transitions: [
        Transition { to: "run"; NumberAnimation { property: "off"; duration: 400 + m.over / 38 * 1000
                                                  easing.type: Easing.OutSine } },
        Transition { from: "run"; NumberAnimation { property: "off"; duration: 450 + m.off * 2
                                                    easing.type: Easing.InOutSine } }
    ]
}
