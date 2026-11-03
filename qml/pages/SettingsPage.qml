// Settings: search + sections on the left, on the right the chosen section or the search hits (mirrored form).
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var sp: settingsPage
    onVisibleChanged: sp.setActive(visible)
    Component.onCompleted: sp.setActive(visible)

    Rectangle {
        id: nav
        x: 18; y: 14
        width: 260; height: parent.height - 26
        radius: 16
        color: Qt.darker(T.surface, 1.1)
        border.width: 1; border.color: T.line
        SearchField {   // search across all sections (qsettings.search); Ctrl+F jumps here, Esc clears
            id: find
            x: 10; y: 12; width: parent.width - 20
            placeholder: shell.text("Search …") + "   Ctrl+F"
            onEdited: function (t) { searchT.restart() }
            onAccepted: page.sp.search(text)
            onTextChanged: if (text === "") page.sp.search("")
            Keys.onEscapePressed: { text = ""; dropFocus() }
            Timer { id: searchT; interval: 220; onTriggered: page.sp.search(find.text) }
        }
        Shortcut { sequences: [StandardKey.Find]; enabled: page.visible; onActivated: find.focusAll() }
        Connections { target: page.sp; function onChanged() { if (page.sp.query === "" && find.text !== "" && !find.inputFocus) find.text = "" } }
        Column {
            x: 8; y: find.y + find.height + 6; width: parent.width - 16
            spacing: 2
            Repeater {
                model: page.sp.pages
                delegate: Item {
                    required property var modelData
                    readonly property real head: modelData.section ? 30 : 0   // block heading (Often, Looks …)
                    width: parent.width; height: 48 + head
                    readonly property bool sel: modelData.key === page.sp.current
                    Text { visible: parent.head > 0; x: 12; y: 12; text: (modelData.section || "").toUpperCase()
                           color: T.dim; font.family: T.font; font.pixelSize: 10; font.letterSpacing: 1.6 }
                    Item {
                    y: parent.head; width: parent.width; height: 48
                    readonly property bool sel: parent.sel
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 2; radius: 10
                        visible: parent.sel || nh.hovered
                        color: parent.sel ? T.accent_deep : T.surface2
                        border.width: 1; border.color: parent.sel ? T.accent : T.line
                    }
                    NavIcon { id: secIcon; x: 13; anchors.verticalCenter: parent.verticalCenter; key: modelData.icon; s: 0.9
                              color: parent.sel ? T.text : T.muted; play: nh.hovered }
                    Text { x: 46; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 54
                           text: modelData.title; elide: Text.ElideRight
                           opacity: modelData.hits === 0 ? 0.45 : 1   // searching: sections without hits dimmed
                           color: parent.sel ? T.top : (nh.hovered ? T.text : T.text2)
                           font.family: T.font; font.pixelSize: 15 }
                    Lamp { visible: modelData.badge === true && modelData.hits < 0; anchors.right: parent.right
                           anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter }
                    Text { visible: modelData.hits > 0; anchors.right: parent.right; anchors.rightMargin: 14   // search hits
                           anchors.verticalCenter: parent.verticalCenter; text: modelData.hits; color: T.text2
                           font.family: T.font; font.pixelSize: 12 }
                    HoverHandler { id: nh; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: { secIcon.kick(); page.sp.show(modelData.key) } }
                    Timer { id: tipT; interval: 700; onTriggered: { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(modelData.sub, p.x, p.y) } }
                    Connections { target: nh; function onHoveredChanged() { if (nh.hovered) tipT.restart(); else { tipT.stop(); shell.tip("", 0, 0) } } }
                    }
                }
            }
        }
    }

    Item {
        id: right
        x: nav.x + nav.width + 18; y: 14
        width: parent.width - x - 18; height: parent.height - 26
        readonly property var cur: {
            if (page.sp.query !== "") return {title: page.sp.heading, sub: ""}
            var ps = page.sp.pages
            for (var i = 0; i < ps.length; i++) if (ps[i].key === page.sp.current) return ps[i]
            return {title: "", sub: ""}
        }
        // the content: at most ~1280 px wide and centred in the free space – on wide screens nothing runs out to the
        // far left and right edges any more (Oliver, review .101 o3)
        readonly property real colW: Math.min(width - 14, 1280)
        readonly property real colX: Math.max(0, (width - 14 - colW) / 2)
        Row {
            id: head
            x: right.colX
            spacing: 12
            Text { text: right.cur.title; color: T.text; font.family: T.font; font.pixelSize: 21; font.bold: true }
            Text { anchors.baseline: parent.children[0].baseline; text: right.cur.sub; color: T.dim
                   font.family: T.font; font.pixelSize: 13 }
        }
        Flickable {
            id: fl
            ScrollHint {}
            y: head.height + 12
            width: parent.width; height: parent.height - y
            contentHeight: form.height + 30
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickDeceleration: 3500
            Mirror {
                id: form
                x: right.colX; width: right.colW
                mirror: page.sp.mirror
            }
            onContentHeightChanged: if (contentY > contentHeight - height) contentY = Math.max(0, contentHeight - height)
        }
    }
    Connections { target: page.sp; function onChanged() { fl.contentY = 0 } }
}
