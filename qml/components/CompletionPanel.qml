// Set progress (like completion.CompletionPanel): at the top the set families (▸ expand), bar, „have“, „missing €“,
// sortable by column header (click again = reversed); at the bottom, below a draggable divider, the missing cards of the selected set. cp = qcompletion.CompletionBackend.
import QtQuick

Rectangle {
    id: p
    property var cp
    signal closeRequested()
    signal menuRequested(real sx, real sy)   // „Missing → list ▾“ (the Library shows the menu – here it would be clipped)
    radius: 14
    color: Qt.darker(T.surface, 1.1)
    border.width: 1; border.color: T.line
    clip: true

    Item {
        id: top
        x: 12; y: 10; width: p.width - 24; height: 34
        Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Set completion")
               color: T.text; font.family: T.font; font.pixelSize: 17; font.bold: true }
        Seg {   // three modes: chips in place (selection = brightness)
            anchors.right: close.left; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
            items: p.cp.modes; current: p.cp.mode
            onPicked: function (k) { p.cp.setMode(k) }
        }
        Btn { id: close; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
              width: 32; height: 32; compact: true; glyph: "close"; tip: shell.text("Close set progress")
              onClicked: p.closeRequested() }
    }
    Text {
        id: hint
        x: 12; y: top.y + top.height + 4; width: p.width - 24
        text: shell.text("One copy per collector number counts. Related sets are grouped (▸ expand).")
        color: T.muted; font.family: T.font; font.pixelSize: 12; wrapMode: Text.Wrap
    }
    // column headers (click = sort)
    Row {
        id: heads
        x: 12; y: hint.y + hint.height + 8; width: p.width - 24; height: 24
        readonly property var cols: [shell.text("Set"), shell.text("Progress"), shell.text("Have"), shell.text("Fehlt")]
        readonly property var widths: [width - 92 - 88 - 66, 92, 88, 66]
        Repeater {
            model: 4
            Text {
                required property int index
                width: heads.widths[index]; height: 24
                verticalAlignment: Text.AlignVCenter
                text: heads.cols[index] + (p.cp.sortCol === index ? (p.cp.sortAsc ? "  ↑" : "  ↓") : (sh.hovered ? "  ↕" : ""))
                color: p.cp.sortCol === index ? T.text : (sh.hovered ? T.text2 : T.muted)
                font.family: T.font; font.pixelSize: 12; font.bold: true
                HoverHandler { id: sh; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: p.cp.sortBy(index) }   // again = reversed
            }
        }
    }
    ListView {
        ScrollHint {}
        id: list
        x: 12; y: heads.y + heads.height + 2
        width: p.width - 24
        height: Math.max(90, Math.min(p.height - y - 190, (p.height - y) * p.split))
        clip: true
        model: p.cp.rows
        boundsBehavior: Flickable.StopAtBounds
        delegate: Rectangle {
            required property var modelData
            width: list.width; height: 30
            radius: 6
            color: modelData.id.split("/")[1] === p.cp.selected ? Qt.rgba(1, 1, 1, 0.09) : (rh.hovered ? Qt.rgba(1, 1, 1, 0.04) : "transparent")
            Row {
                anchors.verticalCenter: parent.verticalCenter
                Item {
                    width: heads.widths[0]; height: 30
                    Text {
                        x: 4 + modelData.level * 16
                        visible: modelData.expandable
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.expanded ? "▾" : "▸"
                        color: T.text2; font.pixelSize: 12
                        TapHandler { onTapped: p.cp.toggle(modelData.id) }
                    }
                    Text {
                        x: 20 + modelData.level * 16; width: parent.width - x - 6
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        color: modelData.done ? "#9fd1ad" : T.text
                        font.family: T.font; font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                }
                Item {
                    width: heads.widths[1]; height: 30
                    Rectangle { x: 2; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 10; height: 10; radius: 5
                                color: T.button
                        Rectangle { height: parent.height; radius: 5; width: Math.max(height, parent.width * modelData.have / Math.max(1, modelData.total))
                                    visible: modelData.have > 0
                                    gradient: Gradient { orientation: Gradient.Horizontal
                                        GradientStop { position: 0; color: modelData.done ? "#2f6f45" : T.accent_deep }
                                        GradientStop { position: 1; color: modelData.done ? "#8fd1a0" : T.accent } } } }
                }
                Text { width: heads.widths[2]; anchors.verticalCenter: parent.verticalCenter
                       text: modelData.have + "/" + modelData.total + " · " + modelData.pct + " %"
                       color: T.text2; font.family: T.font; font.pixelSize: 12 }
                Text { width: heads.widths[3]; anchors.verticalCenter: parent.verticalCenter
                       text: modelData.missing; color: T.muted; font.family: T.font; font.pixelSize: 12 }
            }
            HoverHandler { id: rh }
            TapHandler { onTapped: p.cp.select(modelData.id) }
        }
    }
    // divider between set list and missing cards: drag = change the split
    property real split: 0.55
    Item {
        id: divider
        x: 12; y: list.y + list.height + 2
        width: p.width - 24; height: 14
        Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 1; color: T.line2 }
        Rectangle {
            anchors.centerIn: parent; width: 46; height: 10; radius: 5; color: Qt.darker(T.surface, 1.1)
            Row { anchors.centerIn: parent; spacing: 4
                  Repeater { model: 3; Rectangle { width: 4; height: 4; radius: 2; color: dh.hovered || dd.active ? T.text : T.dim } } }
        }
        HoverHandler { id: dh; cursorShape: Qt.SizeVerCursor }
        DragHandler {
            id: dd
            target: null; xAxis.enabled: false
            property real start: 0
            onActiveChanged: if (active) start = list.height
            onTranslationChanged: if (active) p.split = Math.max(0.15, Math.min(0.85, (start + translation.y) / Math.max(1, p.height - list.y)))
        }
    }
    Column {
        id: low
        x: 12; y: divider.y + divider.height + 6; width: p.width - 24
        spacing: 6
        Text { width: parent.width; text: p.cp.nodeTitle; textFormat: Text.RichText; wrapMode: Text.Wrap
               color: T.text; font.family: T.font; font.pixelSize: 12 }
    }
    ListView {
        ScrollHint {}
        id: miss
        x: 12; y: low.y + low.height + 6
        width: p.width - 24
        height: p.height - y - 54
        clip: true
        model: p.cp.missing
        boundsBehavior: Flickable.StopAtBounds
        delegate: Text { required property string modelData; width: miss.width; height: 22; text: modelData
                         color: T.text2; font.family: T.font; font.pixelSize: 12; elide: Text.ElideRight; verticalAlignment: Text.AlignVCenter }
    }
    Row {
        x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 12
        spacing: 8
        Btn { text: shell.text("Show"); height: 32; enabled: p.cp.selected !== ""; tip: shell.text("Show the set in the library")
              onClicked: p.cp.showInLibrary() }
        Btn { id: wish; height: 32; enabled: p.cp.missingCount > 0
              text: shell.text("Fehlende") + " (" + p.cp.missingCount + ") → " + shell.text("List") + "  ▾"
              tip: shell.text("Missing cards of the set (exactly these prints) onto a wish or own list")
              onClicked: { var q = mapToItem(null, 0, height + 4); p.menuRequested(q.x, q.y) } }
    }
}
