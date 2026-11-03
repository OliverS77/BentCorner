// Tags: input field (Enter adds) with matching suggestions below (tags already used, no pop-up),
// the tags as chips with ✕. Reports added(tag) and removed(tag).
import QtQuick

Column {
    id: root
    property var tags: []
    property var suggestions: []
    property string placeholder: ""
    signal added(string tag)
    signal removed(string tag)
    spacing: 6

    property string typed: ""
    readonly property var matches: {
        var t = typed.trim().toLowerCase(), out = []
        if (!t) return out
        for (var i = 0; i < suggestions.length && out.length < 6; i++) {
            var s = suggestions[i]
            if (s.toLowerCase().indexOf(t) >= 0 && tags.indexOf(s) < 0) out.push(s)
        }
        return out
    }
    function add(t) {
        t = (t || "").trim()
        sf.text = ""; typed = ""
        if (t && tags.indexOf(t) < 0) added(t)
    }

    SearchField {
        id: sf
        width: root.width; height: 32
        clearable: false
        placeholder: root.placeholder || shell.text("Type a tag + Enter, e.g. convention, local store")
        onEdited: function (t) { root.typed = t }
        onAccepted: root.add(text)
    }
    Flow {   // suggestions
        visible: root.matches.length > 0
        width: root.width; spacing: 6
        Repeater {
            model: root.matches
            Rectangle {
                required property var modelData
                height: 26; width: st.implicitWidth + 20; radius: 13
                color: sh.hovered ? T.surface2 : "transparent"; border.width: 1; border.color: T.line2
                Text { id: st; anchors.centerIn: parent; text: "+ " + modelData; color: T.text2; font.family: T.font; font.pixelSize: 12 }
                HoverHandler { id: sh; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.add(modelData) }
            }
        }
    }
    Flow {   // tags
        visible: root.tags.length > 0
        width: root.width; spacing: 6
        Repeater {
            model: root.tags
            Rectangle {
                required property var modelData
                height: 28; width: tt.implicitWidth + 40; radius: 14
                color: T.surface2; border.width: 1; border.color: T.line2
                Text { id: tt; x: 12; anchors.verticalCenter: parent.verticalCenter; text: modelData
                       color: T.text; font.family: T.font; font.pixelSize: 13 }
                Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                       text: "✕"; color: xh.hovered ? T.text : T.muted; font.pixelSize: 12
                       HoverHandler { id: xh; cursorShape: Qt.PointingHandCursor }
                       TapHandler { onTapped: root.removed(modelData) } }
            }
        }
    }
}
