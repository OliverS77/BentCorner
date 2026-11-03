// Navigation as a fixed bar: every tab stays in its place (the hand learns where „Decks“ is).
// Three groups – Capture (Scan, Sessions) | Collection (Library, Decks, Play) | Outside (Trade, Import/Export) –
// centred; Stats and Settings as icons on the right edge. The active tab carries the dot (Btn).
// (There used to be a carousel next to it – removed, the bar always stays the same.)
import QtQuick

Item {
    id: nav
    property var items: []            // [{key, text}] – only for the names
    property var groups: [["scan", "sessions"], ["library", "decks", "testing"], ["trade", "import"]]
    property var side: ["settings", "profile"]   // stats: a view of the "Sessions" tab (SessionsHead)
    property string current: "scan"
    property string backKey: ""
    // way back (review .90, Oliver): the tab you came from is lit just like the open one, the other tabs are dimmed a
    // little as long as the way back holds – and when it appears its lamp blinks twice, once (review .101 – a6)
    readonly property bool backOn: backKey !== "" && backKey !== current
    function dimmed(key) { return backOn && key !== current && key !== backKey }
    property real backPulse: -1   // the lamp's brightness while it blinks (-1: not blinking, lit as usual)
    readonly property string backTag: backOn ? backKey : ""   // (backKey is set before current changes)
    onBackTagChanged: if (backTag !== "" && shell.animate) backBlink.restart()
    SequentialAnimation {
        id: backBlink
        NumberAnimation { target: nav; property: "backPulse"; from: 1; to: 0; duration: 140 }
        NumberAnimation { target: nav; property: "backPulse"; to: 1; duration: 160 }
        NumberAnimation { target: nav; property: "backPulse"; to: 0; duration: 140 }
        NumberAnimation { target: nav; property: "backPulse"; to: 1; duration: 160 }
        PropertyAction { target: nav; property: "backPulse"; value: -1 }
    }
    property var badges: ({})
    property int clickDir: 0
    property int direction: 1
    signal picked(string key)
    signal friendsClicked(real rightX, real bottomY)   // own button right of the profile: friends menu
    property bool friendsOpen: false
    property bool friendsBadge: false                    // open requests
    // full screen: own close button (Windows/Linux far right, macOS left – where the window buttons sit)
    property bool closeBtn: false
    property bool closeLeft: Qt.platform.os === "osx"
    signal closeClicked()
    property real leftPad: 0          // space on the left (game button)
    property real rightPad: 0         // space on the right before the icons (download circle while loading)
    readonly property real leftW: (closeBtn && closeLeft ? iconW + 16 : 0) + leftPad
    readonly property real rightW: sideW + (closeBtn && !closeLeft ? iconW + 16 : 0) + rightPad

    readonly property var order: {
        var o = []
        for (var g = 0; g < groups.length; g++) o = o.concat(groups[g])
        return o.concat(side)
    }
    readonly property int nMain: order.length - side.length
    // gap between the groups (with a grey dot in the middle) – narrower when the window is too narrow for icon tabs
    // with the full gap (otherwise the tabs ran into the icons on the right, ~900 px)
    readonly property real gap: Math.max(14, Math.min(44, (room - nMain * 42 - (nMain - groups.length) * sp) / Math.max(1, groups.length - 1)))
    readonly property real sp: room < 900 ? 6 : 10          // gap within a group
    readonly property real iconW: width < 1000 ? 54 : 76   // icon tabs (Settings, Profile): narrower in a narrow window
    readonly property real friendsW: iconW + 8   // friends: own button next to the profile
    readonly property real sideW: side.length * iconW + (side.length - 1) * 8 + friendsW
    readonly property real room: width - 32 - rightW - leftW - 24
    readonly property real bw: Math.max(42, Math.min(150, (room - (groups.length - 1) * gap - (nMain - groups.length) * sp) / Math.max(1, nMain)))
    // too narrow for every name (level 2): only the open tab shows its name, the others their icon (P5, Oliver) –
    // the open tab as wide as its name needs, the others share the rest; changing tabs moves the widths smoothly
    FontMetrics { id: navFm; font.family: T.font; font.pixelSize: 14; font.bold: true }
    // the gaps between the groups give way first, so the tabs never reach the icons on the right
    readonly property real gapUse: !openOnly ? gap
        : Math.max(14, Math.min(44, (room - openW - (nMain - 1) * 42 - (nMain - groups.length) * sp) / Math.max(1, groups.length - 1)))
    readonly property real tabsRoom: room - (groups.length - 1) * gapUse - (nMain - groups.length) * sp
    readonly property real openW: Math.min(150, Math.ceil(textW(textOf(current))) + 22 + 9 + (T.gray ? 16 : 0) + 26,
                                           // never more than is left after the others' smallest icon keys and gaps
                                           Math.max(46, room - (nMain - 1) * 36 - (groups.length - 1) * 14 - (nMain - groups.length) * sp))
    readonly property real restW: Math.max(36, Math.min(76, (tabsRoom - openW) / Math.max(1, nMain - 1)))
    readonly property bool openOnly: level === 2 && indexOf(current) >= 0 && indexOf(current) < nMain
    // changing the open tab: the widths move from the old open tab to the new one (glide 0 → 1), nothing jumps
    property string wasOpen: ""      // the tab that was open before (during the glide)
    property string lastOpen: ""
    property real glide: 1
    NumberAnimation { id: glideAnim; target: nav; property: "glide"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic
                      onFinished: nav.wasOpen = nav.current }
    onCurrentChanged: {
        if (openOnly && lastOpen !== "" && lastOpen !== current && shell.animate) { wasOpen = lastOpen; glideAnim.restart() }
        else wasOpen = current
        lastOpen = current
    }
    Component.onCompleted: { lastOpen = current; wasOpen = current }
    function openWOf(key) {
        return Math.min(150, Math.ceil(textW(textOf(key))) + 22 + 9 + (T.gray ? 16 : 0) + 26,
                        Math.max(46, room - (nMain - 1) * 36 - (groups.length - 1) * 14 - (nMain - groups.length) * sp))
    }
    function tabW(i) {
        if (!openOnly) return bw
        var now = order[i] === current ? openW : restW
        if (glide >= 1 || wasOpen === current) return now
        var before = order[i] === wasOpen ? openWOf(wasOpen) : restW
        return before + (now - before) * glide
    }
    readonly property real groupW: {
        var s = (nMain - groups.length) * sp + (groups.length - 1) * gapUse
        for (var i = 0; i < nMain; i++) s += tabW(i)
        return s
    }
    // centred in the window, as long as it does not run into the icons on the right
    readonly property real x0: Math.max(16 + leftW, Math.min((width - groupW) / 2, width - 16 - rightW - 24 - groupW))
    readonly property int level: {
        var longest = 0
        for (var i = 0; i < nMain; i++) longest = Math.max(longest, lineLen(textOf(order[i])))
        var w0 = longest * 8.6 + 49, w1 = longest * 7.0 + 34
        return w0 <= bw ? 0 : (w1 <= bw ? 1 : 2)
    }

    function textOf(key) {
        for (var i = 0; i < items.length; i++) if (items[i].key === key) return items[i].text
        return key
    }
    // stacked names ("Logs\nStats", "Import\nExport": two small lines next to the icon) count by their longer line
    function lineLen(t) { var m = 0, ls = t.split("\n"); for (var i = 0; i < ls.length; i++) m = Math.max(m, ls[i].length); return m }
    function textW(t) { var m = 0, ls = t.split("\n"); for (var i = 0; i < ls.length; i++) m = Math.max(m, navFm.advanceWidth(ls[i])); return m }
    function oneLine(key) { return textOf(key).replace("\n", " & ") }   // tips: the name in one line
    function indexOf(key) { return order.indexOf(key) }
    function xOf(i) {   // left edge of tab i
        if (i >= nMain) return width - 16 - rightW + rightPad + (i - nMain) * (iconW + 8)
        var x = x0, k = 0
        for (var g = 0; g < groups.length; g++) {
            for (var j = 0; j < groups[g].length; j++) {
                if (k === i) return x
                x += tabW(k) + (j < groups[g].length - 1 ? sp : 0)
                k++
            }
            x += gapUse
        }
        return x
    }
    function wOf(i) { return i >= nMain ? iconW : tabW(i) }
    function setCurrent(key, animate) {
        if (key === "stats") key = "sessions"   // stats: a view of the Sessions tab
        var a = indexOf(current), b = indexOf(key)
        if (b < 0) return
        if (a >= 0 && a !== b) direction = b > a ? 1 : -1
        clickDir = 0
        current = key
    }

    Rectangle { anchors.fill: parent; color: T.bg }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: T.line2; opacity: 0.6 }

    WheelHandler {
        onWheel: function (ev) {
            var d = ev.angleDelta.y > 0 ? -1 : 1
            var i = nav.indexOf(nav.current)
            var j = Math.max(0, Math.min(nav.order.length - 1, i + d))
            if (j === i) return
            nav.clickDir = d
            nav.picked(nav.order[j])
        }
    }

    Repeater {
        model: nav.order
        delegate: Btn {
            required property string modelData
            required property int index
            readonly property bool icon: index >= nav.nMain
            x: nav.xOf(index)
            y: 8
            width: nav.wOf(index)
            height: nav.height - 18
            text: icon ? "" : nav.textOf(modelData)
            navIcon: modelData === "trade" ? "orbit" : modelData   // the Trade page is "Orbit" (Oliver, 2026-10-29)
            iconMotion: true
            navLevel: nav.openOnly && modelData === nav.current && nav.glide > 0.55 ? 0 : nav.level   // the name once there is room
            led: !icon
            active: modelData === nav.current || (nav.backOn && modelData === nav.backKey)
            pulse: nav.backOn && modelData === nav.backKey ? nav.backPulse : -1
            opacity: nav.dimmed(modelData) ? 0.5 : 1
            Behavior on opacity { enabled: shell.animate; NumberAnimation { duration: 220 } }
            badge: nav.badges[modelData] === true
            badgeCount: typeof nav.badges[modelData] === "number" ? nav.badges[modelData] : 0
            tip: modelData === nav.backKey ? shell.text("Back to") + " " + nav.oneLine(modelData)
                                           : modelData === "trade" ? nav.oneLine(modelData) + " · " + shell.text("Friends · Trade · Lists · Prices")
                                           : (icon || nav.level >= 2 ? nav.oneLine(modelData) : "")
            onClicked: {
                var a = nav.indexOf(nav.current)
                nav.clickDir = index > a ? 1 : (index < a ? -1 : 0)
                nav.picked(modelData)
            }
            // mouse rests on „Scan“: preload the AI already (separate process, does not freeze the UI)
            HoverHandler { id: preHover; enabled: modelData === "scan" }
            Timer { interval: 300; running: preHover.hovered && nav.current !== "scan"; onTriggered: shell.navHover(modelData) }
        }
    }

    // friends: own button right of the profile – opens the friends menu
    Btn {
        id: friendsBtn
        readonly property int pi: nav.indexOf("profile")
        visible: pi >= 0
        x: nav.xOf(pi) + nav.iconW + 8
        y: 8; width: nav.iconW; height: nav.height - 18
        navIcon: "friends"
        iconMotion: true
        active: nav.friendsOpen
        opacity: nav.backOn && !nav.friendsOpen ? 0.5 : 1
        Behavior on opacity { enabled: shell.animate; NumberAnimation { duration: 220 } }
        badge: nav.friendsBadge
        tip: shell.text("Friends")
        onClicked: { var p = mapToItem(null, width, height + 6); nav.friendsClicked(p.x, p.y) }
    }

    Btn {
        visible: nav.closeBtn
        x: nav.closeLeft ? 16 + nav.leftPad : nav.width - 16 - nav.iconW
        y: 8; width: nav.iconW; height: nav.height - 18
        glyph: "close"; danger: true
        tip: shell.text("Close Bent°Corner")
        onClicked: nav.closeClicked()
    }

    // grey dot in every group gap
    Repeater {
        model: nav.groups.length - 1
        Rectangle {
            required property int index
            readonly property int last: {   // last tab of the group before the gap
                var k = -1
                for (var g = 0; g <= index; g++) k += nav.groups[g].length
                return k
            }
            width: 5; height: 5; radius: 2.5
            x: nav.xOf(last) + nav.wOf(last) + nav.gapUse / 2 - width / 2
            y: 8 + (nav.height - 18) / 2 - height / 2
            color: T.dim
        }
    }
}
