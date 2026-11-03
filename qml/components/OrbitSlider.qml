// Bent°Corner Orbit: a slider with three stops – Core · Near Orbit · Full Orbit (Oliver, 2026-10-29; layout .92:
// "Apple would only have the slider – a little more transparency, but not 15 lines nobody reads").
// Top: the Orbit picture follows the handle. Below the slider three columns of fixed width, each under its stop –
// everything always there, nothing comes or goes (no jumping height); selection = brightness, a click on a column
// picks it too. Then one shared small line with "More ›" (the details slide open inline). Leaving Full Orbit has a
// reserved place of fixed height: the sentence – in the settings with "Stay / Leave" – only fades in and out.
// The same slider sits in the setup, in "What's new?" and in Settings → Friends & privacy (qform "orbit").
import QtQuick

Item {
    id: o
    property int level: 1
    property var names: ["Core", "Near Orbit", "Full Orbit"]
    property var lines: ["", "", ""]        // Oliver's sentence, short
    property var points: [[], [], []]       // 2–3 very short lines per level: what you get / what goes out
    property var outs: ["", "", ""]         // the exact small print – behind "More ›"
    property string terms: ""               // Full Orbit: terms of use + age (link) – always in its column
    property string foot: ""                // the shared line under the columns
    property string moreText: "More"
    property string lessText: "Less"
    property string privacy: ""             // link to the privacy policy at the end of the details
    property string leaveNote: ""           // set while Full Orbit is on: what leaving does (reserved place)
    property bool confirm: false            // settings: "Leave Full Orbit? [Stay] [Leave]" in the reserved place
    property string leaveAsk: ""
    property string stayText: ""
    property string leaveText: ""
    property bool compact: false            // settings: smaller picture
    signal picked(int level)
    signal decided(bool leave)

    implicitWidth: 600
    implicitHeight: col.implicitHeight

    property real live: level               // follows the finger while dragging, otherwise the level
    property bool dragging: false
    property bool more: false
    readonly property int shownStop: Math.round(live)
    onLevelChanged: if (!dragging) live = level
    function settle() {
        if (!dragging) return
        var v = Math.round(live)
        dragging = false
        live = v
        if (v !== level) picked(v)
    }
    Behavior on live { enabled: shell.animate && !o.dragging; NumberAnimation { duration: 520 * shell.speed; easing.type: Easing.InOutCubic } }

    Column {
        id: col
        width: parent.width
        spacing: o.compact ? 10 : 14
        OrbitIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            width: o.compact ? 76 : 116; height: width
            lv: shell.animate ? o.live : o.shownStop   // without animations: the picture jumps to the stop
        }
        Item {   // the track – its three stops sit exactly over the middle of the three columns
            id: track
            width: parent.width; height: 34
            function xOf(v) { return width / 6 + v * width / 3 }
            function vOf(x) { return Math.max(0, Math.min(2, (x - width / 6) * 3 / width)) }
            Rectangle { x: track.xOf(0); y: 16; width: track.xOf(2) - x; height: 2; radius: 1; color: T.line2 }
            Rectangle { x: track.xOf(0); y: 16; width: track.xOf(o.live) - x; height: 2; radius: 1; color: T.text2 }
            Repeater {
                model: 3
                Rectangle {
                    required property int index
                    x: track.xOf(index) - 4; y: 13; width: 8; height: 8; radius: 4
                    color: index <= o.live + 0.01 ? T.text2 : T.line2
                }
            }
            Rectangle {   // the handle
                x: track.xOf(o.live) - 11; y: 6; width: 22; height: 22; radius: 11
                color: T.hi
                border.width: 1; border.color: T.line2
                scale: tm.pressed || th.hovered ? 1.08 : 1
                Behavior on scale { NumberAnimation { duration: 120 } }
            }
            HoverHandler { id: th; cursorShape: Qt.PointingHandCursor }
            MouseArea {
                id: tm
                x: track.xOf(0) - 18; width: track.xOf(2) - track.xOf(0) + 36; y: -6; height: parent.height + 12
                // the sheet / settings page around is a Flickable: without this it takes over the drag as soon as the
                // hand drifts a few pixels up or down – then the handle jumped back (Oliver, real .90)
                preventStealing: true
                onPressed: function (m) { o.dragging = true; o.live = track.vOf(m.x + x) }
                onPositionChanged: function (m) { if (pressed) o.live = track.vOf(m.x + x) }
                onReleased: o.settle()
                onCanceled: o.settle()   // taken away after all: the stop the handle is nearest to counts, no jump back
            }
            Keys.onLeftPressed: if (o.level > 0) o.picked(o.level - 1)
            Keys.onRightPressed: if (o.level < 2) o.picked(o.level + 1)
            activeFocusOnTab: true
        }
        Row {   // three columns of fixed width, each under its stop – selection = brightness
            id: cols
            width: parent.width
            Repeater {
                model: 3
                Item {
                    id: cl
                    required property int index
                    readonly property bool on: index === o.shownStop
                    readonly property color ink: on ? T.hi : (ch.hovered ? T.text2 : T.dim)
                    width: cols.width / 3
                    height: cc.implicitHeight   // always the same: nothing in a column comes or goes
                    Column {
                        id: cc
                        x: 6; width: parent.width - 12
                        spacing: o.compact ? 4 : 6
                        Text {
                            width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                            text: o.names[cl.index] || ""
                            color: cl.ink; font.family: T.font; font.pixelSize: o.compact ? 14 : 15; font.bold: true
                            Behavior on color { ColorAnimation { duration: 160 } }
                        }
                        Text {
                            width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                            text: o.lines[cl.index] || ""
                            color: cl.on ? T.text : cl.ink; font.family: T.font; font.pixelSize: o.compact ? 13 : 14
                            Behavior on color { ColorAnimation { duration: 160 } }
                        }
                        Item { width: 1; height: 2 }
                        Repeater {
                            model: o.points[cl.index] || []
                            Item {
                                required property string modelData
                                width: cc.width; height: pt.implicitHeight
                                Text {
                                    id: pt
                                    width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                                    text: modelData
                                    color: cl.on ? T.text2 : cl.ink; font.family: T.font; font.pixelSize: 13
                                    Behavior on color { ColorAnimation { duration: 160 } }
                                }
                            }
                        }
                        Text {   // Full Orbit: terms of use and age – before you choose it, always visible
                            visible: cl.index === 2 && o.terms !== ""
                            width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                            text: o.terms; textFormat: Text.StyledText
                            color: cl.on ? T.text2 : cl.ink; linkColor: color   // links in the text colour, only underlined
                            font.family: T.font; font.pixelSize: 13
                            onLinkActivated: function (l) { Qt.openUrlExternally(l) }
                            HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        }
                    }
                    HoverHandler { id: ch; cursorShape: cl.on ? Qt.ArrowCursor : Qt.PointingHandCursor }
                    TapHandler { onTapped: if (cl.index !== o.level) o.picked(cl.index) }
                }
            }
        }
        Item {   // leaving Full Orbit: a reserved place of fixed height – the sentence (and the question) only fade
            visible: o.leaveNote !== ""
            width: parent.width; height: o.confirm ? 70 : 38
            readonly property bool shown: o.leaveNote !== "" && o.shownStop < 2
            opacity: shown ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }
            Column {
                width: parent.width; spacing: 6
                Text {
                    width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                    text: o.leaveNote; color: T.text2; font.family: T.font; font.pixelSize: 12; lineHeight: 1.1
                }
                Row {
                    visible: o.confirm
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8
                    Text { anchors.verticalCenter: parent.verticalCenter; text: o.leaveAsk; color: T.text
                           font.family: T.font; font.pixelSize: 13 }
                    Btn { height: 28; compact: true; text: o.stayText; enabled: parent.parent.parent.shown
                          onClicked: o.decided(false) }
                    Btn { height: 28; compact: true; text: o.leaveText; danger: true; enabled: parent.parent.parent.shown
                          onClicked: o.decided(true) }
                }
            }
        }
        Text {   // one shared line, small – with "More ›" (the details slide open right here)
            width: parent.width; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
            textFormat: Text.StyledText
            text: o.foot + (o.outs.length ? "  <a href='more'>" + (o.more ? o.lessText + " ‹" : o.moreText + " ›") + "</a>" : "")
            color: T.dim; linkColor: T.text2; font.family: T.font; font.pixelSize: 12
            onLinkActivated: o.more = !o.more
            HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
        }
        Item {   // the details: exactly what leaves the device per level
            width: parent.width
            height: o.more ? details.implicitHeight : 0
            clip: true
            Behavior on height { enabled: shell.animate; NumberAnimation { duration: 240 * shell.speed; easing.type: Easing.OutCubic } }
            Column {
                id: details
                width: parent.width; spacing: 6
                Repeater {
                    model: 3
                    Text {
                        required property int index
                        width: details.width; wrapMode: Text.Wrap
                        textFormat: Text.StyledText
                        text: "<b>" + (o.names[index] || "") + ":</b> " + (o.outs[index] || "")
                        color: T.muted; font.family: T.font; font.pixelSize: 12; lineHeight: 1.1
                    }
                }
                Text {
                    visible: o.privacy !== ""
                    width: details.width; wrapMode: Text.Wrap
                    text: o.privacy; textFormat: Text.StyledText
                    color: T.muted; linkColor: T.text2; font.family: T.font; font.pixelSize: 12
                    onLinkActivated: function (l) { Qt.openUrlExternally(l) }
                    HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                }
            }
        }
    }
}
