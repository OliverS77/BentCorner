// Profile: on top the card back and „You“ (name, ID), below your binders of ALL games (freely arrangeable, at most 8,
// then „+ New binder“), at the very bottom a line saying whether the profile is offline or shared with friends.
// Friends are in the menu at the profile button (FriendsMenu). Logic: qprofile.py, open binder: qbinder.BinderBackend.
import QtQuick
import "../components"

Item {
    id: page
    property string key
    readonly property var pp: profilePage
    property bool editBack: false
    onVisibleChanged: pp.setActive(visible)
    Component.onCompleted: pp.setActive(visible)

    // open binder: large over the page – only built when opened. With its own library that is ~11 000
    // items; merely invisible in the window they made every frame of the whole app more expensive (Qt 6.11 walks
    // all items of the window after every new tile)
    Loader {
        id: binderLd
        readonly property bool open: page.pp.binderView.isOpen && page.pp.binderView.hostPage === "profile"
        property bool warm: false   // keep built for 60 s after closing (like ViewPane.lazy), built asynchronously
        onOpenChanged: if (open) { binderCool.stop(); warm = true } else binderCool.restart()
        active: open || warm   // synchronous: without the library (only when editing) the binder builds quickly
        visible: open
        focus: open
        x: 24; y: 16; width: parent.width - 48; height: parent.height - 32
        sourceComponent: BinderView { bd: page.pp.binderView }
    }
    Timer { id: binderCool; interval: 60000; onTriggered: binderLd.warm = false }
    Flickable {
        id: fl
        visible: !binderLd.open
        y: 14
        width: Math.min(parent.width - 40, 1180); height: parent.height - 28
        anchors.horizontalCenter: parent.horizontalCenter
        clip: true
        contentHeight: col.implicitHeight + 30
        boundsBehavior: Flickable.StopAtBounds
        ScrollHint {}
        Column {
            id: col
            width: fl.width - 14
            spacing: 22

            // ---------- Header: card back + You ----------
            Row {
                spacing: 22
                width: parent.width
                Item {
                    width: 168; height: 236
                    Image { anchors.fill: parent; source: page.pp.backImage; smooth: false; fillMode: Image.PreserveAspectFit
                            sourceSize.height: 472 }
                    Rectangle { anchors.fill: parent; radius: 10; color: "transparent"; border.width: bh.hovered ? 2 : 0
                                border.color: T.text2 }
                    Btn { visible: bh.hovered || page.editBack; anchors.horizontalCenter: parent.horizontalCenter
                          anchors.bottom: parent.bottom; anchors.bottomMargin: 10; height: 30; compact: true
                          width: implicitWidth + 20; text: page.editBack ? shell.text("Done") : shell.text("Paint card back")
                          onClicked: page.editBack = !page.editBack }
                    HoverHandler { id: bh }
                }
                Item {   // no frame: the form is a heading with a divider (no boxes in boxes)
                    width: parent.width - 190; height: Math.max(236, meMirror.implicitHeight)
                    Mirror { id: meMirror; width: parent.width; mirror: page.pp.meForm }
                }
            }
            Loader {   // paint card back: expands below the header (heading with a divider, no frame) – built only then
                active: page.editBack
                visible: active
                width: parent.width; height: visible && item ? item.implicitHeight : 0
                sourceComponent: Mirror { width: parent.width; mirror: page.pp.backForm }
            }

            // ---------- Binders ----------
            Text { text: shell.text("YOUR BINDERS"); color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true
                   font.letterSpacing: 1.5 }
            BinderGrid { width: parent.width; pp: page.pp }

            // ---------- one line at the very bottom ----------
            Rectangle { width: parent.width; height: 1; color: T.line }
            Text { width: parent.width; wrapMode: Text.Wrap; text: page.pp.shareLine
                   color: T.muted; font.family: T.font; font.pixelSize: 13 }
        }
    }
}
