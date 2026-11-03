// File browser in the program window (instead of the Windows dialog): places and drives on the left, the clickable
// path at the top, folder content in the middle, below file name (save), type and buttons. fb: qfiles.FilesBackend.
import QtQuick

Item {
    id: root
    property var fb
    implicitHeight: 600

    Rectangle {
        id: placesBox
        width: 210; height: root.height
        radius: 12; color: Qt.darker(T.surface, 1.15); border.width: 1; border.color: T.line
        ListView {
            ScrollHint {}
            anchors.fill: parent; anchors.margins: 6
            clip: true; boundsBehavior: Flickable.StopAtBounds
            model: root.fb.places
            delegate: Rectangle {
                id: pl
                required property var modelData
                width: ListView.view.width; height: 34; radius: 8
                readonly property bool here: root.fb.path.toLowerCase().indexOf(modelData.path.toLowerCase().replace(/\\$/, "")) === 0 && (modelData.drive ? false : true)
                color: plh.hovered ? T.surface2 : "transparent"
                Text { x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 20; elide: Text.ElideRight
                       text: (pl.modelData.drive ? "▭  " : "") + pl.modelData.name
                       color: T.text; font.family: T.font; font.pixelSize: 13 }
                HoverHandler { id: plh; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: root.fb.cd(pl.modelData.path) }
            }
        }
    }
    Item {
        id: main
        x: placesBox.width + 12; width: root.width - x; height: root.height
        Row {
            id: crumbs
            width: main.width; height: 34
            spacing: 6
            Btn { width: 40; height: 34; compact: true; text: "↑"; tip: shell.text("One folder up"); onClicked: root.fb.up() }
            Flickable {
                width: crumbs.width - 46 - newB.width - 6; height: 34
                contentWidth: crumbRow.width; clip: true
                flickableDirection: Flickable.HorizontalFlick
                contentX: Math.max(0, contentWidth - width)
                Row {
                    id: crumbRow
                    spacing: 2
                    Repeater {
                        model: root.fb.crumbs
                        delegate: Row {
                            required property var modelData
                            required property int index
                            Text { visible: index > 0; height: 34; verticalAlignment: Text.AlignVCenter; text: " › "
                                   color: T.dim; font.family: T.font; font.pixelSize: 13 }
                            Rectangle {
                                height: 34; width: ct.implicitWidth + 16; radius: 8
                                color: cth.hovered ? T.surface2 : "transparent"
                                Text { id: ct; anchors.centerIn: parent; text: modelData.name; color: T.text
                                       font.family: T.font; font.pixelSize: 13; font.bold: index === root.fb.crumbs.length - 1 }
                                HoverHandler { id: cth; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: root.fb.cd(modelData.path) }
                            }
                        }
                    }
                }
            }
            Btn { id: newB; height: 34; compact: true; text: shell.text("+ New folder"); visible: root.fb.mode !== "open" && root.fb.mode !== "many"
                  onClicked: root.fb.newFolder() }
        }
        Rectangle {
            id: listBox
            y: crumbs.height + 8
            width: main.width; height: main.height - y - foot.height - 10
            radius: 12; color: Qt.darker(T.surface, 1.1); border.width: 1; border.color: T.line
            ListView {
                ScrollHint {}
                id: list
                anchors.fill: parent; anchors.margins: 6
                clip: true; boundsBehavior: Flickable.StopAtBounds
                model: root.fb.entries
                delegate: Rectangle {
                    id: en
                    required property var modelData
                    width: list.width; height: 32; radius: 7
                    readonly property bool sel: root.fb.selected.indexOf(modelData.path) >= 0
                    color: sel ? T.surface2 : (enh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent")
                    border.width: sel ? 1 : 0; border.color: T.line2
                    Text { x: 10; anchors.verticalCenter: parent.verticalCenter; width: 22; text: en.modelData.dir ? "▸" : "·"
                           color: T.muted; font.pixelSize: 14 }
                    Text { x: 34; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 34 - 250; elide: Text.ElideMiddle
                           visible: !en.editing
                           text: en.modelData.name; color: en.modelData.dir ? T.text : T.text2
                           font.family: T.font; font.pixelSize: 13; font.bold: en.modelData.dir }
                    readonly property bool editing: root.fb.editing === modelData.path
                    Rectangle {   // new folder: type the name right here (Enter = done, Esc = leave as is)
                        visible: en.editing
                        x: 28; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 28 - 250; height: 26
                        radius: 6; color: T.surface; border.width: 1; border.color: T.line2
                        TextInput {
                            id: renameIn
                            x: 6; width: parent.width - 12; anchors.verticalCenter: parent.verticalCenter
                            text: en.modelData.name; selectByMouse: true; clip: true
                            selectionColor: T.line2; selectedTextColor: T.text
                            color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true
                            property bool done: false
                            function finish() { if (done) return; done = true; root.fb.rename(en.modelData.path, text) }
                            onAccepted: finish()
                            onActiveFocusChanged: if (!activeFocus && en.editing) finish()
                            Keys.onEscapePressed: { text = en.modelData.name; finish() }
                        }
                        onVisibleChanged: if (visible) { renameIn.done = false; renameIn.forceActiveFocus(); renameIn.selectAll() }
                        Component.onCompleted: if (visible) { renameIn.forceActiveFocus(); renameIn.selectAll() }
                    }
                    Text { x: parent.width - 240; width: 90; anchors.verticalCenter: parent.verticalCenter; horizontalAlignment: Text.AlignRight
                           text: en.modelData.size; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                    Text { x: parent.width - 140; width: 130; anchors.verticalCenter: parent.verticalCenter; horizontalAlignment: Text.AlignRight
                           text: en.modelData.date; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                    HoverHandler { id: enh; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: function (ev, b) {
                            if (tapCount !== 1) return
                            root.fb.click(en.modelData.path, (ev.modifiers & (Qt.ControlModifier | Qt.ShiftModifier)) !== 0)
                        }
                        onDoubleTapped: root.fb.open(en.modelData.path)
                    }
                }
                Text { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 6
                       visible: root.fb.error !== ""; text: root.fb.error; color: "#e08080"; font.family: T.font; font.pixelSize: 12 }
                Text { anchors.centerIn: parent; visible: list.count === 0; text: shell.text("This folder is empty.")
                       color: T.dim; font.family: T.font; font.pixelSize: 14 }
            }
        }
        Item {
            id: foot
            y: main.height - height
            width: main.width; height: 38
            Rectangle {
                id: nameBox
                visible: root.fb.mode === "save"
                width: Math.max(200, main.width - typeBox.width - btns.width - 24); height: 38
                radius: 10; color: T.surface; border.width: 1; border.color: nameIn.activeFocus ? T.line2 : T.line
                TextInput {
                    id: nameIn
                    x: 12; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter
                    text: root.fb.fileName; clip: true; selectByMouse: true
                    color: T.text; font.family: T.font; font.pixelSize: 14
                    onTextEdited: root.fb.setFileName(text)
                    onAccepted: root.fb.accept()
                    Component.onCompleted: if (root.fb.mode === "save") { forceActiveFocus(); var dot = text.lastIndexOf("."); select(0, dot > 0 ? dot : text.length) }
                }
                Connections { target: root.fb; function onSelChanged() { if (nameIn.text !== root.fb.fileName) nameIn.text = root.fb.fileName } }
            }
            DropList {
                id: typeBox
                x: nameBox.visible ? nameBox.width + 12 : 0
                visible: root.fb.mode !== "dir"
                width: Math.min(300, main.width * 0.32); height: 38
                items: root.fb.filters; current: root.fb.filter
                onPicked: function (k) { root.fb.setFilter(k) }
            }
            Row {
                id: btns
                anchors.right: parent.right
                spacing: 8
                Btn { height: 38; width: 120; text: shell.text("Cancel"); onClicked: root.fb.cancel() }
                Btn { height: 38; width: Math.max(140, implicitWidth); primary: true; enabled: root.fb.canAccept
                      text: root.fb.acceptText; onClicked: root.fb.accept() }
            }
        }
    }
    Keys.onPressed: function (e) { if (e.key === Qt.Key_Backspace && !nameIn.activeFocus) { root.fb.up(); e.accepted = true } }
}
