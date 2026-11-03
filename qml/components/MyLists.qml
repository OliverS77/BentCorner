// „My lists“ in the detail view: per section (wish, own, trade lists) the lists with two equally wide
// buttons (wish/own: „+ this one“ · „+ any“, trade: „+ this one“ · „+ all“). If the card is already on a
// list, the list can be expanded (▸) – collapsed it shows a short summary; −/+/✕ only appear
// on hover. det = qdetail.DetailBackend.
import QtQuick

Column {
    id: m
    property var det
    readonly property real btnW: 84
    width: parent ? parent.width : 300
    spacing: 2

    Repeater {
        model: m.det ? m.det.myLists : []
        delegate: Column {
            id: sec
            required property var modelData
            required property int index
            width: m.width
            spacing: 2
            // section header
            Item {
                width: parent.width; height: sec.index === 0 ? 26 : 38
                Text { x: 2; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                       text: (sec.modelData.title || "").toUpperCase()
                       color: T.text; font.family: T.font; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1.3 }
                Text { anchors.right: parent.right; anchors.rightMargin: 4; anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                       text: "+  " + shell.text("New list")
                       color: nl.hovered ? T.text : T.muted; font.family: T.font; font.pixelSize: 12
                       HoverHandler { id: nl; cursorShape: Qt.PointingHandCursor }
                       TapHandler { onTapped: m.det.newMyList(sec.modelData.kind) } }
            }
            Repeater {
                model: sec.modelData.lists
                delegate: Column {
                    id: li
                    required property var modelData
                    width: m.width
                    readonly property bool has: modelData.entries.length > 0
                    // list: name (+ summary when collapsed) · two buttons
                    Item {
                        opacity: li.modelData.dim ? 0.45 : 1   // trade list, but the card is not in the collection
                        width: parent.width; height: (li.has && !li.modelData.open) || (!li.has && !!li.modelData.summary) ? 46 : 36
                        Rectangle { anchors.fill: parent; radius: 8; color: lh.hovered && li.has ? Qt.lighter(T.surface, 1.08) : "transparent" }
                        Chevron {   // centred on the name line (not on the whole row with summary)
                            visible: li.has
                            x: 2; size: 15
                            y: nameCol.y + nameTxt.height / 2 - height / 2
                            open: li.modelData.open
                            color: lh.hovered ? T.text : T.text2
                        }
                        Column {   // name, below it (collapsed) the summary
                            id: nameCol
                            x: 22; anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - x - 2 * m.btnW - 14
                            spacing: 1
                            Text { id: nameTxt; width: parent.width; elide: Text.ElideRight; text: li.modelData.name || ""
                                   color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: li.has }
                            Text { visible: (li.has && !li.modelData.open) || (!li.has && !!li.modelData.summary)
                                   width: parent.width; elide: Text.ElideRight
                                   text: li.modelData.summary; color: T.dim; font.family: T.font; font.pixelSize: 11 }
                        }
                        HoverHandler { id: lh; cursorShape: li.has ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        TapHandler { enabled: li.has; onTapped: m.det.toggleMyList(li.modelData.key) }
                        Row {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            Repeater {
                                model: li.modelData.buttons
                                Btn { required property var modelData
                                      width: m.btnW; height: 28; compact: true
                                      text: modelData.text; tip: modelData.tip; enabled: modelData.enabled
                                      onClicked: m.det.listDo(modelData.fid) }
                            }
                        }
                    }
                    // entries (expanded)
                    Repeater {
                        model: li.modelData.open ? li.modelData.entries : []
                        delegate: Item {
                            id: en
                            required property var modelData
                            width: m.width; height: 30
                            Rectangle { anchors.fill: parent; anchors.leftMargin: 18; radius: 7
                                        color: eh.hovered ? Qt.lighter(T.surface, 1.06) : "transparent" }
                            Rectangle { x: 28; anchors.verticalCenter: parent.verticalCenter; width: 7; height: 7; radius: 3.5
                                        color: en.modelData.here ? "#e6e6e6" : T.line2 }
                            Text { x: 44; anchors.verticalCenter: parent.verticalCenter
                                   width: parent.width - x - 140; elide: Text.ElideRight
                                   text: en.modelData.text
                                   color: en.modelData.red ? "#ff8a95" : (en.modelData.here ? T.text : T.text2)
                                   font.family: T.font; font.pixelSize: 13 }
                            Text { anchors.right: parent.right; anchors.rightMargin: eh.hovered ? 104 : 8
                                   anchors.verticalCenter: parent.verticalCenter
                                   text: en.modelData.n + "×"; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                            HoverHandler { id: eh }
                            Row {
                                visible: eh.hovered
                                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                spacing: 3
                                Btn { width: 30; height: 24; compact: true; text: "−"; tip: shell.text("One less")
                                      onClicked: m.det.listDo(en.modelData.minus) }
                                Btn { width: 30; height: 24; compact: true; text: "+"; tip: shell.text("One more")
                                      enabled: en.modelData.plus !== ""; onClicked: m.det.listDo(en.modelData.plus) }
                                Btn { width: 30; height: 24; compact: true; text: "✕"; danger: true
                                      tip: shell.text("Remove from list"); onClicked: m.det.listDo(en.modelData.remove) }
                            }
                        }
                    }
                }
            }
        }
    }
    Item { width: 1; height: 4 }
}
