// Chips of the active filters (like libview.ChipGroup): one box per filter kind „Title │ value value“. Clicking a
// value removes it, clicking the title turns the group off; removed values stay grey briefly with ↺ (click = undo),
// then fade and the others slide together. Data: groups (from Python), clicks: chipClicked(id).
// New values grow from width 0 and push the following chips (e.g. „Clear all filters“) directly ahead of
// them; what Python removes first fades, then slides together towards the left edge (staying in the list as
// „gone“ meanwhile).
import QtQuick

Item {
    id: bar
    property var groups: []
    property var lead: null            // bright chip in front (e.g. selected list): {icon, text}
    signal chipClicked(string id)
    signal leadClicked()
    implicitHeight: flow.implicitHeight
    height: groups.length || lead ? flow.implicitHeight : 0
    Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    clip: true

    ListModel { id: gm }
    // widths currently growing or shrinking: meanwhile the bar follows directly (without its own move animation,
    // which would otherwise restart every frame and lag behind)
    property int sizing: 0
    function removeGone(lm, key, field) {
        for (var i = lm.count - 1; i >= 0; i--) if (lm.get(i).gone && lm.get(i)[field] === key) { lm.remove(i); return }
    }

    // take data from Python into the lists without rebuilding existing boxes (otherwise everything jumps)
    function vkey(v) { return v.text }   // the same value stays the same chip (even when it turns grey)
    function syncValues(lm, vals) {
        var i, j, k, m
        for (i = lm.count - 1; i >= 0; i--) {   // gone: fade out first, then slide together
            var keep = false
            for (j = 0; j < vals.length; j++) if (vkey(vals[j]) === lm.get(i).vk) keep = true
            if (!keep && !lm.get(i).gone) { lm.setProperty(i, "gone", true); lm.setProperty(i, "collapsing", true) }
        }
        // order: the remaining ones (also fading) stay where they are; new ones at their place
        var pos = 0
        for (k = 0; k < vals.length; k++) {
            var v = vals[k], at = -1
            for (m = 0; m < lm.count; m++) if (lm.get(m).vk === vkey(v)) at = m
            while (pos < lm.count && lm.get(pos).gone && pos !== at) pos++
            var props = {cid: v.cid, text: v.text, kind: v.kind, neg: v.neg, collapsing: v.collapsing, gone: false, vk: vkey(v)}
            if (at < 0) lm.insert(Math.min(pos, lm.count), props)
            else {
                if (at > pos) { lm.move(at, pos, 1); at = pos }
                for (var p in props) lm.setProperty(at, p, props[p])
            }
            pos = at < 0 ? Math.min(lm.count, pos + 1) : Math.max(pos, at + 1)
        }
    }
    function sync() {
        var gs = groups, i, j, k, m
        for (i = gm.count - 1; i >= 0; i--) {   // whole group gone: fade, then slide together towards the left edge
            var keep = false
            for (j = 0; j < gs.length; j++) if (gs[j].key === gm.get(i).key) keep = true
            if (!keep && !gm.get(i).gone) { gm.setProperty(i, "gone", true); gm.setProperty(i, "collapsing", true) }
        }
        var pos = 0
        for (k = 0; k < gs.length; k++) {
            var g = gs[k], at = -1
            for (m = 0; m < gm.count; m++) if (gm.get(m).key === g.key) at = m
            while (pos < gm.count && gm.get(pos).gone && pos !== at) pos++
            var props = {key: g.key, gid: g.id, title: g.title, titleId: g.titleId, coverId: g.coverId,
                         grey: g.grey, clear: g.clear, collapsing: g.collapsing, gone: false}
            if (at < 0) {
                props.values = []
                gm.insert(Math.min(pos, gm.count), props)
                at = Math.min(pos, gm.count - 1)
            } else {
                if (at > pos) { gm.move(at, pos, 1); at = pos }
                for (var p in props) gm.setProperty(at, p, props[p])
            }
            syncValues(gm.get(at).values, g.values)
            pos = Math.max(pos, at + 1)
        }
    }
    onGroupsChanged: sync()

    Flow {
        id: flow
        width: bar.width
        spacing: 8
        move: bar.sizing > 0 ? null : moveTr
        Transition { id: moveTr; NumberAnimation { properties: "x,y"; duration: 260; easing.type: Easing.InOutCubic } }
        Rectangle {   // bright chip in front: „you are looking at this list“ (click = all cards again)
            visible: !!bar.lead
            height: 30; radius: 15
            width: visible ? leadRow.implicitWidth + 24 : 0
            color: lh.hovered ? T.hi : "#dedede"
            border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.6)
            Row {
                id: leadRow
                x: 10; anchors.verticalCenter: parent.verticalCenter
                spacing: 7
                NavIcon { anchors.verticalCenter: parent.verticalCenter; key: bar.lead ? bar.lead.icon : ""; color: T.onHi; s: 0.7 }
                Text { anchors.verticalCenter: parent.verticalCenter; text: bar.lead ? bar.lead.text : ""
                       color: T.onHi; font.family: T.font; font.pixelSize: 13; font.bold: true }
                Text { anchors.verticalCenter: parent.verticalCenter; text: "✕"; color: "#333333"; font.pixelSize: 11 }
            }
            HoverHandler { id: lh; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: bar.leadClicked() }
        }
        Repeater {
            model: gm
            delegate: Item {
                id: box
                required property string gid
                required property string title
                required property string titleId
                required property string coverId
                required property bool grey
                required property bool clear
                required property bool collapsing
                required property bool gone
                required property string key
                required property var values
                height: 30
                // k: 1 = fully there, 0 = collapsed (only the group's own fade in/out is animated –
                // if its values grow or shrink, the box follows directly)
                property real k: collapsing ? 0 : 1
                Behavior on k {
                    SequentialAnimation {
                        PauseAnimation { duration: box.collapsing ? 650 : 0 }
                        NumberAnimation { duration: 320; easing.type: Easing.InOutCubic }
                    }
                }
                readonly property bool sizing: k > 0 && k < 1
                onSizingChanged: bar.sizing += sizing ? 1 : -1
                Component.onDestruction: if (sizing) bar.sizing--
                onKChanged: if (k <= 0 && gone) rmBox.start()
                onGoneChanged: if (k <= 0 && gone) rmBox.start()
                Timer { id: rmBox; interval: 1; onTriggered: if (box.gone) bar.removeGone(gm, box.key, "key") }
                width: Math.round((row.implicitWidth + 16) * k)
                clip: true
                opacity: collapsing ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: 500; easing.type: Easing.InOutSine } }
                Component.onCompleted: { appear.start() }
                NumberAnimation { id: appear; target: box; property: "scale"; from: 0.92; to: 1; duration: 220
                                  easing.type: Easing.OutCubic }

                Rectangle {
                    anchors.fill: parent
                    radius: 15
                    color: box.clear ? "#3a2026" : Qt.darker(T.surface, 1.05)
                    border.width: 1
                    border.color: box.clear ? "#7a3b46" : T.line2
                }
                Row {
                    id: row
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Text {   // title (click = group off)
                        visible: box.title !== ""
                        anchors.verticalCenter: parent.verticalCenter
                        text: box.title
                        color: box.grey ? Qt.rgba(0.67, 0.67, 0.67, 0.45) : (th.hovered && box.titleId ? T.text : T.muted)
                        font.family: T.font; font.pixelSize: 12; font.bold: true
                        HoverHandler { id: th; cursorShape: box.titleId ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        TapHandler { enabled: box.titleId !== ""; onTapped: bar.chipClicked(box.titleId) }
                    }
                    Rectangle { visible: box.title !== ""; width: 1; height: 16; color: T.line2
                                anchors.verticalCenter: parent.verticalCenter }
                    Repeater {
                        model: box.values
                        delegate: Item {
                            id: chip
                            required property string cid
                            required property string text
                            required property string kind
                            required property bool neg
                            required property bool collapsing
                            required property bool gone
                            required property string vk
                            readonly property bool undo: kind === "undo" || kind === "grey"
                            height: 22
                            // new: grows from 0 and pushes the following chips ahead; gone: fade, then
                            // slide together
                            property bool born: false
                            Component.onCompleted: born = true
                            property real k: collapsing || !born ? 0 : 1
                            Behavior on k {
                                SequentialAnimation {
                                    PauseAnimation { duration: chip.collapsing ? 650 : 0 }
                                    NumberAnimation { duration: chip.collapsing ? 320 : 280; easing.type: Easing.InOutCubic }
                                }
                            }
                            readonly property bool sizing: k > 0 && k < 1
                            onSizingChanged: bar.sizing += sizing ? 1 : -1
                            Component.onDestruction: if (sizing) bar.sizing--
                            onKChanged: if (k <= 0 && gone) rmChip.start()
                            onGoneChanged: if (k <= 0 && gone) rmChip.start()
                            Timer { id: rmChip; interval: 1; onTriggered: if (chip.gone) bar.removeGone(box.values, chip.vk, "vk") }
                            width: Math.round((label.implicitWidth + 18) * k)
                            clip: true
                            anchors.verticalCenter: parent.verticalCenter
                            opacity: collapsing ? 0 : (born ? 1 : 0)
                            Behavior on opacity { NumberAnimation { duration: chip.collapsing ? 500 : 260; easing.type: Easing.InOutSine } }
                            Rectangle {
                                anchors.fill: parent
                                radius: 11
                                color: ch.hovered && chip.kind !== "grey" ? Qt.rgba(1, 1, 1, 0.12)
                                       : chip.undo ? Qt.rgba(0.47, 0.47, 0.47, 0.16)
                                       : chip.kind === "clear" ? "transparent"
                                       : chip.neg ? Qt.rgba(1, 0.3, 0.37, 0.14) : Qt.rgba(1, 1, 1, 0.07)
                                Behavior on color { ColorAnimation { duration: 120 } }
                            }
                            Text {
                                id: label
                                anchors.centerIn: parent
                                text: chip.text
                                color: chip.undo ? Qt.rgba(0.67, 0.67, 0.67, 0.4)
                                       : chip.kind === "clear" ? "#ffd6dc" : chip.neg ? "#ff9aa3" : T.text
                                font.family: T.font; font.pixelSize: 12; font.bold: true
                            }
                            UndoIcon { visible: chip.kind === "undo"; anchors.centerIn: parent }
                            HoverHandler { id: ch; cursorShape: chip.kind === "grey" ? Qt.ArrowCursor : Qt.PointingHandCursor }
                            TapHandler { enabled: chip.kind !== "grey"; onTapped: bar.chipClicked(chip.cid) }
                        }
                    }
                }
                // whole group off: ONE ↺ over the box – click anywhere = undo
                Item {
                    anchors.fill: parent
                    visible: box.coverId !== ""
                    UndoIcon { anchors.centerIn: parent; size: 16 }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: bar.chipClicked(box.coverId) }
                }
            }
        }
    }

    component UndoIcon: Canvas {
        property real size: 14
        width: size; height: size
        onPaint: {
            var g = getContext("2d"); g.reset()
            var r = size / 2 - 2
            g.strokeStyle = "#d6d6d6"; g.fillStyle = "#d6d6d6"; g.lineWidth = 1.6; g.lineCap = "round"
            g.beginPath(); g.arc(size / 2, size / 2, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 290 / 180 * -1, true); g.stroke()
            var tx = size / 2, ty = size / 2 - r
            g.beginPath(); g.moveTo(tx - 3.6, ty); g.lineTo(tx + 1.4, ty - 3.2); g.lineTo(tx + 1.4, ty + 3.2); g.closePath(); g.fill()
        }
    }
}
