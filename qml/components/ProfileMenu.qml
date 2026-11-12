// Profile menu on the profile button (Oliver after the sync test T1, lead 06.11.): a small list right under the button –
// „Profile“ (the page, as the button did before), „Edit“ (the page with the name field focused), „Devices“ (Settings →
// Your devices, only where the sync is built in: shell.syncBuilt). No dimming; a click beside it closes it.
import QtQuick

Item {
    id: pm
    property bool open: false
    property real ax: 0            // right edge (scene) the menu hangs from
    property real ay: 0            // top edge
    visible: open
    function show(rightX, topY) { ax = rightX; ay = topY; open = true }
    function go(fn) { open = false; fn() }

    MouseArea { anchors.fill: parent; onClicked: pm.open = false }   // clicking beside it closes
    Shortcut { sequence: "Esc"; enabled: pm.open; onActivated: pm.open = false }

    Rectangle {
        id: box
        width: 240
        x: Math.max(8, Math.min(pm.ax - width, pm.width - width - 8)); y: pm.ay
        height: col.implicitHeight + 16
        radius: 14; color: Qt.darker(T.surface, 1.05); border.width: 1; border.color: T.line2
        MouseArea { anchors.fill: parent }   // clicks in the menu don't close it
        Column {
            id: col
            x: 8; y: 8; width: parent.width - 16
            spacing: 4
            Repeater {
                model: [{key: "profile", text: shell.text("Profile")}, {key: "edit", text: shell.text("Edit")}]
                       .concat(shell.syncBuilt ? [{key: "devices", text: shell.text("Devices")}] : [])
                Btn {
                    required property var modelData
                    width: col.width; height: 44
                    text: modelData.text
                    objectName: "profilemenu-" + modelData.key
                    onClicked: pm.go(function () {
                        if (modelData.key === "profile") shell.pick("profile", 0)
                        else if (modelData.key === "edit") shell.profileEdit()
                        else shell.openDevices()
                    })
                }
            }
        }
    }
}
