// Head of the "Log" tab: title and the two views "Entries | Stats" right next to it, as words in the heading
// (selection = brightness: the open view bright, the other dim, hover in between) – so the stats aren't hidden behind
// a small key on the far right. Both views are their own page (SessionsPage, StatsPage); the nav shows "Log" for
// both, switching has no flip. A quiet line follows.
// Oliver is still trying this out (P9): viewsUp: false = the earlier look (keys "List | Stats" on the right).
import QtQuick

Item {
    id: sh
    property string view: "sessions"     // sessions | stats
    property string sub: ""
    readonly property bool viewsUp: true
    readonly property var views: [{ key: "sessions", text: shell.text("Logs") }, { key: "stats", text: shell.text("Stats") }]
    width: parent ? parent.width : 0
    height: 34
    FontMetrics { id: fmBig; font.family: T.font; font.pixelSize: 21; font.bold: true }
    FontMetrics { id: fmSmall; font.family: T.font; font.pixelSize: 13 }
    Row {
        id: ttl
        anchors.verticalCenter: parent.verticalCenter
        spacing: 12
        Row {   // Logs | Stats – the heading itself (no extra title in front: review .101)
            visible: sh.viewsUp
            spacing: 10
            Repeater {
                model: sh.views
                Row {
                    required property var modelData
                    required property int index
                    spacing: 10
                    Text { visible: index > 0; text: "|"; color: T.line2; font.family: T.font; font.pixelSize: 21 }
                    Text {
                        readonly property bool on: sh.view === modelData.key
                        text: modelData.text
                        color: on ? T.text : vh.hovered ? T.text2 : T.dim
                        font.family: T.font; font.pixelSize: 21; font.bold: on
                        Behavior on color { ColorAnimation { duration: 120 } }
                        HoverHandler { id: vh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: if (sh.view !== modelData.key) shell.pickView(modelData.key) }
                    }
                }
            }
        }
        Text { leftPadding: sh.viewsUp ? 12 : 0; topPadding: Math.max(0, fmBig.ascent - fmSmall.ascent)   // on the heading's baseline
               text: sh.sub; color: T.dim; font.family: T.font; font.pixelSize: 13 }
    }
    Row {   // the earlier look: two keys on the right
        visible: !sh.viewsUp
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        spacing: 8
        Repeater {
            model: [{ key: "sessions", text: shell.text("List") }, { key: "stats", text: shell.text("Stats") }]
            Btn {
                required property var modelData
                height: 32; width: 120; compact: true
                led: true; active: sh.view === modelData.key
                text: modelData.text
                onClicked: if (sh.view !== modelData.key) shell.pickView(modelData.key)
            }
        }
    }
}
