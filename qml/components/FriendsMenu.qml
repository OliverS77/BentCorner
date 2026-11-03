// Friends menu (button with the friends icon next to the profile): add a friend by ID („+“), received requests,
// your friends as a plain list (a click opens the friend in Trade – folders, notes, sorting live there) and – only
// while there are any – „Sent requests“ greyed out. Your own ID lives in the profile (one place): a link leads there.
// pp = qprofile.ProfileBackend, tf = qtrade_friends.FriendsBackend.
import QtQuick

Item {
    id: fm
    property bool open: false
    property real ax: 0            // right edge (scene) the menu hangs from
    property real ay: 0            // top edge
    readonly property var pp: profilePage
    readonly property var tf: tradeFriends   // TRADE-SPLIT: FriendsBackend
    visible: open
    function show(rightX, topY) { ax = rightX; ay = topY; open = true; pp.refresh() }

    MouseArea { anchors.fill: parent; onClicked: { fm.open = false; fm.cancelAsk() } }   // clicking beside it closes
    function go(page) { open = false; cancelAsk(); shell.openBack(page) }
    function cancelAsk() { if (boxLd.item) boxLd.item.cancelAsk() }
    component FmLink: Text {   // a quiet link (text, no box)
        signal clicked()
        color: lh.hovered ? T.top : T.text2
        font.family: T.font; font.pixelSize: 12
        HoverHandler { id: lh; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: parent.clicked() }
    }

    Loader {   // the menu only while open
        id: boxLd
        anchors.fill: parent
        active: fm.open
        sourceComponent: Item {
    function cancelAsk() { ask.cancel() }
    Rectangle {
        id: box
        width: 380
        x: Math.max(8, Math.min(fm.ax - width, fm.width - width - 8)); y: fm.ay
        height: Math.min(fm.height - y - 16, inner.implicitHeight + 24)
        radius: 14; color: Qt.darker(T.surface, 1.05); border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent }   // clicks in the menu don't close it
        Flickable {
            x: 12; y: 12; width: parent.width - 24; height: parent.height - 24
            contentHeight: inner.implicitHeight
            clip: true; boundsBehavior: Flickable.StopAtBounds
            ScrollHint {}
            Column {
                id: inner
                width: parent.width
                spacing: 8
                // ---------- head: friends · „+“ = add by ID; your ID lives in the profile (only there) ----------
                Item {
                    width: parent.width; height: 40
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { text: shell.text("Friends"); color: T.text; font.family: T.font; font.pixelSize: 16; font.bold: true }
                        Text { visible: !(fm.pp.me.relay === true); text: shell.text("Exchange via the server is off")
                               color: T.dim; font.family: T.font; font.pixelSize: 12 }
                    }
                    Btn { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 36; height: 32
                          text: "+"; active: ask.open; tip: shell.text("Add friend")
                          onClicked: ask.open ? ask.cancel() : (ask.justClosed() ? undefined
                                     : ask.start("add", "", shell.text("Add friend"), "", shell.text("OK"))) }
                }
                InlineAsk {
                    id: ask
                    width: parent.width
                    placeholder: shell.text("ID, e.g. 7F3A-21C9-0B44-E1D2")
                    property string err: ""
                    onAccepted: function (mode, ident, text) { ask.err = fm.pp.addFriend(text) }
                    Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: T.line; visible: ask.height > 1 }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line; visible: ask.height > 1 }
                }
                Text { visible: ask.err !== ""; width: parent.width; wrapMode: Text.Wrap; text: ask.err
                       color: "#d48a8a"; font.family: T.font; font.pixelSize: 12 }
                FmLink { text: shell.text("Your ID and profile →"); onClicked: fm.go("profile") }

                // ---------- received requests ----------
                Repeater {
                    model: fm.pp.requests
                    Item {
                        required property var modelData
                        visible: modelData.dir === "in"
                        width: inner.width; height: visible ? 46 : 0
                        Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: T.line }
                        Column { anchors.verticalCenter: parent.verticalCenter
                                 Text { text: modelData.name; color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
                                 Text { text: shell.text("wants to be your friend"); color: T.muted; font.family: T.font; font.pixelSize: 11 } }
                        Row { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                              Btn { height: 28; compact: true; width: implicitWidth + 16; primary: true; text: shell.text("Accept")
                                    onClicked: fm.pp.answer(modelData.code, 1) }
                              Btn { height: 28; width: 30; compact: true; text: "✕"; tip: shell.text("Decline")
                                    onClicked: fm.pp.answer(modelData.code, 0) } }
                    }
                }

                // ---------- friends: a plain list – a click opens the friend in Trade (folders, notes … live there) ----------
                Item {
                    width: inner.width; height: 26
                    Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("FRIENDS"); color: T.dim
                           font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.5 }
                }
                Text { visible: fm.tf.friends.length === 0; width: parent.width; wrapMode: Text.Wrap
                       text: shell.text("No friends yet – tap + above and enter a friend's ID.")
                       color: T.dim; font.family: T.font; font.pixelSize: 12 }
                Repeater {
                    model: fm.tf.friends
                    Item {
                        id: fe
                        required property var modelData
                        width: inner.width; height: 44
                        Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: T.line }
                        Image { anchors.verticalCenter: parent.verticalCenter; height: 34; width: 34 * 63 / 88
                                source: fe.modelData.img || ""; sourceSize.height: 88; smooth: false }
                        Column { x: 34; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 34
                                 Text { width: parent.width; elide: Text.ElideRight; text: fe.modelData.name || ""
                                        color: rh.hovered ? T.top : T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
                                 Text { width: parent.width; elide: Text.ElideRight; text: fe.modelData.info || ""
                                        color: T.muted; font.family: T.font; font.pixelSize: 11 } }
                        HoverHandler { id: rh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: { fm.open = false; shell.openBack("trade"); fm.tf.openFriend(fe.modelData.fid) } }
                    }
                }
                FmLink { visible: fm.tf.friends.length > 0; text: shell.text("Folders, notes and more in Orbit →"); onClicked: fm.go("trade") }

                // ---------- sent requests (only while there are any) ----------
                Text {
                    visible: { for (var i = 0; i < fm.pp.requests.length; i++) if (fm.pp.requests[i].dir === "out") return true; return false }
                    text: shell.text("SENT REQUESTS"); color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true
                    font.letterSpacing: 1.5
                }
                Repeater {
                    model: fm.pp.requests
                    Rectangle {
                        required property var modelData
                        visible: modelData.dir === "out"
                        width: inner.width; height: visible ? 46 : 0; radius: 9; color: "transparent"
                        opacity: 0.5
                        Rectangle { x: 6; anchors.verticalCenter: parent.verticalCenter; height: 38; width: 38 * 63 / 88; radius: 3
                                    color: Qt.darker(T.surface, 1.2); border.width: 1; border.color: T.line2 }   // placeholder
                        Column { x: 42; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 90
                                 Text { width: parent.width; elide: Text.ElideRight; text: modelData.name
                                        color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
                                 Text { text: shell.text("waiting for an answer"); color: T.muted; font.family: T.font; font.pixelSize: 11 } }
                        Btn { anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                              width: 30; height: 26; compact: true; text: "✕"; tip: shell.text("Withdraw request")
                              onClicked: fm.pp.retract(modelData.code) }
                    }
                }
            }
        }
    }
    }
    }
}
