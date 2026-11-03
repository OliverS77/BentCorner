// Import/Export: on the left „Bring in“ and „Hand out“, on the right the chosen item (mirrored form).
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var ip: importPage
    onVisibleChanged: ip.setActive(visible)
    Component.onCompleted: ip.setActive(visible)

    Rectangle {
        id: nav
        x: 20; y: 14
        width: 280; height: parent.height - 28
        radius: 16
        color: Qt.darker(T.surface, 1.1)
        border.width: 1; border.color: T.line
        Flickable {
            ScrollHint {}
            anchors.fill: parent; anchors.margins: 8
            contentHeight: navCol.implicitHeight
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: navCol
                width: parent.width
                spacing: 2
                Repeater {
                    model: page.ip.groups
                    delegate: Column {
                        required property var modelData
                        required property int index
                        width: navCol.width
                        spacing: 2
                        Item {   // divider between the sections (Bring in | Hand out)
                            visible: index > 0
                            width: navCol.width; height: 22
                            Rectangle { x: 10; width: parent.width - 20; height: 1; anchors.bottom: parent.bottom
                                        color: T.line }
                        }
                        Text { x: 10; height: 38; bottomPadding: 8; verticalAlignment: Text.AlignBottom; text: modelData.title
                               color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.5 }
                        Repeater {
                            model: modelData.tabs
                            delegate: Item {
                                required property var modelData
                                width: navCol.width; height: 44
                                readonly property bool sel: modelData.key === page.ip.current
                                Rectangle { anchors.fill: parent; anchors.margins: 2; radius: 10
                                            visible: parent.sel || th.hovered
                                            color: parent.sel ? T.accent_deep : T.surface2
                                            border.width: 1; border.color: parent.sel ? T.accent : T.line }
                                Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: modelData.icon
                                       color: parent.sel ? T.text : T.muted; font.pixelSize: 14 }
                                Text { x: 44; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 52
                                       text: modelData.title; elide: Text.ElideRight
                                       color: parent.sel ? T.top : (th.hovered ? T.text : T.text2)
                                       font.family: T.font; font.pixelSize: 14 }
                                Lamp { visible: modelData.badge === true; anchors.right: parent.right; anchors.rightMargin: 14
                                       anchors.verticalCenter: parent.verticalCenter }
                                HoverHandler { id: th; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: page.ip.show(modelData.key) }
                                Timer { id: tipT; interval: 700; onTriggered: { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(modelData.sub, p.x, p.y) } }
                                Connections { target: th; function onHoveredChanged() { if (th.hovered) tipT.restart(); else { tipT.stop(); shell.tip("", 0, 0) } } }
                            }
                        }
                    }
                }
                // backups live only in the settings now – the way there (Oliver, review .72)
                Item {
                    width: navCol.width; height: 22
                    Rectangle { x: 10; width: parent.width - 20; height: 1; anchors.bottom: parent.bottom; color: T.line }
                }
                Item {
                    width: navCol.width; height: 52
                    Rectangle { anchors.fill: parent; anchors.topMargin: 8; anchors.margins: 2; radius: 10
                                visible: bh.hovered; color: T.surface2; border.width: 1; border.color: T.line }
                    Text { x: 14; y: 8 + (parent.height - 8 - height) / 2; text: "↗"
                           color: bh.hovered ? T.text : T.muted; font.pixelSize: 14 }
                    Text { x: 44; y: 8 + (parent.height - 8 - height) / 2; width: parent.width - 52
                           text: page.ip.backupLink.title; elide: Text.ElideRight
                           color: bh.hovered ? T.text : T.text2; font.family: T.font; font.pixelSize: 14 }
                    HoverHandler { id: bh; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: page.ip.openBackup() }
                    Timer { id: btipT; interval: 700; onTriggered: { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(page.ip.backupLink.sub, p.x, p.y) } }
                    Connections { target: bh; function onHoveredChanged() { if (bh.hovered) btipT.restart(); else { btipT.stop(); shell.tip("", 0, 0) } } }
                }
            }
        }
    }
    Flickable {
        ScrollHint {}
        id: fl
        x: nav.x + nav.width + 18; y: 14
        width: parent.width - x - 20; height: parent.height - 28
        contentHeight: form.height + 30
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Mirror { id: form; width: fl.width - 14; mirror: page.ip.mirror }
    }
    Connections { target: page.ip; function onChanged() { fl.contentY = 0 } }
}
